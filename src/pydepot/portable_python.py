from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .errors import CommandError, PyDepotError
from .util import Progress, run_streaming


PYTHON_VERSIONS_URL = "https://api.nuget.org/v3-flatcontainer/python/index.json"
NUGET_EXE_URL = "https://dist.nuget.org/win-x86-commandline/latest/nuget.exe"


def available_python_versions() -> list[str]:
    """Return stable NuGet Python versions supported by PyDepot, newest first."""
    try:
        with urllib.request.urlopen(PYTHON_VERSIONS_URL, timeout=30) as response:
            payload = json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise PyDepotError(
            f"Impossible de consulter les versions Python sur NuGet: {exc}"
        ) from exc

    versions: list[tuple[tuple[int, ...], str]] = []
    for raw in payload.get("versions", []):
        value = str(raw)
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", value):
            continue
        parts = tuple(int(part) for part in value.split("."))
        if parts[:2] < (3, 9):
            continue
        versions.append((parts, value))
    if not versions:
        raise PyDepotError("NuGet n'a retourné aucune version Python stable compatible.")
    return [value for _parts, value in sorted(versions, reverse=True)]


def install_portable_python(
    version: str, destination: Path, progress: Progress | None = None
) -> Path:
    """Install the NuGet Python package and bootstrap pip in a destination folder."""
    if os.name != "nt":
        raise PyDepotError("L'installation de Python portable via NuGet est réservée à Windows.")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", version):
        raise PyDepotError(f"Version Python NuGet invalide: {version!r}")

    notify = progress or (lambda _message: None)
    root = destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    nuget = root / "nuget.exe"
    notify(f"Téléchargement de NuGet dans {nuget}…")
    _download_atomically(NUGET_EXE_URL, nuget)

    run_streaming(
        [
            str(nuget),
            "install",
            "python",
            "-Version",
            version,
            "-ExcludeVersion",
            "-OutputDirectory",
            str(root),
        ],
        notify,
    )

    executable = root / "python" / "tools" / "python.exe"
    if not executable.is_file():
        raise CommandError(f"Python n'a pas été créé à l'emplacement attendu: {executable}")
    run_streaming([str(executable), "-V"], notify)
    run_streaming([str(executable), "-m", "ensurepip", "--upgrade"], notify)
    run_streaming([str(executable), "-m", "pip", "install", "--upgrade", "pip"], notify)
    return executable


def _download_atomically(url: str, destination: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        try:
            response = urllib.request.urlopen(url, timeout=120)
            with response, temporary.open("wb") as stream:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
        except (OSError, urllib.error.URLError) as exc:
            raise PyDepotError(f"Impossible de télécharger NuGet: {exc}") from exc
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
