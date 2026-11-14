"""Tests for context_digest.py: what the digest sees and what it ignores."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import context_digest

SCRIPT = Path(__file__).with_name("context_digest.py")

SPEC = """# Spec

Status: approved

## Acceptance criteria

1. AC1 - login redirects to /home.
"""

PLAN = """# Plan

**Spec:** docs/specs/s.md

## Tasks

### Task 1

Covers: AC1

## Execution record

```text
Base: %s   Root: /r   Branch: b
Task 1: done - test -> ok
%s```
"""


def record(extra=""):
    return PLAN % ("a" * 40, extra)


class Repo:
    def __init__(self, test):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".git").mkdir()
        (self.root / "docs" / "specs").mkdir(parents=True)
        self.plan = self.root / "docs" / "plan.md"
        self.spec = self.root / "docs" / "specs" / "s.md"
        self.spec.write_text(SPEC)
        self.plan.write_text(record())

    def digest(self, path=None):
        return context_digest.digest(str(path or self.plan))


class DigestTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.base = self.repo.digest()

    def change_plan(self, old, new):
        text = self.repo.plan.read_text()
        self.assertEqual(text.count(old), 1)
        self.repo.plan.write_text(text.replace(old, new))

    def test_digest_shape(self):
        self.assertRegex(self.base, r"^sha256:[0-9a-f]{64}$")

    def test_spec_ac_change_changes_digest(self):
        self.repo.spec.write_text(SPEC.replace("/home", "/dashboard"))
        self.assertNotEqual(self.repo.digest(), self.base)

    def test_spec_status_change_changes_digest(self):
        self.repo.spec.write_text(SPEC.replace("approved", "draft"))
        self.assertNotEqual(self.repo.digest(), self.base)

    def test_plan_task_change_changes_digest(self):
        self.change_plan("### Task 1", "### Task 1 renamed")
        self.assertNotEqual(self.repo.digest(), self.base)

    def test_covers_change_changes_digest(self):
        self.change_plan("Covers: AC1", "Covers: AC2")
        self.assertNotEqual(self.repo.digest(), self.base)

    def test_appended_chain_lines_do_not_change_digest(self):
        extra = (
            "Verify: PASS full tree %s context none 2026-11-14 08:00\n" % ("b" * 40)
            + "Round verify 1: AC1 - x\n"
            + "Review R1: Clean tree %s reviewer m mode code\n" % ("b" * 40)
            + "Finding R1-F1: Minor a.py:1 - t\n"
            + "Received R1: R1-F1 ACCEPT Re-review: not needed\n"
            + "Task 2: pending\n"
            + "Ruling: round R1 started by the user past the limit - go - low\n"
            + "Ruling: no review - user said so - low\n")
        self.repo.plan.write_text(record(extra))
        self.assertEqual(self.repo.digest(), self.base)

    def test_other_ruling_changes_digest(self):
        self.repo.plan.write_text(record("Ruling: use X - same - low\n"))
        self.assertNotEqual(self.repo.digest(), self.base)

    def test_deferred_changes_digest(self):
        self.repo.plan.write_text(record("Deferred: flaky test - issue\n"))
        self.assertNotEqual(self.repo.digest(), self.base)

    def test_spec_ruling_changes_digest(self):
        self.repo.spec.write_text(SPEC + "\n## Verification record\n\n```text\n"
                                  "Branch: b\nRuling: spec re-approved - 2026-11-14\n```\n")
        self.assertNotEqual(self.repo.digest(), self.base)

    def test_spec_verify_line_does_not_change_digest(self):
        self.repo.spec.write_text(SPEC + "\n## Verification record\n\n```text\n"
                                  "Branch: b\nVerify: PASS full tree x\n```\n")
        self.assertEqual(self.repo.digest(), self.base)

    def test_crlf_equals_lf(self):
        crlf = self.repo.plan.read_bytes().replace(b"\n", b"\r\n")
        self.repo.plan.write_bytes(crlf)
        self.repo.spec.write_bytes(self.repo.spec.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.repo.digest(), self.base)

    def test_heading_inside_fence_is_not_a_boundary(self):
        fenced = ("## Tasks\n\n```text\n## Execution record\n```\n")
        self.change_plan("## Tasks\n", fenced)
        with_fence = self.repo.digest()
        # The fenced heading stays in the body, so editing it changes the digest.
        self.change_plan("```text\n## Execution record\n```", "```text\n## Execution record x\n```")
        self.assertNotEqual(self.repo.digest(), with_fence)

    def test_shorter_fence_does_not_close_longer_one(self):
        body = "## Tasks\n\n````text\n```\n## Execution record\n```\n````\n"
        self.change_plan("## Tasks\n", body)
        first = self.repo.digest()
        self.change_plan("```\n## Execution record\n```", "```\n## Execution record x\n```")
        self.assertNotEqual(self.repo.digest(), first)

    def test_spec_none(self):
        self.change_plan("**Spec:** docs/specs/s.md", "**Spec:** none")
        self.repo.spec.unlink()
        self.assertRegex(self.repo.digest(), r"^sha256:")

    def test_absolute_spec_path_outside_repo(self):
        with tempfile.TemporaryDirectory() as other:
            spec = Path(other) / "spec.md"
            spec.write_text(SPEC)
            self.change_plan("docs/specs/s.md", str(spec))
            first = self.repo.digest()
            spec.write_text(SPEC + "\nextra\n")
            self.assertNotEqual(self.repo.digest(), first)

    def test_host_without_record_section(self):
        self.repo.spec.write_text(SPEC)
        self.assertRegex(self.repo.digest(self.repo.spec), r"^sha256:")


class FailClosedTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)

    def run_cli(self, path):
        return subprocess.run([sys.executable, str(SCRIPT), str(path)],
                              capture_output=True, text=True)

    def assert_exit2(self, path):
        done = self.run_cli(path)
        self.assertEqual((done.returncode, done.stdout), (2, ""), done.stderr)
        return done.stderr

    def test_missing_host(self):
        self.assert_exit2(self.repo.root / "nope.md")

    def test_missing_named_spec(self):
        self.repo.spec.unlink()
        self.assertIn("cannot read", self.assert_exit2(self.repo.plan))

    def test_duplicate_record_heading(self):
        text = self.repo.plan.read_text()
        self.repo.plan.write_text(text + "\n## Execution record\n\n```text\n```\n")
        self.assertIn("duplicate", self.assert_exit2(self.repo.plan))

    def test_unclosed_fence(self):
        self.repo.plan.write_text(self.repo.plan.read_text() + "\n```text\nno end\n")
        self.assertIn("unclosed", self.assert_exit2(self.repo.plan))

    def test_unclosed_fence_in_spec(self):
        self.repo.spec.write_text(SPEC + "\n```\nopen\n")
        self.assertIn("unclosed", self.assert_exit2(self.repo.plan))

    def test_success_prints_one_word(self):
        done = self.run_cli(self.repo.plan)
        self.assertEqual(done.returncode, 0)
        self.assertRegex(done.stdout, r"^sha256:[0-9a-f]{64}\n$")


if __name__ == "__main__":
    unittest.main()
