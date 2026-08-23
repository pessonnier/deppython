from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .bundle import (
    ExportOptions,
    ImportOptions,
    export_bundle,
    import_bundle,
    inspect_bundle,
    verify_bundle,
)
from .errors import PyDepotError
from .util import default_python_executable, default_python_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pydepot",
        description="Crée et importe des bundles de dépendances Python hors ligne.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    export = subparsers.add_parser("export", help="Télécharger un bundle portable")
    export.add_argument("packages", nargs="*", help="Paquets (ex: requests==2.32.3)")
    export.add_argument("-r", "--requirements", type=Path, help="Fichier requirements source")
    export.add_argument("-o", "--output", type=Path, required=True, help="Bundle .pybundle")
    export.add_argument(
        "--python-version",
        default=default_python_version(),
        help="Version Python cible, ex: 3.11",
    )
    export.add_argument(
        "--platform",
        action="append",
        default=[],
        help="Tag plateforme pip, répétable (ex: win_amd64, manylinux_2_17_x86_64)",
    )
    export.add_argument("--implementation", default="cp", help="Implémentation (cp, pp…)")
    export.add_argument("--abi", action="append", default=[], help="Tag ABI, répétable")
    export.add_argument(
        "--python",
        default=default_python_executable(),
        help="Python servant à résoudre (même version majeure/mineure que la cible)",
    )
    export.add_argument("--index-url", help="Index de paquets principal")
    export.add_argument(
        "--extra-index-url", action="append", default=[], help="Index additionnel, répétable"
    )
    export.add_argument("--pre", action="store_true", help="Autoriser les préversions")
    export.add_argument("--json", action="store_true", help="Afficher le manifeste en JSON")

    install = subparsers.add_parser(
        "import", aliases=["install"], help="Installer un bundle sans accès réseau"
    )
    install.add_argument("bundle", type=Path, help="Bundle .pybundle")
    destination = install.add_mutually_exclusive_group()
    destination.add_argument("--venv", type=Path, help="Créer et installer dans ce venv")
    destination.add_argument("--target", type=Path, help="Installer dans ce dossier")
    install.add_argument(
        "--python",
        default=default_python_executable(),
        help="Interpréteur cible ou base du venv",
    )
    install.add_argument("--no-verify", action="store_true", help="Ignorer les empreintes SHA-256")
    install.add_argument(
        "--ignore-python-version", action="store_true", help="Ignorer le contrôle major.minor"
    )
    install.add_argument("--upgrade", action="store_true", help="Mettre à niveau les paquets présents")

    inspect = subparsers.add_parser("inspect", help="Afficher le contenu d'un bundle")
    inspect.add_argument("bundle", type=Path)
    inspect.add_argument("--verify", action="store_true", help="Vérifier toutes les empreintes")
    inspect.add_argument("--json", action="store_true", help="Sortie JSON")

    verify = subparsers.add_parser("verify", help="Contrôler l'intégrité d'un bundle")
    verify.add_argument("bundle", type=Path)

    subparsers.add_parser("tui", help="Ouvrir l'interface plein écran")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        if sys.stdin.isatty() and sys.stdout.isatty():
            args.command = "tui"
        else:
            parser.print_help()
            return 0

    try:
        if args.command == "export":
            manifest = export_bundle(
                ExportOptions(
                    output=args.output,
                    packages=args.packages,
                    requirements=args.requirements,
                    python_version=args.python_version,
                    implementation=args.implementation,
                    platforms=args.platform,
                    abis=args.abi,
                    index_url=args.index_url,
                    extra_index_urls=args.extra_index_url,
                    prerelease=args.pre,
                    python_executable=args.python,
                ),
                progress=_progress,
            )
            if args.json:
                print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"✓ {len(manifest.artifacts)} artefact(s) exporté(s).")
            return 0

        if args.command in ("import", "install"):
            executable = import_bundle(
                ImportOptions(
                    bundle=args.bundle,
                    venv_path=args.venv,
                    python_executable=args.python,
                    target=args.target,
                    verify=not args.no_verify,
                    ignore_python_version=args.ignore_python_version,
                    upgrade=args.upgrade,
                ),
                progress=_progress,
            )
            print(f"✓ Dépendances disponibles via {executable}")
            return 0

        if args.command == "inspect":
            manifest = inspect_bundle(args.bundle, verify=args.verify)
            if args.json:
                print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))
            else:
                _print_manifest(manifest, args.verify)
            return 0

        if args.command == "verify":
            manifest = verify_bundle(args.bundle)
            print(f"✓ Bundle intègre: {len(manifest.artifacts)} artefact(s) vérifié(s).")
            return 0

        if args.command == "tui":
            from .tui import run_tui

            return run_tui()
    except KeyboardInterrupt:
        print("\nOpération annulée.", file=sys.stderr)
        return 130
    except PyDepotError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1
    return 0


def _progress(message: str) -> None:
    print(f"  {message}", file=sys.stderr, flush=True)


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _print_manifest(manifest, verified: bool) -> None:
    size = sum(item.size for item in manifest.artifacts)
    platforms = ", ".join(manifest.platforms) if manifest.platforms else "plateforme courante"
    print(f"Bundle PyDepot v{manifest.format_version}")
    print(f"Créé le       : {manifest.created_at}")
    print(f"Python        : {manifest.python_version} ({manifest.implementation})")
    print(f"Plateforme(s) : {platforms}")
    print(f"Demandé       : {', '.join(manifest.requested)}")
    print(f"Contenu       : {len(manifest.artifacts)} artefact(s), {_human_size(size)}")
    print(f"Intégrité     : {'vérifiée' if verified else 'non vérifiée'}")
    print()
    width = max((len(item.name or item.filename) for item in manifest.artifacts), default=6)
    for item in manifest.artifacts:
        label = item.name or item.filename
        version = item.version or "?"
        print(f"  {label:<{width}}  {version:>12}  {_human_size(item.size):>9}")


def _human_size(value: int) -> str:
    amount = float(value)
    for unit in ("o", "Kio", "Mio", "Gio"):
        if amount < 1024 or unit == "Gio":
            return f"{amount:.1f} {unit}" if unit != "o" else f"{int(amount)} {unit}"
        amount /= 1024
    return f"{value} o"


if __name__ == "__main__":
    raise SystemExit(main())
