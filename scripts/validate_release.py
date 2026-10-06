"""Validate version tags or main pushes before signing secrets become available."""

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
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("tag", "main-push"), default="tag")
    parser.add_argument("--tag")
    parser.add_argument("--ref")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--default-branch", required=True)
    args = parser.parse_args()
    if not SHA_PATTERN.fullmatch(args.sha):
        parser.error("event SHA must be a full canonical 40-character lowercase hexadecimal commit SHA")
    if args.mode == "main-push":
        if args.tag is not None:
            parser.error("main-push mode does not accept --tag")
        if args.ref != "refs/heads/main" or args.default_branch != "main":
            parser.error("main-push releases require refs/heads/main and default branch main")
    elif args.tag is None or not re.fullmatch(f"v{VERSION_PATTERN.pattern}", args.tag):
        parser.error("release tag must use v plus three numeric version components")
    subprocess.run(["git", "check-ref-format", f"refs/heads/{args.default_branch}"], cwd=ROOT, check=True)
    if args.mode == "tag":
        source_sha = git("rev-parse", "--verify", f"refs/tags/{args.tag}^{{commit}}")
        if source_sha != args.sha:
            parser.error("release tag and event commit must refer to the same commit")
    else:
        source_sha = git("rev-parse", "--verify", f"{args.sha}^{{commit}}")
        if source_sha != args.sha:
            parser.error("event SHA must resolve to exactly the pushed commit")
    trusted_sha = git("rev-parse", "--verify", f"refs/remotes/origin/{args.default_branch}^{{commit}}")
    if git("rev-parse", "HEAD") != trusted_sha:
        parser.error("release validator must run from the trusted default-branch checkout")
    subprocess.run(["git", "merge-base", "--is-ancestor", source_sha, trusted_sha], cwd=ROOT, check=True)
    # Inspect event-commit blobs without importing or executing source code.
    version = tomllib.loads(git("show", f"{source_sha}:pyproject.toml"))["project"]["version"]
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        parser.error("project.version must use three numeric version components")
    if args.mode == "tag" and args.tag != f"v{version}":
        parser.error("release tag must be exactly v<project.version>, with three numeric version components")
    package = ast.parse(git("show", f"{source_sha}:src/pirate_wallet_lite_recovery/__init__.py"))
    declared_versions = [ast.literal_eval(statement.value) for statement in package.body
                         if isinstance(statement, ast.Assign)
                         and any(isinstance(target, ast.Name) and target.id == "__version__" for target in statement.targets)]
    if declared_versions != [version]:
        parser.error("package __version__ must exactly match project.version")
    release_tag = args.tag if args.mode == "tag" else f"v{version}-{source_sha[:12]}"
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"version={version}\ntag={release_tag}\nsource_sha={source_sha}\n"
                         f"trusted_sha={trusted_sha}\nmode={args.mode}\n")
    print(f"Validated {args.mode} release {release_tag} on the default branch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
