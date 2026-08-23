from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydepot.tui import _confirm, _latest_for_minor, _select_bundle


class TuiTests(unittest.TestCase):
    def test_confirmation_accepts_empty_answer_when_yes_is_default(self) -> None:
        with mock.patch("builtins.input", return_value=""):
            self.assertTrue(_confirm("Continuer ?", default=True))

    def test_bundle_selection_lists_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "a.pybundle"
            second = root / "b.pybundle"
            first.write_bytes(b"")
            second.write_bytes(b"")
            with mock.patch("pydepot.tui.Path.cwd", return_value=root), mock.patch(
                "pydepot.tui._ask", return_value="2"
            ):
                self.assertEqual(_select_bundle(), second)

    def test_latest_version_for_current_minor(self) -> None:
        versions = ["3.14.2", "3.14.1", "3.13.5"]
        self.assertEqual(_latest_for_minor(versions, "3.14"), "3.14.2")
        self.assertIsNone(_latest_for_minor(versions, "3.12"))


if __name__ == "__main__":
    unittest.main()
