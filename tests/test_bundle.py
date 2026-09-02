from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from pydepot.bundle import (
    ExportOptions,
    IncludedExecutable,
    ImportOptions,
    export_bundle,
    import_bundle,
    inspect_bundle,
)
from pydepot.errors import BundleError, CommandError, PyDepotError


def _wheel(directory: Path, distribution: str, version: str) -> Path:
    normalized = distribution.replace("-", "_")
    path = directory / f"{normalized}-{version}-py3-none-any.whl"
    metadata = f"Metadata-Version: 2.1\nName: {distribution}\nVersion: {version}\n\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{normalized}-{version}.dist-info/METADATA", metadata)
        archive.writestr(f"{normalized}/__init__.py", "")
    return path


def _fake_download(command, progress=None, env=None):
    destination = Path(command[command.index("--dest") + 1])
    _wheel(destination, "demo-lib", "1.2.3")
    _wheel(destination, "transitive", "4.5.6")


class BundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_bundle(self, version: str = "3.11", include_tool: bool = False) -> Path:
        output = self.root / "demo.pybundle"
        executables = []
        if include_tool:
            tool = self.root / "opencode-source"
            tool.write_bytes(b"linux executable")
            executables.append(IncludedExecutable(tool, "opencode"))
        with mock.patch(
            "pydepot.bundle.run_streaming", side_effect=_fake_download
        ), mock.patch("pydepot.bundle.python_version", return_value="3.11"):
            export_bundle(
                ExportOptions(
                    output=output,
                    packages=["demo-lib>=1"],
                    python_version=version,
                    executables=executables,
                )
            )
        return output

    def test_export_builds_locked_verifiable_bundle(self) -> None:
        output = self.make_bundle("3.11.9")
        manifest = inspect_bundle(output, verify=True)
        self.assertEqual(manifest.python_version, "3.11")
        self.assertEqual(len(manifest.artifacts), 2)
        self.assertEqual(manifest.requested, ["demo-lib>=1"])
        self.assertEqual(manifest.format_version, 2)
        with zipfile.ZipFile(output) as archive:
            lock = archive.read("requirements.lock").decode()
            self.assertIn("demo-lib==1.2.3", lock)
            self.assertIn("transitive==4.5.6", lock)

    def test_export_includes_verifiable_executable(self) -> None:
        output = self.make_bundle(include_tool=True)
        manifest = inspect_bundle(output, verify=True)
        self.assertEqual([item.filename for item in manifest.executables], ["opencode"])
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read("tools/opencode"), b"linux executable")

    def test_modified_executable_is_rejected(self) -> None:
        output = self.make_bundle(include_tool=True)
        altered = self.root / "altered-tool.pybundle"
        with zipfile.ZipFile(output) as source, zipfile.ZipFile(altered, "w") as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "tools/opencode":
                    content = bytes([content[0] ^ 1]) + content[1:]
                target.writestr(info, content)
        with self.assertRaisesRegex(BundleError, "Empreinte invalide"):
            inspect_bundle(altered, verify=True)

    def test_modified_artifact_is_rejected(self) -> None:
        output = self.make_bundle()
        altered = self.root / "altered.pybundle"
        with zipfile.ZipFile(output) as source, zipfile.ZipFile(altered, "w") as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename.startswith("packages/"):
                    content = bytes([content[0] ^ 1]) + content[1:]
                target.writestr(info, content)
        with self.assertRaisesRegex(BundleError, "Empreinte invalide"):
            inspect_bundle(altered, verify=True)

    def test_modified_lock_is_rejected(self) -> None:
        output = self.make_bundle()
        altered = self.root / "altered-lock.pybundle"
        with zipfile.ZipFile(output) as source, zipfile.ZipFile(altered, "w") as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "requirements.lock":
                    content = b"demo @ https://example.invalid/demo.whl\n"
                target.writestr(info, content)
        with self.assertRaisesRegex(BundleError, "verrouillage"):
            inspect_bundle(altered, verify=True)

    def test_import_uses_no_index_and_selected_venv_python(self) -> None:
        output = self.make_bundle()
        calls = []

        def capture(command, progress=None, env=None):
            calls.append((command, env))

        with mock.patch(
            "pydepot.bundle.run_streaming", side_effect=capture
        ), mock.patch("pydepot.bundle.python_version", return_value="3.11"):
            executable = import_bundle(
                ImportOptions(
                    bundle=output,
                    venv_path=self.root / "venv",
                    python_executable="python3.11",
                )
            )
        self.assertEqual(calls[0][0][:3], ["python3.11", "-m", "venv"])
        install, environment = calls[1]
        expected = self.root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.assertEqual(str(executable), str(expected))
        self.assertIn("--no-index", install)
        self.assertIn("--no-deps", install)
        self.assertIn("--find-links", install)
        self.assertEqual(environment["PIP_NO_INDEX"], "1")
        self.assertNotIn("PIP_INDEX_URL", environment)
        self.assertEqual(calls[2][0], [str(expected), "-m", "pip", "check"])

    def test_import_installs_executable_in_venv_bin(self) -> None:
        output = self.make_bundle(include_tool=True)
        venv = self.root / "venv-with-tool"

        with mock.patch("pydepot.bundle.run_streaming"), mock.patch(
            "pydepot.bundle.python_version", return_value="3.11"
        ):
            import_bundle(
                ImportOptions(
                    bundle=output,
                    venv_path=venv,
                    python_executable="python3.11",
                )
            )

        tools = venv / ("Scripts" if os.name == "nt" else "bin")
        self.assertEqual((tools / "opencode").read_bytes(), b"linux executable")
        if os.name != "nt":
            self.assertTrue((tools / "opencode").stat().st_mode & 0o111)

    def test_existing_different_executable_requires_upgrade(self) -> None:
        output = self.make_bundle(include_tool=True)
        tools = self.root / "tools"
        tools.mkdir()
        (tools / "opencode").write_bytes(b"older")

        with mock.patch("pydepot.bundle.run_streaming"), mock.patch(
            "pydepot.bundle.python_version", return_value="3.11"
        ):
            with self.assertRaisesRegex(PyDepotError, "--upgrade"):
                import_bundle(
                    ImportOptions(
                        bundle=output,
                        python_executable="python3.11",
                        tools_dir=tools,
                    )
                )

    def test_tool_bundle_requires_destination_before_installing_packages(self) -> None:
        output = self.make_bundle(include_tool=True)
        with mock.patch("pydepot.bundle.run_streaming") as run:
            with self.assertRaisesRegex(PyDepotError, "--venv"):
                import_bundle(
                    ImportOptions(bundle=output, python_executable="python3.11")
                )
        run.assert_not_called()

    def test_export_rejects_different_resolver_python_version(self) -> None:
        with mock.patch("pydepot.bundle.python_version", return_value="3.14"):
            with self.assertRaisesRegex(PyDepotError, "même version majeure/mineure"):
                export_bundle(
                    ExportOptions(
                        output=self.root / "bad.pybundle",
                        packages=["scrapy"],
                        python_version="3.12",
                    )
                )

    def test_cross_platform_export_requires_explicit_opt_in(self) -> None:
        with mock.patch("pydepot.bundle.python_version", return_value="3.11"), mock.patch(
            "pydepot.bundle.os.name", "nt"
        ):
            with self.assertRaisesRegex(PyDepotError, "--allow-cross-platform"):
                export_bundle(
                    ExportOptions(
                        output=self.root / "linux.pybundle",
                        packages=["demo-lib"],
                        python_version="3.11",
                        platforms=["manylinux_2_17_x86_64"],
                    )
                )

    def test_cross_platform_export_can_be_acknowledged(self) -> None:
        messages: list[str] = []
        with mock.patch(
            "pydepot.bundle.run_streaming", side_effect=_fake_download
        ), mock.patch("pydepot.bundle.python_version", return_value="3.11"), mock.patch(
            "pydepot.bundle.os.name", "nt"
        ):
            manifest = export_bundle(
                ExportOptions(
                    output=self.root / "linux.pybundle",
                    packages=["demo-lib"],
                    python_version="3.11",
                    platforms=["manylinux_2_17_x86_64"],
                    allow_cross_platform=True,
                ),
                progress=messages.append,
            )
        self.assertEqual(manifest.platforms, ["manylinux_2_17_x86_64"])
        self.assertTrue(any("résolution croisée" in message for message in messages))

    def test_failed_venv_creation_cleans_new_partial_directory(self) -> None:
        output = self.make_bundle()
        venv_path = self.root / "partial-venv"

        def fail_after_creating(command, progress=None, env=None):
            venv_path.mkdir()
            raise CommandError("venv failed")

        with mock.patch(
            "pydepot.bundle.run_streaming", side_effect=fail_after_creating
        ), mock.patch("pydepot.bundle.python_version", return_value="3.11"):
            with self.assertRaises(CommandError):
                import_bundle(
                    ImportOptions(
                        bundle=output,
                        venv_path=venv_path,
                        python_executable="python3.11",
                    )
                )
        self.assertFalse(venv_path.exists())

    def test_rejects_unsafe_archive_member(self) -> None:
        bundle = self.root / "unsafe.pybundle"
        with zipfile.ZipFile(bundle, "w") as archive:
            archive.writestr("../escape", b"bad")
            archive.writestr("manifest.json", json.dumps({"format_version": 1}))
        with self.assertRaisesRegex(BundleError, "Chemin dangereux"):
            inspect_bundle(bundle)

    def test_rejects_unexpected_archive_member(self) -> None:
        output = self.make_bundle()
        altered = self.root / "extra.pybundle"
        with zipfile.ZipFile(output) as source, zipfile.ZipFile(altered, "w") as target:
            for info in source.infolist():
                target.writestr(info, source.read(info.filename))
            target.writestr("extra.txt", b"not expected")
        with self.assertRaisesRegex(BundleError, "Fichier inattendu"):
            inspect_bundle(altered)


if __name__ == "__main__":
    unittest.main()
