"""Exercise release signing using an ephemeral synthetic key, never a user key."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile

from sign_release import (APP, EXPECTED_FINGERPRINT, MAX_METADATA_BYTES, TARGETS, SigningError, clean_environment, gpg,
                          primary_fingerprints, sign_release, validate_archive,
                          verify_signature)


class SigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("gpg") or not shutil.which("gpgconf"):
            raise RuntimeError("GPG and gpgconf are required for the synthetic release-signing tests")
        cls.temporary = tempfile.TemporaryDirectory(prefix="pirate-recovery-sign-test-")
        # unittest skips tearDownClass when setUpClass fails. Registered cleanups
        # still run, and their LIFO order stops the scoped agent before deletion.
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        cls.home = cls.work / "synthetic-keyring"
        cls.home.mkdir(mode=0o700)
        cls.addClassCleanup(cls.stop_test_agent)
        cls.passphrase = "synthetic-only-test-passphrase"
        gpg(cls.home, ["--pinentry-mode", "loopback", "--passphrase-fd", "0",
                       "--quick-generate-key", "Recovery CI Test <ci@example.invalid>",
                       "ed25519", "sign", "1d"], data=(cls.passphrase + "\n").encode())
        cls.fingerprint = primary_fingerprints(gpg(cls.home, ["--with-colons", "--list-keys"]), "pub")[0]
        cls.public_key = gpg(cls.home, ["--armor", "--export", cls.fingerprint])
        private_key = gpg(cls.home, ["--pinentry-mode", "loopback", "--passphrase-fd", "0",
                                    "--armor", "--export-secret-keys", cls.fingerprint],
                          data=(cls.passphrase + "\n").encode())
        cls.private_b64 = base64.b64encode(private_key).decode("ascii")
        cls.public_path = cls.work / "public_key.asc"
        cls.public_path.write_bytes(cls.public_key)

    @classmethod
    def stop_test_agent(cls) -> None:
        executable = shutil.which("gpgconf")
        if executable:
            subprocess.run([executable, "--homedir", str(cls.home), "--kill", "all"],
                           env=clean_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=30, check=False)

    def make_packages(self, directory: Path) -> None:
        directory.mkdir()
        for target in TARGETS:
            stem = f"{APP}-1.0.0-{target}"
            binary = f"{APP}{'.exe' if target.startswith('windows') else ''}"
            members = {
                binary: b"Synthetic executable bytes. Never run this signing fixture.\n",
                "README.md": b"Synthetic release documentation.\n",
                "SECURITY.md": b"Synthetic security documentation.\n",
                "release-signing/README.md": b"Synthetic release signing documentation.\n",
                "LICENSE": b"Synthetic license text.\n",
                "public_key.asc": self.public_key,
                "BUILD-INFO.json": json.dumps({"name": APP, "version": "1.0.0", "target": target,
                                               "self_test": "passed"}).encode(),
                "THIRD_PARTY_LICENSES/index.json": b"[]\n",
                "THIRD_PARTY_LICENSES/PYTHON-LICENSE.txt": b"Synthetic license fixture.\n",
            }
            if target.startswith("windows"):
                with zipfile.ZipFile(directory / f"{stem}.zip", "w") as archive:
                    for name, content in members.items():
                        archive.writestr(f"{stem}/{name}", content)
            else:
                with tarfile.open(directory / f"{stem}.tar.gz", "w:gz") as archive:
                    for name, content in members.items():
                        entry = tarfile.TarInfo(f"{stem}/{name}")
                        entry.size = len(content)
                        entry.mode = 0o644
                        archive.addfile(entry, io.BytesIO(content))

    def test_signs_all_assets_and_verifies_expected_signer(self) -> None:
        unsigned, signed = self.work / "valid-input", self.work / "valid-output"
        self.make_packages(unsigned)
        sign_release(unsigned, signed, "1.0.0", self.public_path, self.private_b64,
                     self.passphrase, expected_fingerprint=self.fingerprint)
        self.assertEqual(len(list(signed.iterdir())), 13)
        verify_signature(self.home, signed / "SHA256SUMS.asc", signed / "SHA256SUMS", self.fingerprint)
        sums = (signed / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        self.assertEqual(len(sums), 6)
        self.assertTrue(any(line.endswith("  public_key.asc") for line in sums))
        package = next(signed.glob("*.zip"))
        verify_signature(self.home, signed / f"{package.name}.asc", package, self.fingerprint)
        with package.open("ab") as handle:
            handle.write(b"tampered")
        with self.assertRaises(SigningError):
            verify_signature(self.home, signed / f"{package.name}.asc", package, self.fingerprint)

    def test_missing_secret_fails_before_signing(self) -> None:
        with self.assertRaisesRegex(SigningError, "secrets are missing"):
            sign_release(self.work / "absent", self.work / "absent-output", "1.0.0",
                         self.public_path, "", self.passphrase, expected_fingerprint=self.fingerprint)

    def test_repository_public_key_fingerprint(self) -> None:
        public_key = (Path(__file__).resolve().parents[1] / "release-signing" / "public_key.asc").read_bytes()
        inspected = gpg(self.home, ["--with-colons", "--import-options", "show-only", "--import"], data=public_key)
        self.assertEqual(primary_fingerprints(inspected, "pub"), [EXPECTED_FINGERPRINT])

    def test_wrong_fingerprint_fails_without_output_assets(self) -> None:
        unsigned, signed = self.work / "wrong-key-input", self.work / "wrong-key-output"
        self.make_packages(unsigned)
        with self.assertRaisesRegex(SigningError, "fingerprint"):
            sign_release(unsigned, signed, "1.0.0", self.public_path, self.private_b64,
                         self.passphrase, expected_fingerprint="0" * 40)
        self.assertFalse(any(signed.iterdir()))

    def test_wrong_passphrase_fails_without_output_assets(self) -> None:
        unsigned, signed = self.work / "wrong-pass-input", self.work / "wrong-pass-output"
        self.make_packages(unsigned)
        with self.assertRaises(SigningError):
            sign_release(unsigned, signed, "1.0.0", self.public_path, self.private_b64,
                         "wrong synthetic passphrase", expected_fingerprint=self.fingerprint)
        self.assertFalse(any(signed.iterdir()))

    def test_archive_refuses_extra_wallet_file(self) -> None:
        unsigned = self.work / "unexpected-file-input"
        self.make_packages(unsigned)
        package = next(unsigned.glob("*.zip"))
        stem = package.stem
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr(f"{stem}/wallet.dat", b"synthetic forbidden archive member")
        with self.assertRaisesRegex(SigningError, "forbidden wallet or secret"):
            validate_archive(package, "1.0.0", "windows-x64", self.public_key)

    def test_archive_refuses_wallet_nested_under_licenses(self) -> None:
        unsigned = self.work / "nested-wallet-input"
        self.make_packages(unsigned)
        package = next(unsigned.glob("*.zip"))
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr(f"{package.stem}/THIRD_PARTY_LICENSES/nested/zero_wallet.json", b"synthetic forbidden data")
        with self.assertRaisesRegex(SigningError, "forbidden wallet or secret"):
            validate_archive(package, "1.0.0", "windows-x64", self.public_key)

    def test_archive_refuses_oversized_metadata(self) -> None:
        package = self.work / "oversized-metadata.zip"
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{APP}-1.0.0-windows-x64/BUILD-INFO.json", b" " * (MAX_METADATA_BYTES + 1))
        with self.assertRaisesRegex(SigningError, "metadata exceeds"):
            validate_archive(package, "1.0.0", "windows-x64", self.public_key)

    def test_archive_refuses_secret_nested_under_licenses(self) -> None:
        unsigned = self.work / "nested-secret-input"
        self.make_packages(unsigned)
        package = next(unsigned.glob("*.zip"))
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr(f"{package.stem}/THIRD_PARTY_LICENSES/nested/secret.asc", b"synthetic forbidden data")
        with self.assertRaisesRegex(SigningError, "forbidden wallet or secret"):
            validate_archive(package, "1.0.0", "windows-x64", self.public_key)

    def test_partial_release_is_refused(self) -> None:
        unsigned = self.work / "incomplete-input"
        unsigned.mkdir()
        with self.assertRaisesRegex(SigningError, "five expected"):
            sign_release(unsigned, self.work / "incomplete-output", "1.0.0", self.public_path,
                         self.private_b64, self.passphrase, expected_fingerprint=self.fingerprint)


if __name__ == "__main__":
    unittest.main(verbosity=2)
