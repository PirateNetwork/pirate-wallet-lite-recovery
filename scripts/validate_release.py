"""Validate release tags before any signing secrets become available."""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import re
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--default-branch", required=True)
    args = parser.parse_args()
    if not re.fullmatch(f"v{VERSION_PATTERN.pattern}", args.tag):
        parser.error("release tag must use v plus three numeric version components")
    subprocess.run(["git", "check-ref-format", f"refs/heads/{args.default_branch}"], cwd=ROOT, check=True)
    tag_sha = git("rev-parse", "--verify", f"refs/tags/{args.tag}^{{commit}}")
    if tag_sha != args.sha:
        parser.error("release tag and event commit must refer to the same commit")
    trusted_sha = git("rev-parse", "--verify", f"refs/remotes/origin/{args.default_branch}^{{commit}}")
    if git("rev-parse", "HEAD") != trusted_sha:
        parser.error("release validator must run from the trusted default-branch checkout")
    subprocess.run(["git", "merge-base", "--is-ancestor", tag_sha, trusted_sha], cwd=ROOT, check=True)
    # Inspect tag blobs without importing or executing any tagged source code.
    version = tomllib.loads(git("show", f"{tag_sha}:pyproject.toml"))["project"]["version"]
    if not VERSION_PATTERN.fullmatch(version) or args.tag != f"v{version}":
        parser.error("release tag must be exactly v<project.version>, with three numeric version components")
    package = ast.parse(git("show", f"{tag_sha}:src/pirate_wallet_lite_recovery/__init__.py"))
    declared_versions = [ast.literal_eval(statement.value) for statement in package.body
                         if isinstance(statement, ast.Assign)
                         and any(isinstance(target, ast.Name) and target.id == "__version__" for target in statement.targets)]
    if declared_versions != [version]:
        parser.error("package __version__ must exactly match project.version")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"version={version}\ntag={args.tag}\ntrusted_sha={trusted_sha}\n")
    print(f"Validated release {args.tag} on the default branch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
