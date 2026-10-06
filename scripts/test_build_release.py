"""Check release license collection with public fixtures and installed dependencies."""

from __future__ import annotations

from email.message import Message
import importlib.metadata
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import build_release
from sign_release import SigningError, validate_archive


class LicenseCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="pirate-recovery-license-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.installed = self.work / "installed"
        self.installed.mkdir()
        self.output_count = 0

    def distribution(self, entries: list[Path], license_files: tuple[str, ...] = ()) -> SimpleNamespace:
        for entry in entries:
            source = self.installed / entry
            source.resolve().relative_to(self.work.resolve())
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"Public synthetic license fixture.\n")
        metadata = Message()
        metadata["License-Expression"] = "MIT"
        for name in license_files:
            metadata["License-File"] = name
        return SimpleNamespace(version="1.2.3", files=entries,
                               metadata=metadata,
                               locate_file=lambda entry: self.installed / entry)

    def collect_fixture(self, distribution: SimpleNamespace) -> Path:
        self.output_count += 1
        destination = self.work / f"collected-{self.output_count}"
        with patch.object(build_release, "locked_packages", return_value={"fixture"}), \
                patch.object(build_release.importlib.metadata, "distribution",
                             return_value=distribution):
            build_release.collect_licenses(destination)
        return destination

    def test_legal_documents_retained_but_license_modules_and_caches_excluded(self) -> None:
        documents = [Path("fixture.dist-info/licenses") / name for name in
                     ("LICENSE", "LICENSE.txt", "LICENSE.rst", "LICENSE.APACHE",
                      "COPYING", "NOTICE", "AUTHORS", "LiCeNcE")]
        code = [Path(prefix) / name for prefix in
                ("packaging/licenses", "pip/_vendor/packaging/licenses",
                 "setuptools/_vendor/packaging/licenses") for name in
                ("__init__.py", "_spdx.py", "__pycache__/__init__.cpython-313.pyc",
                 "__pycache__/_spdx.cpython-313.pyc")]
        code.extend(Path(name) for name in ("licenses.py", "LICENSE.py", "notice.py"))
        destination = self.collect_fixture(self.distribution(documents + code))
        records = json.loads((destination / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(records, [{"name": "fixture", "version": "1.2.3", "license": "MIT",
                                    "files": [entry.as_posix() for entry in documents]}])
        package = destination / "fixture-1.2.3"
        self.assertEqual({path.relative_to(package) for path in package.rglob("*") if path.is_file()},
                         set(documents))
        for entry in documents:
            self.assertEqual((package / entry).read_bytes(), b"Public synthetic license fixture.\n")
        self.assertTrue((destination / "PYTHON-LICENSE.txt").is_file())

    def test_declared_license_files_are_retained_only_under_distribution_metadata(self) -> None:
        documents = [Path("fixture.dist-info/licenses/MIT.txt"),
                     Path("fixture.dist-info/licenses/Apache-2.0.txt"),
                     Path("fixture.dist-info/legal.txt")]
        excluded = [Path("fixture.dist-info/licenses/BSD-3-Clause.txt"),
                    Path("packaging/licenses/MIT.txt"),
                    Path("fixture.dist-info/licenses/LICENSE.py")]
        distribution = self.distribution(documents + excluded,
                                         ("MIT.txt", "Apache-2.0.txt", "legal.txt", "LICENSE.py"))
        destination = self.collect_fixture(distribution)
        records = json.loads((destination / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(records[0]["files"], [entry.as_posix() for entry in documents])
        package = destination / "fixture-1.2.3"
        self.assertEqual({path.relative_to(package) for path in package.rglob("*") if path.is_file()},
                         set(documents))

    def test_distribution_without_genuine_license_document_fails(self) -> None:
        for entries in ([], [Path("packaging/licenses/__init__.py"), Path("licenses.py")]):
            with self.subTest(entries=entries):
                with self.assertRaisesRegex(RuntimeError, "no bundled license text"):
                    self.collect_fixture(self.distribution(entries))

    def test_unsafe_license_entries_are_skipped(self) -> None:
        document = Path("fixture.dist-info/licenses/LICENSE")
        linked = Path("linked/LICENSE")
        unsafe = [Path("../outside/LICENSE"), self.work / "absolute" / "LICENSE", linked]
        distribution = self.distribution([document, *unsafe])
        original_is_symlink = Path.is_symlink
        with patch.object(Path, "is_symlink", autospec=True,
                          side_effect=lambda path: path == self.installed / linked or original_is_symlink(path)):
            destination = self.collect_fixture(distribution)
        records = json.loads((destination / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(records[0]["files"], [document.as_posix()])
        package = destination / "fixture-1.2.3"
        self.assertEqual([path.relative_to(package) for path in package.rglob("*") if path.is_file()],
                         [document])

    def test_installed_locked_dependencies_collect_documents_without_code_or_cache(self) -> None:
        installed = {}
        for name in build_release.locked_packages(build_release.ROOT / "requirements-build.lock"):
            try:
                installed[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                continue  # Another platform's marked dependencies are absent.
        self.assertIn("packaging", installed)
        destination = self.work / "installed-licenses"
        build_release.collect_licenses(destination)
        records = json.loads((destination / "index.json").read_text(encoding="utf-8"))
        self.assertEqual({record["name"]: record["version"] for record in records}, installed)
        indexed = set()
        for record in records:
            self.assertTrue(record["files"], record["name"])
            for entry in record["files"]:
                relative = Path(f'{record["name"]}-{record["version"]}') / entry
                indexed.add(relative)
                with self.subTest(package=record["name"], entry=entry):
                    self.assertNotIn("__pycache__", relative.parts)
                    self.assertNotIn(relative.suffix.lower(), {".py", ".pyi", ".pyc", ".pyo",
                                                              ".pyd", ".so", ".dll"})
                    self.assertGreater((destination / relative).stat().st_size, 0)
        copied = {path.relative_to(destination) for path in destination.rglob("*") if path.is_file()}
        self.assertEqual(copied, indexed | {Path("index.json"), Path("PYTHON-LICENSE.txt")})

    def test_real_license_tree_passes_archive_validation_but_cache_files_are_rejected(self) -> None:
        public_key = b"Public synthetic release key fixture.\n"
        for target, windows in (("windows-x64", True), ("linux-x64", False)):
            with self.subTest(target=target):
                stage = self.work / f"{build_release.APP}-1.0.0-{target}"
                stage.mkdir()
                binary = build_release.APP + (".exe" if windows else "")
                files = {binary: b"Public synthetic executable fixture; never executed.\n",
                         "README.md": b"Public synthetic documentation.\n",
                         "SECURITY.md": b"Public synthetic documentation.\n",
                         "LICENSE": b"Public synthetic license fixture.\n",
                         "public_key.asc": public_key,
                         "release-signing/README.md": b"Public synthetic documentation.\n",
                         "BUILD-INFO.json": json.dumps({"name": build_release.APP,
                                                        "version": "1.0.0", "target": target,
                                                        "self_test": "passed"}).encode()}
                for name, content in files.items():
                    path = stage / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                build_release.collect_licenses(stage / "THIRD_PARTY_LICENSES")
                suffix = ".zip" if windows else ".tar.gz"
                package = self.work / f"{stage.name}{suffix}"
                build_release.make_archive(stage, package, windows)
                validate_archive(package, "1.0.0", target, public_key)
                cache = (stage / "THIRD_PARTY_LICENSES" / "fixture-1.2.3" / "packaging" /
                         "licenses" / "__pycache__" / "_spdx.cpython-313.pyc")
                cache.parent.mkdir(parents=True)
                cache.write_bytes(b"Public synthetic cache fixture.\n")
                malformed = self.work / f"malformed-{stage.name}{suffix}"
                build_release.make_archive(stage, malformed, windows)
                with self.assertRaisesRegex(SigningError, "forbidden wallet or secret filename"):
                    validate_archive(malformed, "1.0.0", target, public_key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
