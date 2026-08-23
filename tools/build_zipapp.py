"""Build the dependency-free portable pydepot.pyz executable."""

from __future__ import annotations

import shutil
import tempfile
import zipapp
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "pydepot.pyz"


def main() -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pydepot-build-") as temporary:
        staging = Path(temporary)
        shutil.copytree(ROOT / "src" / "pydepot", staging / "pydepot")
        (staging / "__main__.py").write_text(
            "from pydepot.cli import main\nraise SystemExit(main())\n", encoding="utf-8"
        )
        zipapp.create_archive(
            staging,
            target=OUTPUT,
            interpreter="/usr/bin/env python3",
            compressed=True,
        )
    print(f"Built {OUTPUT}")


if __name__ == "__main__":
    main()

