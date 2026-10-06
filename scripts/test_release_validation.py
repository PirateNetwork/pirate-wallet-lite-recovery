"""Test release gates in temporary repositories with no remote or user key."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import validate_release


class ReleaseValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="pirate-recovery-tag-test-")
        self.root = Path(self.temporary.name)
        (self.root / "src" / "pirate_wallet_lite_recovery").mkdir(parents=True)
        (self.root / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n', encoding="utf-8")
        (self.root / "src" / "pirate_wallet_lite_recovery" / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
        self.git("init", "--initial-branch=main")
        self.git("add", ".")
        self.commit("Synthetic release fixture")
        self.sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.sha)
        self.git("tag", "v1.0.0")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=self.root, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        return result.stdout.strip()

    def commit(self, message: str) -> None:
        # Explicitly disable commit signing: these are disposable fixtures.
        self.git("-c", "commit.gpgsign=false", "-c", "user.name=Recovery CI Test",
                 "-c", "user.email=ci@example.invalid", "commit", "-m", message)

    def validate(self, *, tag: str = "v1.0.0", sha: str | None = None) -> int:
        arguments = ["validate_release.py", "--tag", tag, "--sha", sha if sha is not None else self.sha,
                     "--default-branch", "main"]
        return self.run_validation(arguments)

    def validate_main(self, *, sha: str | None = None, ref: str = "refs/heads/main",
                      default_branch: str = "main", tag: str | None = None) -> int:
        arguments = ["validate_release.py", "--mode", "main-push", "--ref", ref,
                     "--sha", sha if sha is not None else self.sha, "--default-branch", default_branch]
        if tag is not None:
            arguments.extend(["--tag", tag])
        return self.run_validation(arguments)

    def run_validation(self, arguments: list[str]) -> int:
        with patch.object(validate_release, "ROOT", self.root), patch.object(sys, "argv", arguments), \
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(self.root / "outputs")}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return validate_release.main()

    def test_matching_tag_on_default_branch_is_accepted(self) -> None:
        self.assertEqual(self.validate(), 0)
        outputs = (self.root / "outputs").read_text(encoding="utf-8")
        self.assertIn(f"trusted_sha={self.sha}\n", outputs)
        self.assertIn("version=1.0.0\ntag=v1.0.0\n", outputs)
        self.assertIn(f"source_sha={self.sha}\n", outputs)
        self.assertIn("mode=tag\n", outputs)

    def test_wrong_tag_version_is_refused(self) -> None:
        self.git("tag", "v1.0.1")
        with self.assertRaises(SystemExit):
            self.validate(tag="v1.0.1")

    def test_mismatched_event_sha_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            self.validate(sha="0" * 40)

    def test_package_version_mismatch_is_refused(self) -> None:
        (self.root / "src" / "pirate_wallet_lite_recovery" / "__init__.py").write_text('__version__ = "2.0.0"\n', encoding="utf-8")
        self.git("add", ".")
        self.commit("Synthetic package version mismatch")
        mismatch_sha = self.git("rev-parse", "HEAD")
        self.git("tag", "-f", "v1.0.0", mismatch_sha)
        self.git("update-ref", "refs/remotes/origin/main", mismatch_sha)
        with self.assertRaises(SystemExit):
            self.validate(sha=mismatch_sha)

    def test_tag_outside_default_branch_is_refused(self) -> None:
        (self.root / "extra.txt").write_text("Synthetic branch-only content\n", encoding="utf-8")
        self.git("add", ".")
        self.commit("Synthetic unmerged fixture")
        unmerged = self.git("rev-parse", "HEAD")
        self.git("tag", "-f", "v1.0.0", unmerged)
        self.git("switch", "--detach", self.sha)
        with self.assertRaises(subprocess.CalledProcessError):
            self.validate(sha=unmerged)

    def test_old_reviewed_tag_uses_trusted_default_branch_validator(self) -> None:
        (self.root / "later.txt").write_text("Synthetic later default-branch commit\n", encoding="utf-8")
        self.git("add", ".")
        self.commit("Synthetic later default branch")
        trusted_sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", trusted_sha)
        self.assertEqual(self.validate(), 0)
        self.assertIn(f"trusted_sha={trusted_sha}\n", (self.root / "outputs").read_text(encoding="utf-8"))

    def test_untrusted_validator_checkout_is_refused(self) -> None:
        (self.root / "untrusted.txt").write_text("Synthetic untrusted checkout\n", encoding="utf-8")
        self.git("add", ".")
        self.commit("Synthetic untrusted checkout")
        with self.assertRaises(SystemExit):
            self.validate()

    def test_main_push_generates_version_and_twelve_character_commit_tag(self) -> None:
        self.assertEqual(self.validate_main(), 0)
        outputs = (self.root / "outputs").read_text(encoding="utf-8")
        self.assertIn(f"version=1.0.0\ntag=v1.0.0-{self.sha[:12]}\n", outputs)
        self.assertIn(f"source_sha={self.sha}\ntrusted_sha={self.sha}\nmode=main-push\n", outputs)
        self.assertEqual(self.git("tag", "--list"), "v1.0.0")

    def test_main_push_rerun_generates_the_same_tag(self) -> None:
        self.validate_main()
        initial = (self.root / "outputs").read_text(encoding="utf-8")
        (self.root / "outputs").write_text("", encoding="utf-8")
        self.validate_main()
        self.assertEqual((self.root / "outputs").read_text(encoding="utf-8"), initial)

    def test_distinct_main_commits_generate_distinct_tags(self) -> None:
        self.validate_main()
        initial_tag = f"tag=v1.0.0-{self.sha[:12]}\n"
        (self.root / "later.txt").write_text("Synthetic new main commit\n", encoding="utf-8")
        self.git("add", ".")
        self.commit("Synthetic second main push")
        later_sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", later_sha)
        (self.root / "outputs").write_text("", encoding="utf-8")
        self.validate_main(sha=later_sha)
        outputs = (self.root / "outputs").read_text(encoding="utf-8")
        self.assertIn(f"tag=v1.0.0-{later_sha[:12]}\n", outputs)
        self.assertNotIn(initial_tag, outputs)

    def test_old_main_push_uses_event_source_and_new_trusted_head(self) -> None:
        (self.root / "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n', encoding="utf-8")
        (self.root / "src" / "pirate_wallet_lite_recovery" / "__init__.py").write_text('__version__ = "2.0.0"\n', encoding="utf-8")
        self.git("add", ".")
        self.commit("Synthetic later main version")
        later_sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", later_sha)
        self.assertEqual(self.validate_main(), 0)
        outputs = (self.root / "outputs").read_text(encoding="utf-8")
        self.assertIn(f"version=1.0.0\ntag=v1.0.0-{self.sha[:12]}\n", outputs)
        self.assertIn(f"source_sha={self.sha}\ntrusted_sha={later_sha}\n", outputs)

    def test_main_push_rejects_non_main_ref_and_default_branch(self) -> None:
        for ref, default_branch in (("refs/heads/feature", "main"), ("refs/tags/v1.0.0", "main"),
                                    ("refs/heads/main", "master")):
            with self.subTest(ref=ref, default_branch=default_branch), self.assertRaises(SystemExit):
                self.validate_main(ref=ref, default_branch=default_branch)

    def test_main_push_rejects_explicit_tag(self) -> None:
        with self.assertRaises(SystemExit):
            self.validate_main(tag="v1.0.0")

    def test_release_modes_reject_noncanonical_event_sha(self) -> None:
        for sha in (self.sha[:12], "g" * 40, self.sha.upper(), "HEAD", ""):
            with self.subTest(sha=sha, mode="main-push"), self.assertRaises(SystemExit):
                self.validate_main(sha=sha)
            with self.subTest(sha=sha, mode="tag"), self.assertRaises(SystemExit):
                self.validate(sha=sha)

    def test_main_push_rejects_commit_outside_main_history(self) -> None:
        (self.root / "foreign.txt").write_text("Synthetic unmerged content\n", encoding="utf-8")
        self.git("add", ".")
        self.commit("Synthetic foreign commit")
        foreign_sha = self.git("rev-parse", "HEAD")
        self.git("switch", "--detach", self.sha)
        with self.assertRaises(subprocess.CalledProcessError):
            self.validate_main(sha=foreign_sha)

    def test_main_push_rejects_source_version_mismatch(self) -> None:
        (self.root / "src" / "pirate_wallet_lite_recovery" / "__init__.py").write_text('__version__ = "2.0.0"\n', encoding="utf-8")
        self.git("add", ".")
        self.commit("Synthetic main source version mismatch")
        mismatch_sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", mismatch_sha)
        with self.assertRaises(SystemExit):
            self.validate_main(sha=mismatch_sha)

    def test_main_push_rejects_an_annotated_tag_object_as_event_sha(self) -> None:
        self.git("-c", "tag.gpgsign=false", "-c", "user.name=Recovery CI Test",
                 "-c", "user.email=ci@example.invalid", "tag", "-a", "synthetic-annotated",
                 "-m", "Synthetic annotated tag")
        tag_object_sha = self.git("rev-parse", "refs/tags/synthetic-annotated")
        with self.assertRaises(SystemExit):
            self.validate_main(sha=tag_object_sha)


if __name__ == "__main__":
    unittest.main(verbosity=2)
