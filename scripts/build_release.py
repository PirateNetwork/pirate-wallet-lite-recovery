"""Build, package, and smoke-test one native release without reading a wallet."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
APP = "pirate-wallet-lite-recovery"
TARGETS = {
    "windows-x64": ("Windows", "x64", "Windows 10/11 x64; CI: Windows Server 2022"),
    "linux-x64": ("Linux", "x64", "glibc 2.35 or later; CI: Ubuntu 22.04 x64"),
    "linux-arm64": ("Linux", "arm64", "glibc 2.35 or later; CI: Ubuntu 22.04 ARM64"),
    "macos-x64": ("Darwin", "x64", "macOS 15 or later; CI: macOS 15 Intel"),
    "macos-arm64": ("Darwin", "arm64", "macOS 14 or later; CI: macOS 14 ARM64"),
}


def native_architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64", "x64"}:
        return "x64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    raise ValueError(f"unsupported native architecture: {machine}")


def locked_packages(path: Path, seen: set[Path] | None = None) -> set[str]:
    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen:
        return set()
    seen.add(path)
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("-r "):
            names.update(locked_packages(path.parent / line[3:].strip(), seen))
        elif match := re.match(r"([A-Za-z0-9_.-]+)==", line):
            names.add(match.group(1))
    return names


def is_license_document(entry: Path, declared: set[str]) -> bool:
    if (any(part.lower() == "__pycache__" for part in entry.parts) or
            entry.suffix.lower() in {".py", ".pyi", ".pyc", ".pyo", ".pyd", ".so", ".dll"}):
        return False
    if entry.name.lower().startswith(("license", "licence", "copying", "notice", "authors")):
        return True
    # Declared legal files live under metadata directories, not Python modules
    # such as packaging/licenses. Older wheels omit the licenses/ subdirectory.
    for index, part in enumerate(entry.parts):
        if part.endswith(".dist-info"):
            relative = "/".join(entry.parts[index + 1:])
            return relative in declared or relative.removeprefix("licenses/") in declared
    return False


def collect_licenses(destination: Path) -> None:
    destination.mkdir()
    records = []
    for name in sorted(locked_packages(ROOT / "requirements-build.lock")):
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue  # Dependencies guarded by another platform's marker.
        package_dir = destination / f"{name}-{distribution.version}"
        package_dir.mkdir()
        copied = []
        declared = set(distribution.metadata.get_all("License-File", []))
        for entry in distribution.files or []:
            parts = entry.parts
            if not is_license_document(entry, declared):
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file() or source.is_symlink():
                continue
            relative = Path(*parts)
            if relative.is_absolute() or ".." in relative.parts:
                continue
            target = package_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(relative.as_posix())
        if not copied:
            raise RuntimeError(f"installed distribution {name} has no bundled license text")
        records.append({"name": name, "version": distribution.version,
                        "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", ""),
                        "files": copied})
    shutil.copyfile(ROOT / "scripts" / "licenses" / "PYTHON-LICENSE.txt", destination / "PYTHON-LICENSE.txt")
    (destination / "index.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def smoke_test(executable: Path, directory: Path) -> None:
    environment = os.environ.copy()
    for variable in ("PYTHONPATH", "PYTHONHOME", "LINUX_GPG_PRIVATE_KEY_B64", "LINUX_GPG_PASSPHRASE"):
        environment.pop(variable, None)
    subprocess.run([str(executable.resolve()), "--self-test"], cwd=directory,
                   env=environment, check=True, timeout=120)


def make_archive(stage: Path, output: Path, windows: bool) -> None:
    files = sorted(path for path in stage.rglob("*") if path.is_file())
    if windows:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, path.relative_to(stage.parent).as_posix())
    else:
        with tarfile.open(output, "x:gz", format=tarfile.PAX_FORMAT) as archive:
            for path in files:
                archive.add(path, arcname=path.relative_to(stage.parent).as_posix(), recursive=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "release")
    args = parser.parse_args()
    operating_system, architecture, baseline = TARGETS[args.target]
    if (platform.system(), native_architecture()) != (operating_system, architecture):
        parser.error("target must match the current operating system and native Python architecture")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        parser.error("project.version must contain three numeric components")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    basename = f"{APP}-{version}-{args.target}"
    windows = operating_system == "Windows"
    package = output / f"{basename}{'.zip' if windows else '.tar.gz'}"
    if package.exists():
        parser.error(f"package already exists: {package.name}; choose a fresh output directory")
    executable_name = f"{APP}{'.exe' if windows else ''}"
    with tempfile.TemporaryDirectory(prefix="pirate-recovery-build-") as temporary:
        work = Path(temporary)
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--onefile", "--console", "--noupx", "--name", APP,
            "--distpath", str(work / "dist"), "--workpath", str(work / "work"),
            "--specpath", str(work), "--paths", str(ROOT / "src"),
            "--hidden-import", "_cffi_backend", "--collect-all", "mnemonic",
            "--collect-all", "nacl", "--collect-submodules", "pirate_wallet_lite_recovery",
            str(ROOT / "scripts" / "frozen_entry.py"),
        ], cwd=ROOT, check=True)
        stage = work / basename
        stage.mkdir()
        executable = stage / executable_name
        shutil.copy2(work / "dist" / executable_name, executable)
        for document in ("README.md", "SECURITY.md", "LICENSE"):
            shutil.copyfile(ROOT / document, stage / document)
        shutil.copyfile(ROOT / "release-signing" / "public_key.asc", stage / "public_key.asc")
        (stage / "release-signing").mkdir()
        shutil.copyfile(ROOT / "release-signing" / "README.md", stage / "release-signing" / "README.md")
        collect_licenses(stage / "THIRD_PARTY_LICENSES")
        smoke_test(executable, work)
        build_info = {
            "name": APP, "version": version, "target": args.target,
            "python": platform.python_version(), "pyinstaller": importlib.metadata.version("pyinstaller"),
            "tested_baseline": baseline, "self_test": "passed",
            "commit": os.environ.get("GITHUB_SHA", "local-build"),
            "dependencies": {name: importlib.metadata.version(name)
                             for name in sorted(locked_packages(ROOT / "requirements.lock"))},
        }
        (stage / "BUILD-INFO.json").write_text(json.dumps(build_info, indent=2) + "\n", encoding="utf-8")
        temporary_archive = work / package.name
        make_archive(stage, temporary_archive, windows)
        extracted = work / "extracted"
        extracted.mkdir()
        if windows:
            with zipfile.ZipFile(temporary_archive) as archive:
                archive.extractall(extracted)
        else:
            with tarfile.open(temporary_archive) as archive:
                archive.extractall(extracted, filter="data")
        smoke_test(extracted / basename / executable_name, extracted)
        shutil.copyfile(temporary_archive, package)
    print(f"Created and tested {package.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
