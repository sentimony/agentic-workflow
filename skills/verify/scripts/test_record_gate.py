"""Tests for record_gate.py: blockers, the finalize gate, and the failure-code table."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import record_gate

SCRIPT = Path(__file__).with_name("record_gate.py")
TABLE = Path(__file__).resolve().parent.parent / "record-gate.md"
TREE, OTHER_TREE = "a" * 40, "b" * 40
CTX, OTHER_CTX = "sha256:" + "1" * 64, "sha256:" + "2" * 64

BASE = "Base: %s   Root: /r   Branch: b" % ("c" * 40)
VERIFY = "Verify: PASS full tree %s context %s 2026-11-14 08:00" % (TREE, CTX)
CODE = "Review R1: Clean tree %s reviewer m mode code" % TREE


def host(lines, heading="## Execution record"):
    return "# Plan\n\n%s\n\n```text\n%s\n```\n" % (heading, "\n".join(lines))


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "plan.md"

    def write(self, lines, heading="## Execution record"):
        self.path.write_text(host(lines, heading))

    def load(self):
        lines, kind = record_gate.read_record(str(self.path))
        return record_gate.parse(lines), kind

    def gate(self, lines, integrate="merge", tree=TREE, ctx=CTX, heading="## Execution record"):
        self.write(lines, heading)
        events, kind = self.load()
        return record_gate.gate(events, kind, tree, ctx, integrate)

    def blockers(self, lines):
        self.write(lines)
        return record_gate.blockers(self.load()[0])


class GateTest(Case):
    def test_clean_pass(self):
        self.assertEqual(self.gate([BASE, VERIFY, CODE]), [])

    def test_no_verify(self):
        self.assertEqual(self.gate([BASE, CODE]), ["no-verify"])

    def test_tree_changed(self):
        self.assertEqual(self.gate([BASE, VERIFY, CODE], tree=OTHER_TREE), ["tree-mismatch"])

    def test_context_changed(self):
        self.assertEqual(self.gate([BASE, VERIFY, CODE], ctx=OTHER_CTX), ["context-mismatch"])

    def test_old_line_without_context(self):
        old = "Verify: PASS full tree %s 2026-11-14 08:00" % TREE
        self.assertEqual(self.gate([BASE, old, CODE]), ["context-missing"])

    def test_hostless_none_matches_none(self):
        line = "Verify: PASS full tree %s context none 2026-11-14 08:00" % TREE
        self.assertEqual(self.gate([BASE, line, CODE], ctx="none"), [])

    def test_non_pass_compact_working_scoped(self):
        def v(verdict="PASS", mode="full", suffix=""):
            return "Verify: %s %s tree %s context %s 2026-11-14 08:00%s" % (
                verdict, mode, TREE, CTX, suffix)
        self.assertEqual(self.gate([BASE, v("FAIL"), CODE]), ["verify-not-pass"])
        self.assertEqual(self.gate([BASE, v(mode="compact"), CODE]), ["verify-compact"])
        self.assertEqual(self.gate([BASE, v(suffix=" working"), CODE]), ["verify-working"])
        self.assertEqual(self.gate([BASE, v(suffix=" scoped a.py"), CODE]), ["verify-scoped"])

    def test_appended_verify_and_round_do_not_reject(self):
        lines = [BASE, VERIFY, CODE, "Round verify 1: AC1 - x", VERIFY]
        self.assertEqual(self.gate(lines), [])

    def test_last_verify_wins(self):
        fail = "Verify: FAIL full tree %s context %s 2026-11-14 09:00" % (TREE, CTX)
        self.assertEqual(self.gate([BASE, VERIFY, CODE, fail]), ["verify-not-pass"])

    def test_document_review_is_not_code_review(self):
        doc = "Review R1: Clean tree %s reviewer m mode document" % TREE
        self.assertEqual(self.gate([BASE, VERIFY, doc]), ["no-code-review"])

    def test_code_review_before_base_does_not_count(self):
        self.assertEqual(self.gate([CODE, BASE, VERIFY]), ["no-code-review"])

    def test_marker_resets_code_review(self):
        marker = "Ruling: plan revised after spec re-approval - docs/s.md"
        self.assertEqual(self.gate([BASE, CODE, marker, VERIFY]), ["no-code-review"])
        self.assertEqual(self.gate([BASE, CODE, marker, CODE, VERIFY]), [])

    def test_spec_record_counts_review_anywhere(self):
        self.assertEqual(self.gate([CODE, VERIFY], heading="## Verification record"), [])

    def test_no_review_ruling_replaces_review(self):
        ruling = "Ruling: no review - user said skip - low"
        self.assertEqual(self.gate([BASE, VERIFY, ruling]), [])

    def test_pr_does_not_need_review(self):
        self.assertEqual(self.gate([BASE, VERIFY], integrate="pr"), [])

    def test_squash_needs_review(self):
        self.assertEqual(self.gate([BASE, VERIFY], integrate="squash"), ["no-code-review"])

    def test_rereview_needed_without_review(self):
        rec = "Received R1: R1-F1 ACCEPT Re-review: needed"
        find = "Finding R1-F1: Important a.py:1 - t"
        later = "Verify: PASS full tree %s context %s 2026-11-14 09:00" % (TREE, CTX)
        self.assertEqual(self.gate([BASE, CODE, find, rec, later]), ["re-review-needed"])
        rr = "Review R2: Clean tree %s reviewer m mode re-review" % TREE
        self.assertEqual(self.gate([BASE, CODE, find, rec, rr, later]), [])

    def test_clean_code_review_does_not_invalidate(self):
        second = "Review R2: Clean tree %s reviewer m mode code" % TREE
        self.assertEqual(self.gate([BASE, VERIFY, CODE, second]), [])

    def test_new_and_old_open_blockers_reject(self):
        old = "Finding R1-F1: Critical a.py:1 - t"
        new = "Finding R2-F1: Important b.py:2 - t"
        got = self.gate([BASE, CODE, old, new, VERIFY])
        self.assertEqual(got, ["open-blocker:R1-F1", "open-blocker:R2-F1"])

    def test_disposition_closes_blocker(self):
        find = "Finding R1-F1: Critical a.py:1 - t"
        for word in ("REJECT", "OUTDATED"):
            rec = "Received R1: R1-F1 %s Re-review: not needed" % word
            self.assertEqual(self.gate([BASE, CODE, find, rec, VERIFY]), [], word)
        important = "Finding R1-F1: Important a.py:1 - t"
        rec = "Received R1: R1-F1 DEFER Re-review: not needed"
        self.assertEqual(self.gate([BASE, CODE, important, rec, VERIFY]), [])

    def test_critical_defer_stays_open(self):
        find = "Finding R1-F1: Critical a.py:1 - t"
        rec = "Received R1: R1-F1 DEFER Re-review: not needed"
        self.assertEqual(self.gate([BASE, CODE, find, rec, VERIFY]), ["open-blocker:R1-F1"])

    def test_accept_needs_later_pass(self):
        find = "Finding R1-F1: Critical a.py:1 - t"
        rec = "Received R1: R1-F1 ACCEPT Re-review: not needed"
        self.assertEqual(self.gate([BASE, VERIFY, CODE, find, rec]), ["open-blocker:R1-F1"])
        self.assertEqual(self.gate([BASE, CODE, find, rec, VERIFY]), [])

    def test_escalate_until_decided(self):
        find = "Finding R1-F1: Minor a.py:1 - t"
        rec = "Received R1: R1-F1 ESCALATE Re-review: not needed"
        dec = "Ruling: R1-F1 escalation decided - owner said keep - low"
        self.assertEqual(self.gate([BASE, CODE, find, rec, VERIFY]), ["open-blocker:R1-F1"])
        self.assertEqual(self.gate([BASE, CODE, find, rec, dec, VERIFY]), [])

    def test_minor_finding_is_no_blocker(self):
        self.assertEqual(self.blockers([BASE, "Finding R1-F1: Minor a.py:1 - t"]), [])

    def test_blockers_mode_accepts_unverified_fix(self):
        find = "Finding R1-F1: Critical a.py:1 - t"
        rec = "Received R1: R1-F1 PARTIAL Re-review: not needed"
        self.assertEqual(self.blockers([BASE, CODE, find, rec]), [])
        got = self.blockers([BASE, CODE, find])
        self.assertEqual([b["id"] for b in got], ["R1-F1"])
        self.assertEqual(set(got[0]), {"id", "severity", "why"})


class ParseErrorTest(Case):
    def test_two_record_headings(self):
        self.path.write_text(host([BASE]) + "\n## Execution record\n\n```text\n```\n")
        with self.assertRaises(record_gate.GateError):
            record_gate.read_record(str(self.path))

    def test_incomplete_verify_line(self):
        with self.assertRaises(record_gate.GateError):
            self.gate([BASE, "Verify: PASS full tree %s" % TREE])

    def test_lines_outside_text_block_are_ignored(self):
        self.path.write_text("## Execution record\n\n" + VERIFY + "\n\n```text\n" + BASE + "\n```\n")
        self.assertEqual(record_gate.read_record(str(self.path))[0], [BASE])

    def test_heading_in_fence_is_not_a_section(self):
        self.path.write_text("```text\n## Execution record\n```\n" + host([BASE, VERIFY]))
        self.assertEqual(len(record_gate.read_record(str(self.path))[0]), 2)


class CliTest(Case):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

    def test_gate_exit_codes_and_json(self):
        self.write([BASE, VERIFY, CODE])
        ok = self.run_cli("--gate", str(self.path), "--tree", TREE, "--context", CTX)
        self.assertEqual((ok.returncode, json.loads(ok.stdout)), (0, {"ok": True, "reasons": []}))
        bad = self.run_cli("--gate", str(self.path), "--tree", OTHER_TREE, "--context", CTX)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout), {"ok": False, "reasons": ["tree-mismatch"]})

    def test_blockers_exit_codes(self):
        self.write([BASE, "Finding R1-F1: Critical a.py:1 - t"])
        got = self.run_cli("--blockers", str(self.path))
        self.assertEqual(got.returncode, 1)
        self.assertEqual(json.loads(got.stdout)["blockers"][0]["id"], "R1-F1")
        self.write([BASE])
        self.assertEqual(self.run_cli("--blockers", str(self.path)).returncode, 0)

    def test_error_is_exit_2_with_empty_stdout(self):
        self.write([BASE, "Verify: PASS full tree"])
        got = self.run_cli("--gate", str(self.path), "--tree", TREE, "--context", CTX)
        self.assertEqual((got.returncode, got.stdout), (2, ""))
        missing = self.run_cli("--blockers", str(self.path.with_name("none.md")))
        self.assertEqual((missing.returncode, missing.stdout), (2, ""))


class TableTest(unittest.TestCase):
    def test_codes_match_record_gate_md(self):
        rows = re.findall(r"^\| `([a-z:<>-]+)` \|", TABLE.read_text(), re.M)
        self.assertEqual(sorted(rows), sorted(record_gate.REASON_CODES))

    def test_every_emitted_code_is_listed(self):
        source = Path(record_gate.__file__).read_text()
        emitted = set(re.findall(r'reasons\.append\("([a-z-]+)"\)', source))
        emitted |= set(re.findall(r'return \["([a-z-]+)"\]', source))
        self.assertTrue(emitted)
        self.assertLessEqual(emitted, set(record_gate.REASON_CODES))
        self.assertTrue(any(c.startswith("open-blocker") for c in record_gate.REASON_CODES))


if __name__ == "__main__":
    unittest.main()
