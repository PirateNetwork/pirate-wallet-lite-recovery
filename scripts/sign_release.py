"""Sign a complete release in an isolated keyring; never use the user's keyring."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile


APP = "pirate-wallet-lite-recovery"
EXPECTED_FINGERPRINT = "E4FB2399AECCF9B9447DED472CE65343401553A6"
TARGETS = ("windows-x64", "linux-x64", "linux-arm64", "macos-x64", "macos-arm64")
SECRET_VARIABLES = ("LINUX_GPG_PRIVATE_KEY_B64", "LINUX_GPG_PASSPHRASE")
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2048
FORBIDDEN_EXTENSIONS = {".dat", ".key", ".pem", ".gpg", ".asc", ".p12", ".pfx", ".wallet", ".keystore", ".db", ".sqlite"}


class SigningError(RuntimeError):
    pass


def clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (*SECRET_VARIABLES, "GNUPGHOME", "GPG_AGENT_INFO"):
        environment.pop(name, None)
    return environment


def gpg(home: Path, arguments: list[str], *, data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["gpg", "--no-options", "--homedir", str(home), "--batch", "--no-tty",
         "--no-auto-key-retrieve", *arguments],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=clean_environment(), timeout=120, check=False,
    )
    if result.returncode:
        # GPG's raw diagnostics can include key identities or secret input details.
        raise SigningError("GPG operation failed; verify the configured key and passphrase")
    return result.stdout


def primary_fingerprints(colons: bytes, kind: str) -> list[str]:
    fingerprints = []
    awaiting_primary = False
    for line in colons.decode("utf-8").splitlines():
        fields = line.split(":")
        if fields[0] == kind:
            awaiting_primary = True
        elif fields[0] in {"pub", "sec", "sub", "ssb"}:
            awaiting_primary = False
        elif fields[0] == "fpr" and awaiting_primary:
            fingerprints.append(fields[9].upper())
            awaiting_primary = False
    return fingerprints


def verify_signature(home: Path, signature: Path, payload: Path, expected: str) -> None:
    status = gpg(home, ["--status-fd", "1", "--verify", str(signature), str(payload)])
    valid = False
    for line in status.decode("utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[:2] == ["[GNUPG:]", "VALIDSIG"]:
            valid |= expected in {fields[2].upper(), fields[-1].upper()}
    if not valid:
        raise SigningError("signature did not verify against the expected primary fingerprint")


def validate_archive(package: Path, version: str, target: str, public_key: bytes) -> None:
    if package.stat().st_size > MAX_ARCHIVE_BYTES:
        raise SigningError(f"archive exceeds the release size limit: {package.name}")
    stem = f"{APP}-{version}-{target}"
    binary = f"{APP}{'.exe' if target.startswith('windows') else ''}"
    required = {binary, "README.md", "SECURITY.md", "LICENSE", "public_key.asc", "BUILD-INFO.json",
                "release-signing/README.md",
                "THIRD_PARTY_LICENSES/index.json", "THIRD_PARTY_LICENSES/PYTHON-LICENSE.txt"}
    members: dict[str, bytes | None] = {}
    total_bytes = 0

    def accept(name: str, is_regular: bool, size: int, content: bytes | None) -> None:
        nonlocal total_bytes
        path = PurePosixPath(name)
        if len(name) > 512 or "\\" in name or path.is_absolute() or ".." in path.parts or len(path.parts) < 2 or path.parts[0] != stem:
            raise SigningError(f"invalid archive layout: {package.name}")
        relative = PurePosixPath(*path.parts[1:]).as_posix()
        for part in path.parts[1:]:
            lower = part.lower()
            if relative in {binary, "public_key.asc"}:
                continue
            if (PurePosixPath(lower).suffix in FORBIDDEN_EXTENSIONS or
                    any(marker in lower for marker in ("wallet", "private", "secret")) or lower.startswith(".env") or
                    lower in {".env", ".git", ".venv", "credentials", "__pycache__"}):
                raise SigningError(f"archive contains a forbidden wallet or secret filename: {package.name}")
        if not is_regular or relative in members:
            raise SigningError(f"archive has duplicate or nonregular entries: {package.name}")
        if relative not in required and not relative.startswith("THIRD_PARTY_LICENSES/"):
            raise SigningError(f"unexpected archive member: {package.name}")
        if len(members) >= MAX_ARCHIVE_ENTRIES or size < 0:
            raise SigningError(f"archive exceeds the member count limit: {package.name}")
        if relative != binary and size > MAX_METADATA_BYTES:
            raise SigningError(f"archive metadata exceeds the size limit: {package.name}")
        total_bytes += size
        if total_bytes > MAX_ARCHIVE_BYTES:
            raise SigningError(f"archive exceeds the uncompressed size limit: {package.name}")
        members[relative] = content

    if target.startswith("windows"):
        with zipfile.ZipFile(package) as archive:
            for entry in archive.infolist():
                mode = stat.S_IFMT(entry.external_attr >> 16)
                regular = not entry.is_dir() and mode in {0, stat.S_IFREG}
                if entry.file_size > MAX_METADATA_BYTES and entry.filename.endswith(("/BUILD-INFO.json", "/public_key.asc")):
                    raise SigningError(f"archive metadata exceeds the size limit: {package.name}")
                content = archive.read(entry) if entry.filename.endswith(("/BUILD-INFO.json", "/public_key.asc")) else None
                accept(entry.filename, regular, entry.file_size, content)
    else:
        with tarfile.open(package, "r:gz") as archive:
            for entry in archive:
                content = None
                if entry.isfile() and entry.name.endswith(("/BUILD-INFO.json", "/public_key.asc")):
                    if entry.size > MAX_METADATA_BYTES:
                        raise SigningError(f"archive metadata exceeds the size limit: {package.name}")
                    handle = archive.extractfile(entry)
                    assert handle is not None
                    content = handle.read()
                accept(entry.name, entry.isfile(), entry.size, content)
    if not required.issubset(members):
        raise SigningError(f"archive is missing required release files: {package.name}")
    if members["public_key.asc"] != public_key:
        raise SigningError(f"archive public key differs from the trusted release key: {package.name}")
    metadata = json.loads(members["BUILD-INFO.json"] or b"{}")
    if (metadata.get("name"), metadata.get("version"), metadata.get("target"), metadata.get("self_test")) != (APP, version, target, "passed"):
        raise SigningError(f"invalid package build metadata: {package.name}")


def sign_release(input_dir: Path, output_dir: Path, version: str, public_key_path: Path,
                 private_key_b64: str, passphrase: str, *,
                 expected_fingerprint: str = EXPECTED_FINGERPRINT) -> None:
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise SigningError("invalid release version")
    expected_fingerprint = expected_fingerprint.upper()
    if not re.fullmatch(r"[A-F0-9]{40}", expected_fingerprint):
        raise SigningError("expected fingerprint must be a full 40-character fingerprint")
    if not private_key_b64 or not passphrase:
        raise SigningError("required release signing secrets are missing")
    if not shutil.which("gpg") or not shutil.which("gpgconf"):
        raise SigningError("GPG and gpgconf are required for isolated signing and cleanup")
    if len(private_key_b64) > 2 * 1024 * 1024:
        raise SigningError("invalid signing key size")
    if "\n" in passphrase or "\r" in passphrase:
        raise SigningError("GPG passphrase must not contain a newline")
    try:
        private_key = base64.b64decode(private_key_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SigningError("signing key secret is not valid base64") from exc
    if not private_key or len(private_key) > 1024 * 1024:
        raise SigningError("invalid signing key size")
    input_dir, output_dir = input_dir.resolve(), output_dir.resolve()
    if input_dir == output_dir or output_dir in input_dir.parents or input_dir in output_dir.parents:
        raise SigningError("signing input and output directories must be separate")
    public_key = public_key_path.read_bytes()
    if b"PRIVATE KEY" in public_key or b"PUBLIC KEY BLOCK" not in public_key:
        raise SigningError("release key file must contain only a public key")
    expected_names = {f"{APP}-{version}-{target}{'.zip' if target.startswith('windows') else '.tar.gz'}": target
                      for target in TARGETS}
    if {path.name for path in input_dir.iterdir()} != set(expected_names):
        raise SigningError("release must contain exactly the five expected native packages")
    for name, target in expected_names.items():
        package = input_dir / name
        if not package.is_file() or package.is_symlink():
            raise SigningError("release packages must be regular files")
        validate_archive(package, version, target, public_key)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise SigningError("signing output directory must be empty")
    with tempfile.TemporaryDirectory(prefix="pirate-recovery-gpg-") as temporary:
        work = Path(temporary)
        home = work / "keyring"
        home.mkdir(mode=0o700)
        os.chmod(home, 0o700)
        staged = work / "signed"
        staged.mkdir()
        try:
            gpg(home, ["--import"], data=public_key)
            public_fingerprints = primary_fingerprints(gpg(home, ["--with-colons", "--list-keys"]), "pub")
            if public_fingerprints != [expected_fingerprint]:
                raise SigningError("public key fingerprint does not match the configured release signer")
            gpg(home, ["--import"], data=private_key)
            secret_fingerprints = primary_fingerprints(gpg(home, ["--with-colons", "--list-secret-keys"]), "sec")
            if secret_fingerprints != [expected_fingerprint]:
                raise SigningError("private key must contain exactly the expected release signer")
            for name in sorted(expected_names):
                shutil.copyfile(input_dir / name, staged / name)
            (staged / "public_key.asc").write_bytes(public_key)
            sums_lines = []
            for path in sorted(staged.iterdir()):
                with path.open("rb") as handle:
                    checksum = hashlib.file_digest(handle, "sha256").hexdigest()
                sums_lines.append(f"{checksum}  {path.name}\n")
            sums = "".join(sums_lines)
            (staged / "SHA256SUMS").write_text(sums, encoding="ascii", newline="\n")
            for name in [*sorted(expected_names), "SHA256SUMS"]:
                payload = staged / name
                signature = staged / f"{name}.asc"
                gpg(home, ["--pinentry-mode", "loopback", "--passphrase-fd", "0",
                           "--local-user", expected_fingerprint, "--armor", "--digest-algo", "SHA256",
                           "--output", str(signature), "--detach-sign", str(payload)],
                    data=(passphrase + "\n").encode("utf-8"))
                verify_signature(home, signature, payload, expected_fingerprint)
            for path in sorted(staged.iterdir()):
                shutil.copyfile(path, output_dir / path.name)
        finally:
            # Scope gpgconf explicitly to this temporary keyring, including on failure.
            subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "all"],
                           env=clean_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=30, check=True)
    print("Signed and verified five packages and SHA256SUMS.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    args = parser.parse_args()
    # Remove secret environment variables before starting any subprocess.
    private_key = os.environ.pop(SECRET_VARIABLES[0], "")
    passphrase = os.environ.pop(SECRET_VARIABLES[1], "")
    try:
        sign_release(args.input, args.output, args.version, args.public_key, private_key, passphrase)
    except (SigningError, OSError, ValueError, tarfile.TarError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        if isinstance(exc, SigningError):
            parser.exit(1, f"Release signing failed: {exc}\n")
        parser.exit(1, "Release signing failed while processing release files or running GPG.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
