from __future__ import annotations

import hashlib
import locale
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

from .errors import CommandError, PyDepotError


Progress = Callable[[str], None]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_python_version(value: str) -> str:
    match = re.fullmatch(r"\s*(\d+)\.(\d+)(?:\.\d+)?\s*", value)
    if not match:
        raise PyDepotError("La version Python doit être au format 3.11 ou 3.11.9.")
    return f"{int(match.group(1))}.{int(match.group(2))}"


def python_version(executable: str) -> str:
    command = [
        executable,
        "-c",
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CommandError(f"Impossible d'interroger Python ({executable}): {exc}") from exc
    return normalize_python_version(result.stdout.strip())


def run_streaming(
    command: Sequence[str], progress: Progress | None = None, env: dict[str, str] | None = None
) -> None:
    notify = progress or (lambda _message: None)
    display = " ".join(_quote_for_display(part) for part in command)
    notify(f"$ {display}")
    try:
        process = subprocess.Popen(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="replace",
            env=env,
        )
    except OSError as exc:
        raise CommandError(f"Impossible de lancer la commande: {exc}") from exc
    assert process.stdout is not None
    for line in process.stdout:
        notify(line.rstrip())
    code = process.wait()
    if code:
        raise CommandError(f"La commande a échoué avec le code {code}.")


def _quote_for_display(value: str) -> str:
    if not value or any(character.isspace() for character in value):
        return repr(value)
    return value


def venv_python(directory: Path) -> Path:
    if os.name == "nt":
        return directory / "Scripts" / "python.exe"
    return directory / "bin" / "python"


def default_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def default_python_executable() -> str:
    """Return a runnable interpreter, including for some embedded distributions."""
    configured = Path(sys.executable)
    if configured.is_file():
        return str(configured)
    names = ("python.exe",) if os.name == "nt" else ("python3", "python")
    for parent in (configured.parent, Path(sys.prefix).parent):
        for name in names:
            candidate = parent / name
            if candidate.is_file():
                return str(candidate)
    return sys.executable
