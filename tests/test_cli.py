from __future__ import annotations

import unittest

from pydepot.cli import build_parser


class CliTests(unittest.TestCase):
    def test_export_arguments(self) -> None:
        args = build_parser().parse_args(
            [
                "export",
                "requests==2.32.3",
                "-o",
                "web.pybundle",
                "--python-version",
                "3.11",
                "--platform",
                "win_amd64",
                "--include-executable",
                "downloads/opencode=opencode",
                "--allow-cross-platform",
            ]
        )
        self.assertEqual(args.command, "export")
        self.assertEqual(args.packages, ["requests==2.32.3"])
        self.assertEqual(args.platform, ["win_amd64"])
        self.assertEqual(args.include_executable, ["downloads/opencode=opencode"])
        self.assertTrue(args.allow_cross_platform)

    def test_import_alias(self) -> None:
        args = build_parser().parse_args(
            ["install", "web.pybundle", "--venv", ".venv", "--tools-dir", "tools"]
        )
        self.assertEqual(args.command, "install")
        self.assertEqual(str(args.venv), ".venv")
        self.assertEqual(str(args.tools_dir), "tools")


if __name__ == "__main__":
    unittest.main()
