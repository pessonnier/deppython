from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Iterable

from .errors import BundleError, CommandError, PyDepotError
from .model import Artifact, Manifest
from .util import (
    Progress,
    default_python_executable,
    default_python_version,
    normalize_python_version,
    python_version,
    run_streaming,
    sha256_file,
    venv_python,
)


MANIFEST_NAME = "manifest.json"
LOCK_NAME = "requirements.lock"
WHEELHOUSE = "packages"


@dataclass
class ExportOptions:
    output: Path
    packages: list[str] = field(default_factory=list)
    requirements: Path | None = None
    python_version: str = field(default_factory=default_python_version)
    implementation: str = "cp"
    platforms: list[str] = field(default_factory=list)
    abis: list[str] = field(default_factory=list)
    index_url: str | None = None
    extra_index_urls: list[str] = field(default_factory=list)
    prerelease: bool = False
    python_executable: str = field(default_factory=default_python_executable)


@dataclass
class ImportOptions:
    bundle: Path
    venv_path: Path | None = None
    python_executable: str = field(default_factory=default_python_executable)
    target: Path | None = None
    verify: bool = True
    ignore_python_version: bool = False
    upgrade: bool = False


def export_bundle(options: ExportOptions, progress: Progress | None = None) -> Manifest:
    notify = progress or (lambda _message: None)
    target_version = normalize_python_version(options.python_version)
    resolver_version = python_version(options.python_executable)
    if resolver_version != target_version:
        raise PyDepotError(
            f"L'interpréteur d'export utilise Python {resolver_version}, mais le bundle cible "
            f"Python {target_version}. pip évalue certains marqueurs de dépendances avec "
            "l'interpréteur d'export ; choisissez un Python de même version majeure/mineure "
            "(un Python portable peut être installé depuis la TUI)."
        )
    _validate_platform_environment(options.platforms)
    requested = list(options.packages)
    if options.requirements:
        if not options.requirements.is_file():
            raise PyDepotError(f"Fichier requirements introuvable: {options.requirements}")
        requested.extend(_read_top_level_requirements(options.requirements))
    if not options.packages and not options.requirements:
        raise PyDepotError("Indiquez au moins un paquet ou un fichier requirements.")
    if not requested and options.requirements:
        requested.append(f"-r {options.requirements.name}")

    output = options.output.resolve()
    if output.suffix.lower() != ".pybundle":
        output = output.with_suffix(output.suffix + ".pybundle" if output.suffix else ".pybundle")
    output.parent.mkdir(parents=True, exist_ok=True)

    notify(f"Résolution de {len(requested)} dépendance(s) pour Python {target_version}…")
    with tempfile.TemporaryDirectory(prefix="pydepot-export-") as temporary:
        root = Path(temporary)
        package_dir = root / WHEELHOUSE
        package_dir.mkdir()
        command = _download_command(options, target_version, package_dir)
        run_streaming(command, notify)

        files = sorted(path for path in package_dir.iterdir() if path.is_file())
        if not files:
            raise BundleError("pip n'a téléchargé aucun artefact.")
        artifacts = [_artifact_from_file(path) for path in files]
        lock_lines = _lock_lines(artifacts)
        if not lock_lines:
            raise BundleError("Aucun wheel exploitable n'a été trouvé dans le téléchargement.")

        manifest = Manifest(
            python_version=target_version,
            implementation=options.implementation,
            platforms=list(options.platforms),
            abis=list(options.abis),
            requested=requested,
            artifacts=artifacts,
        )
        (root / MANIFEST_NAME).write_bytes(
            (json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
        (root / LOCK_NAME).write_bytes(("\n".join(lock_lines) + "\n").encode("utf-8"))
        _write_bundle_atomically(root, output)

    notify(f"Bundle créé: {output} ({len(manifest.artifacts)} fichier(s))")
    return manifest


def inspect_bundle(bundle: Path, verify: bool = False) -> Manifest:
    bundle = bundle.resolve()
    if not bundle.is_file():
        raise BundleError(f"Bundle introuvable: {bundle}")
    try:
        with zipfile.ZipFile(bundle) as archive:
            _validate_members(archive)
            try:
                raw = archive.read(MANIFEST_NAME)
            except KeyError as exc:
                raise BundleError("Le manifeste est absent du bundle.") from exc
            try:
                manifest = Manifest.from_dict(json.loads(raw.decode("utf-8")))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise BundleError(f"Manifeste invalide: {exc}") from exc
            _validate_manifest_artifacts(manifest)
            _validate_bundle_layout(archive, manifest)
            if verify:
                _verify_archive(archive, manifest)
            return manifest
    except zipfile.BadZipFile as exc:
        raise BundleError("Le fichier n'est pas un bundle ZIP valide.") from exc


def import_bundle(options: ImportOptions, progress: Progress | None = None) -> Path:
    notify = progress or (lambda _message: None)
    if options.venv_path and options.target:
        raise PyDepotError("--venv et --target ne peuvent pas être utilisés ensemble.")
    manifest = inspect_bundle(options.bundle, verify=False)
    with tempfile.TemporaryDirectory(prefix="pydepot-import-") as temporary:
        root = Path(temporary)
        notify("Extraction et contrôle du bundle…")
        with zipfile.ZipFile(options.bundle.resolve()) as archive:
            _validate_members(archive)
            archive.extractall(root)
        if options.verify:
            _verify_directory(root, manifest)
        expected_lock = "\n".join(_lock_lines(manifest.artifacts)) + "\n"
        lock_path = root / LOCK_NAME
        try:
            bundled_lock = lock_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise BundleError("Le fichier de verrouillage est absent du bundle.") from exc
        if bundled_lock != expected_lock:
            raise BundleError("Le fichier de verrouillage ne correspond pas au manifeste.")

        base_version = python_version(options.python_executable)
        if base_version != manifest.python_version and not options.ignore_python_version:
            raise BundleError(
                f"Bundle prévu pour Python {manifest.python_version}, "
                f"interpréteur sélectionné: {base_version}. "
                "Utilisez le bon Python ou --ignore-python-version."
            )

        executable = options.python_executable
        venv_existed = True
        if options.venv_path:
            venv_path = options.venv_path.resolve()
            venv_existed = venv_path.exists()
            notify(f"Création de l'environnement virtuel: {venv_path}")
            try:
                run_streaming(
                    [options.python_executable, "-m", "venv", str(venv_path)],
                    notify,
                )
            except CommandError:
                if not venv_existed and venv_path.exists():
                    shutil.rmtree(venv_path, ignore_errors=True)
                raise
            executable = str(venv_python(venv_path))

        command = [
            executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--find-links",
            str(root / WHEELHOUSE),
            "--requirement",
            str(root / LOCK_NAME),
        ]
        if options.upgrade:
            command.append("--upgrade")
        if options.target:
            options.target.mkdir(parents=True, exist_ok=True)
            command.extend(["--target", str(options.target.resolve())])
        try:
            run_streaming(command, notify, env=_offline_environment())
            if options.venv_path:
                run_streaming(
                    [executable, "-m", "pip", "check"],
                    notify,
                    env=_offline_environment(),
                )
        except CommandError:
            if options.venv_path and not venv_existed and venv_path.exists():
                shutil.rmtree(venv_path, ignore_errors=True)
            raise
    notify(f"Import terminé avec Python {executable}")
    return Path(executable)


def verify_bundle(bundle: Path) -> Manifest:
    return inspect_bundle(bundle, verify=True)


def _download_command(options: ExportOptions, version: str, destination: Path) -> list[str]:
    command = [
        options.python_executable,
        "-m",
        "pip",
        "download",
        "--dest",
        str(destination),
        "--only-binary=:all:",
        "--python-version",
        version.replace(".", ""),
        "--implementation",
        options.implementation,
    ]
    for platform in options.platforms:
        command.extend(["--platform", platform])
    for abi in options.abis:
        command.extend(["--abi", abi])
    if options.index_url:
        command.extend(["--index-url", options.index_url])
    for url in options.extra_index_urls:
        command.extend(["--extra-index-url", url])
    if options.prerelease:
        command.append("--pre")
    if options.requirements:
        command.extend(["--requirement", str(options.requirements.resolve())])
    command.extend(options.packages)
    return command


def _validate_platform_environment(platforms: list[str]) -> None:
    current = (
        "windows" if os.name == "nt" else "macos" if sys.platform == "darwin" else "linux"
    )
    prefixes = {
        "win": "windows",
        "manylinux": "linux",
        "musllinux": "linux",
        "linux": "linux",
        "macosx": "macos",
    }
    for platform in platforms:
        family = next(
            (value for prefix, value in prefixes.items() if platform.lower().startswith(prefix)),
            None,
        )
        if family and family != current:
            raise PyDepotError(
                f"La plateforme cible {platform!r} ne correspond pas au système d'export "
                f"({current}). pip évalue les marqueurs de plateforme sur le système courant ; "
                "créez ce bundle sur la même famille de système que la cible."
            )


def _read_top_level_requirements(path: Path) -> list[str]:
    result: list[str] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith(("#", "-")):
            result.append(line.split(" #", 1)[0].strip())
    return result


def _artifact_from_file(path: Path) -> Artifact:
    name: str | None = None
    version: str | None = None
    if path.suffix.lower() == ".whl":
        try:
            with zipfile.ZipFile(path) as wheel:
                metadata_names = [
                    item for item in wheel.namelist() if item.endswith(".dist-info/METADATA")
                ]
                if metadata_names:
                    metadata = BytesParser().parsebytes(wheel.read(metadata_names[0]))
                    name = metadata.get("Name")
                    version = metadata.get("Version")
        except (zipfile.BadZipFile, OSError):
            pass
    return Artifact(
        filename=path.name,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        name=name,
        version=version,
    )


def _lock_lines(artifacts: Iterable[Artifact]) -> list[str]:
    pairs: set[tuple[str, str]] = set()
    for artifact in artifacts:
        if not artifact.name or not artifact.version:
            continue
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", artifact.name):
            raise BundleError(f"Nom de distribution invalide: {artifact.name!r}")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.!+_-]*[A-Za-z0-9])?", artifact.version):
            raise BundleError(f"Version de distribution invalide: {artifact.version!r}")
        pairs.add((artifact.name, artifact.version))
    return sorted(f"{name}=={version}" for name, version in pairs)


def _write_bundle_atomically(root: Path, output: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_members(archive: zipfile.ZipFile) -> None:
    seen: set[str] = set()
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
            raise BundleError(f"Chemin dangereux dans le bundle: {member.filename}")
        if member.filename in seen:
            raise BundleError(f"Entrée ZIP dupliquée: {member.filename}")
        seen.add(member.filename)


def _validate_manifest_artifacts(manifest: Manifest) -> None:
    seen: set[str] = set()
    for artifact in manifest.artifacts:
        if (
            not artifact.filename
            or PurePosixPath(artifact.filename).name != artifact.filename
            or "\\" in artifact.filename
        ):
            raise BundleError(f"Nom d'artefact dangereux: {artifact.filename!r}")
        if artifact.filename in seen:
            raise BundleError(f"Artefact dupliqué: {artifact.filename}")
        if artifact.size < 0:
            raise BundleError(f"Taille d'artefact invalide: {artifact.filename}")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact.sha256):
            raise BundleError(f"Empreinte invalide dans le manifeste: {artifact.filename}")
        seen.add(artifact.filename)


def _validate_bundle_layout(archive: zipfile.ZipFile, manifest: Manifest) -> None:
    expected = {MANIFEST_NAME, LOCK_NAME}
    expected.update(f"{WHEELHOUSE}/{artifact.filename}" for artifact in manifest.artifacts)
    files = {item.filename for item in archive.infolist() if not item.is_dir()}
    unexpected = sorted(files - expected)
    missing = sorted(expected - files)
    if unexpected:
        raise BundleError(f"Fichier inattendu dans le bundle: {unexpected[0]}")
    if missing:
        raise BundleError(f"Fichier manquant dans le bundle: {missing[0]}")
    sizes = {
        item.filename: item.file_size for item in archive.infolist() if not item.is_dir()
    }
    for artifact in manifest.artifacts:
        member = f"{WHEELHOUSE}/{artifact.filename}"
        if sizes[member] != artifact.size:
            raise BundleError(f"Taille déclarée invalide: {artifact.filename}")


def _verify_archive(archive: zipfile.ZipFile, manifest: Manifest) -> None:
    names = set(archive.namelist())
    for artifact in manifest.artifacts:
        member = f"{WHEELHOUSE}/{artifact.filename}"
        if member not in names:
            raise BundleError(f"Artefact manquant: {artifact.filename}")
        digest = __import__("hashlib").sha256()
        with archive.open(member) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != artifact.sha256:
            raise BundleError(f"Empreinte invalide: {artifact.filename}")
    expected_lock = "\n".join(_lock_lines(manifest.artifacts)) + "\n"
    try:
        actual_lock = archive.read(LOCK_NAME).decode("utf-8")
    except (KeyError, UnicodeDecodeError) as exc:
        raise BundleError("Le fichier de verrouillage est absent ou invalide.") from exc
    if actual_lock != expected_lock:
        raise BundleError("Le fichier de verrouillage ne correspond pas au manifeste.")


def _verify_directory(root: Path, manifest: Manifest) -> None:
    for artifact in manifest.artifacts:
        path = root / WHEELHOUSE / artifact.filename
        if not path.is_file():
            raise BundleError(f"Artefact manquant: {artifact.filename}")
        if path.stat().st_size != artifact.size or sha256_file(path) != artifact.sha256:
            raise BundleError(f"Artefact altéré: {artifact.filename}")


def _offline_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
        }
    )
    environment.pop("PIP_INDEX_URL", None)
    environment.pop("PIP_EXTRA_INDEX_URL", None)
    return environment
