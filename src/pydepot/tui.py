from __future__ import annotations

import os
import shutil
import sys
import textwrap
from pathlib import Path

from .bundle import ExportOptions, ImportOptions, export_bundle, import_bundle, inspect_bundle
from .errors import PyDepotError
from .portable_python import available_python_versions, install_portable_python
from .util import default_python_executable, default_python_version


ESC = "\x1b["
CYAN = f"{ESC}38;5;45m"
BLUE = f"{ESC}38;5;75m"
MUTED = f"{ESC}38;5;245m"
GREEN = f"{ESC}38;5;42m"
RED = f"{ESC}38;5;203m"
BOLD = f"{ESC}1m"
RESET = f"{ESC}0m"


def run_tui() -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("La TUI nécessite un terminal interactif.", file=sys.stderr)
        return 2
    _enable_ansi_windows()
    selected = 0
    entries = [
        ("Exporter", "Créer un bundle pour une version de Python"),
        ("Importer", "Installer un bundle, avec venv optionnel"),
        ("Inspecter", "Consulter et vérifier un bundle"),
        ("Python portable", "Installer Python avec NuGet (Windows)"),
        ("Quitter", "Fermer PyDepot"),
    ]
    while True:
        _clear()
        _header("GESTIONNAIRE DE DÉPENDANCES HORS LIGNE")
        print(f"  {MUTED}↑/↓ naviguer  ·  Entrée sélectionner  ·  q quitter{RESET}\n")
        for index, (title, subtitle) in enumerate(entries):
            active = index == selected
            pointer = f"{CYAN}›{RESET}" if active else " "
            style = f"{BOLD}{CYAN}" if active else ""
            print(f"  {pointer} {style}{title:<12}{RESET} {MUTED}{subtitle}{RESET}")
        key = _get_key()
        if key in ("q", "Q", "escape"):
            return 0
        if key == "up":
            selected = (selected - 1) % len(entries)
        elif key == "down":
            selected = (selected + 1) % len(entries)
        elif key == "enter":
            if selected == 0:
                _export_wizard()
            elif selected == 1:
                _import_wizard()
            elif selected == 2:
                _inspect_wizard()
            elif selected == 3:
                _portable_python_wizard()
            else:
                return 0


def _export_wizard() -> None:
    _clear()
    _header("NOUVEL EXPORT")
    print(f"  {MUTED}Les versions peuvent être contraintes: requests==2.32.3{RESET}\n")
    packages_text = _ask("Paquets (séparés par des virgules)")
    requirements_text = _ask("Fichier requirements (facultatif)")
    version = _ask("Version Python cible", default_python_version())
    print(
        f"\n  {MUTED}Cet interpréteur doit avoir la même version majeure/mineure que la cible,\n"
        f"  afin que pip résolve correctement les dépendances conditionnelles.{RESET}"
    )
    python_executable = _ask("Interpréteur Python servant à l'export", default_python_executable())
    print(
        f"\n  {MUTED}Tags fréquents : win_amd64 (Windows x64), win_arm64, win32,\n"
        "  manylinux_2_17_x86_64 (Linux x64), manylinux_2_17_aarch64 (Linux ARM64),\n"
        f"  macosx_11_0_x86_64 (macOS Intel), macosx_11_0_arm64 (Apple Silicon).{RESET}"
    )
    platform = _ask("Tag plateforme (vide = machine courante)")
    print(
        f"\n  {MUTED}Il s'agit du nom ou du chemin du fichier à créer. Le format est toujours\n"
        f"  .pybundle ; l'extension est ajoutée automatiquement si nécessaire.{RESET}"
    )
    output = _ask("Nom du fichier de sortie", "dependencies.pybundle")
    packages = [item.strip() for item in packages_text.split(",") if item.strip()]
    options = ExportOptions(
        output=Path(output),
        packages=packages,
        requirements=Path(requirements_text) if requirements_text else None,
        python_version=version,
        platforms=[platform] if platform else [],
        python_executable=python_executable,
    )
    print(f"\n  {MUTED}Non : annule cet export ; aucun bundle ne sera créé.{RESET}")
    if not _confirm("Lancer le téléchargement et créer le bundle ?", default=True):
        _cancelled("Export annulé ; aucun fichier n'a été créé.")
        return
    _run_action(lambda log: export_bundle(options, log), "Bundle créé avec succès")


def _import_wizard() -> None:
    _clear()
    _header("IMPORT HORS LIGNE")
    bundle = _select_bundle()
    create_venv = _confirm("Créer un environnement virtuel ?", default=True)
    venv_path = _ask("Dossier du venv", ".venv") if create_venv else ""
    python_executable = _ask("Interpréteur Python", default_python_executable())
    options = ImportOptions(
        bundle=bundle,
        venv_path=Path(venv_path) if venv_path else None,
        python_executable=python_executable,
    )
    print(
        f"\n  {MUTED}Oui : contrôle les empreintes, puis installe uniquement les wheels\n"
        "  du bundle.\n"
        f"  Non : annule l'import ; aucun fichier n'est extrait ou installé.{RESET}"
    )
    if not _confirm("Vérifier puis installer sans réseau ?", default=True):
        _cancelled("Import annulé ; rien n'a été installé.")
        return
    _run_action(lambda log: import_bundle(options, log), "Import terminé")


def _portable_python_wizard() -> None:
    _clear()
    _header("INSTALLATION DE PYTHON PORTABLE")
    if os.name != "nt":
        print(
            f"  {RED}Cette installation via NuGet est disponible uniquement sous Windows."
            f"{RESET}"
        )
        _pause()
        return

    print(f"  {MUTED}Consultation des versions stables publiées sur NuGet…{RESET}")
    try:
        versions = available_python_versions()
    except PyDepotError as exc:
        print(f"\n  {RED}Erreur: {exc}{RESET}")
        _pause()
        return

    _print_python_versions(versions)
    default = _latest_for_minor(versions, default_python_version()) or versions[0]
    while True:
        version = _ask("Version Python à installer", default)
        if version in versions:
            break
        print(f"  {RED}Cette version stable n'est pas proposée par le paquet NuGet Python.{RESET}")

    destination = Path(
        _ask("Dossier de destination", str(Path.cwd() / f"python-{version}-portable"))
    )
    print(
        f"\n  {MUTED}NuGet sera téléchargé dans ce dossier, puis Python et pip y seront\n"
        "  préparés.\n"
        f"  Non : annule l'installation sans télécharger de fichier.{RESET}"
    )
    if not _confirm("Télécharger et installer ce Python portable ?", default=True):
        _cancelled("Installation annulée ; aucun téléchargement n'a été lancé.")
        return

    executable: Path | None = None

    def install(log) -> None:
        nonlocal executable
        executable = install_portable_python(version, destination, log)
        log(f"Interpréteur prêt: {executable}")

    _run_action(install, "Python portable installé")


def _inspect_wizard() -> None:
    _clear()
    _header("INSPECTION")
    bundle = Path(_ask("Bundle .pybundle"))
    verify = _confirm("Vérifier les empreintes SHA-256 ?", default=True)
    try:
        manifest = inspect_bundle(bundle, verify=verify)
        _clear()
        _header("CONTENU DU BUNDLE")
        print(f"  Python       {CYAN}{manifest.python_version}{RESET}")
        print(f"  Paquets      {CYAN}{len(manifest.artifacts)}{RESET}")
        print(f"  Exécutables  {CYAN}{len(manifest.executables)}{RESET}")
        print(f"  Plateformes  {', '.join(manifest.platforms) or 'courante'}")
        print(f"  Intégrité    {GREEN}{'vérifiée' if verify else 'non vérifiée'}{RESET}\n")
        for artifact in manifest.artifacts:
            print(f"  {artifact.name or artifact.filename:<30} {artifact.version or '?'}")
        for executable in manifest.executables:
            print(f"  {executable.filename:<30} exécutable")
    except PyDepotError as exc:
        print(f"\n  {RED}Erreur: {exc}{RESET}")
    _pause()


def _select_bundle() -> Path:
    bundles = sorted(Path.cwd().glob("*.pybundle"), key=lambda path: path.name.lower())
    if not bundles:
        print(f"  {MUTED}Aucun fichier .pybundle dans {Path.cwd()}{RESET}\n")
        return Path(_ask("Chemin du bundle .pybundle"))

    print(f"  {MUTED}Bundles présents dans {Path.cwd()} :{RESET}")
    for index, path in enumerate(bundles, start=1):
        print(f"  {CYAN}{index:>2}{RESET}  {path.name}")
    while True:
        choice = _ask("Numéro du bundle ou autre chemin", "1")
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(bundles):
                return bundles[index - 1]
            print(f"  {RED}Choisissez un numéro entre 1 et {len(bundles)}.{RESET}")
            continue
        return Path(choice)


def _print_python_versions(versions: list[str]) -> None:
    groups: dict[str, list[str]] = {}
    for version in versions:
        minor = ".".join(version.split(".")[:2])
        groups.setdefault(minor, []).append(version)
    print(f"\n  {MUTED}Versions stables disponibles (plus récentes en premier) :{RESET}")
    width = max(40, shutil.get_terminal_size((100, 24)).columns - 12)
    for minor, values in groups.items():
        lines = textwrap.wrap(", ".join(values), width=width) or [""]
        print(f"  {CYAN}{minor:<5}{RESET} {lines[0]}")
        for line in lines[1:]:
            print(f"        {line}")
    print()


def _latest_for_minor(versions: list[str], minor: str) -> str | None:
    prefix = minor + "."
    return next((version for version in versions if version.startswith(prefix)), None)


def _run_action(action, success: str) -> None:
    print()

    def log(message: str) -> None:
        width = max(30, shutil.get_terminal_size((100, 24)).columns - 8)
        clean = message.replace("\r", " ")
        if len(clean) > width:
            clean = "…" + clean[-(width - 1) :]
        print(f"  {MUTED}│{RESET} {clean}")

    try:
        action(log)
        print(f"\n  {GREEN}✓ {success}{RESET}")
    except PyDepotError as exc:
        print(f"\n  {RED}✗ {exc}{RESET}")
    _pause()


def _cancelled(message: str) -> None:
    print(f"\n  {MUTED}{message}{RESET}")
    _pause()


def _header(subtitle: str) -> None:
    width = min(76, max(48, shutil.get_terminal_size((100, 24)).columns - 4))
    print(f"\n  {BLUE}{'─' * width}{RESET}")
    print(f"  {BOLD}{CYAN}PyDepot{RESET}  {subtitle}")
    print(f"  {BLUE}{'─' * width}{RESET}\n")


def _ask(label: str, default: str = "") -> str:
    suffix = f" {MUTED}[{default}]{RESET}" if default else ""
    value = input(f"  {label}{suffix}\n  {CYAN}›{RESET} ").strip()
    return value or default


def _confirm(label: str, default: bool = False) -> bool:
    hint = "O/n" if default else "o/N"
    answer = input(f"\n  {label} {MUTED}[{hint}]{RESET} ").strip().lower()
    if not answer:
        return default
    return answer in ("o", "oui", "y", "yes")


def _pause() -> None:
    input(f"\n  {MUTED}Entrée pour revenir au menu…{RESET}")


def _clear() -> None:
    print(f"{ESC}2J{ESC}H", end="")


def _get_key() -> str:
    if os.name == "nt":
        import msvcrt

        character = msvcrt.getwch()
        if character in ("\x00", "\xe0"):
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
        return {"\r": "enter", "\x1b": "escape"}.get(character, character)
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        character = sys.stdin.read(1)
        if character == "\x1b":
            sequence = sys.stdin.read(2)
            return {"[A": "up", "[B": "down"}.get(sequence, "escape")
        return {"\r": "enter", "\n": "enter"}.get(character, character)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def _enable_ansi_windows() -> None:
    if os.name == "nt":
        os.system("")
