from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydepot.portable_python import available_python_versions, install_portable_python


class PortablePythonTests(unittest.TestCase):
    def test_available_versions_keeps_supported_stable_releases(self) -> None:
        response = io.BytesIO(
            json.dumps(
                {
                    "versions": [
                        "3.8.10",
                        "3.12.9",
                        "3.12.10",
                        "3.13.0-rc1",
                        "3.13.1",
                        "invalid",
                    ]
                }
            ).encode()
        )
        with mock.patch("pydepot.portable_python.urllib.request.urlopen", return_value=response):
            self.assertEqual(available_python_versions(), ["3.13.1", "3.12.10", "3.12.9"])

    def test_installer_runs_nuget_and_bootstraps_pip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[list[str]] = []

            def capture(command, progress=None, env=None):
                values = list(command)
                calls.append(values)
                if "install" in values and "-OutputDirectory" in values:
                    executable = root / "python" / "tools" / "python.exe"
                    executable.parent.mkdir(parents=True)
                    executable.write_bytes(b"")

            with mock.patch("pydepot.portable_python.os.name", "nt"), mock.patch(
                "pydepot.portable_python._download_atomically"
            ) as download, mock.patch(
                "pydepot.portable_python.run_streaming", side_effect=capture
            ):
                executable = install_portable_python("3.12.10", root)

            self.assertEqual(executable, root / "python" / "tools" / "python.exe")
            download.assert_called_once()
            self.assertEqual(
                calls[0],
                [
                    str(root / "nuget.exe"),
                    "install",
                    "python",
                    "-Version",
                    "3.12.10",
                    "-ExcludeVersion",
                    "-OutputDirectory",
                    str(root),
                ],
            )
            self.assertEqual(calls[1][-1], "-V")
            self.assertEqual(calls[2][-2:], ["ensurepip", "--upgrade"])
            self.assertEqual(calls[3][-4:], ["pip", "install", "--upgrade", "pip"])


if __name__ == "__main__":
    unittest.main()
