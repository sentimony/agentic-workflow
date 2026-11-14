import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import round_budget as rb  # noqa: E402

SHA = 'a' * 40


def review(n, mode):
    return 'Review R%d: Summary tree %s reviewer m mode %s' % (n, SHA, mode)


def rnd(n, cause='x', ph=None):
    return 'Round review %d: %s%s' % (n, (ph + ' ') if ph else '', cause)


class Scenarios(unittest.TestCase):
    def test_1_code_review_after_two_document_rounds_is_round_one_of_three(self):
        lines = [review(1, 'document'), rnd(1, ph='document'), review(2, 'document'), rnd(2, ph='document'),
                 review(3, 'code'), rnd(3, ph='code')]
        self.assertEqual(rb.count(lines), {'document': 2, 'code': 1})
        a = rb.allowed(lines)
        self.assertEqual(a['code']['used'], 1)
        self.assertTrue(a['code']['automatic_allowed'])
        self.assertFalse(a['code']['last_automatic'])

    def test_2_fourth_code_round_needs_user_and_document_rounds_do_not_add(self):
        lines = [review(1, 'document'), rnd(1, ph='document'), review(2, 'document'), rnd(2, ph='document')]
        for k in range(3):
            lines += [review(3 + k, 'code'), rnd(3 + k, ph='code')]
        a = rb.allowed(lines)
        self.assertEqual(a['code']['used'], 3)
        self.assertFalse(a['code']['automatic_allowed'])
        self.assertTrue(a['document']['remaining'] == 1 and a['document']['last_automatic'])
        # Third round is the last automatic one while two are used.
        self.assertTrue(rb.allowed(lines[:-2])['code']['last_automatic'])

    def test_3_explicit_two_rounds_cover_both_phases(self):
        self.assertEqual(rb.left_for_code(2, 2), 0)
        self.assertEqual(rb.left_for_code(3, 2), 1)
        lines = [review(1, 'document'), rnd(1, ph='document'), review(2, 'document'), rnd(2, ph='document')]
        a = rb.allowed(lines, explicit_limit=2)
        self.assertFalse(a['code']['automatic_allowed'])
        self.assertFalse(a['document']['automatic_allowed'])
        self.assertEqual(a['shared']['used'], 2)

    def test_4_user_round_past_limit_does_not_count_and_ids_keep_counting(self):
        lines = []
        for k in range(1, 4):
            lines += [review(k, 'code'), rnd(k, ph='code')]
        lines += ['Ruling: round R4 started by the user past the limit - one more - cost',
                  review(4, 'code'), rnd(4, ph='code')]
        a = rb.allowed(lines)
        self.assertEqual(a['code']['used'], 3)
        self.assertEqual(a['next_review_id'], 'R5')
        lines += [review(5, 'code'), rnd(5, ph='code')]
        self.assertEqual(rb.allowed(lines)['next_review_id'], 'R6')

    def test_user_round_ids_are_not_renumbered_from_one(self):
        lines = [review(n, 'code') for n in range(1, 6)] + ['Ruling: round R6 started by the user past the limit - w - c']
        self.assertEqual(rb.next_review_id(lines), 'R7')


class Extra(unittest.TestCase):
    def test_round_without_phase_takes_nearest_review_phase(self):
        lines = [review(1, 'document'), rnd(1), review(2, 'code'), rnd(2)]
        self.assertEqual(rb.phase(lines, 1), 'document')
        self.assertEqual(rb.phase(lines, 3), 'code')
        self.assertEqual(rb.count(lines), {'document': 1, 'code': 1})

    def test_round_without_phase_and_review_counts_against_both(self):
        lines = [rnd(1)]
        self.assertEqual(rb.phase(lines, 0), 'both')
        self.assertEqual(rb.count(lines), {'document': 1, 'code': 1})
        self.assertEqual(rb.allowed(lines, explicit_limit=2)['shared']['used'], 1)

    def test_re_review_continues_its_phase(self):
        lines = [review(1, 'document'), review(2, 're-review'), rnd(2)]
        self.assertEqual(rb.phase(lines, 1), 'document')
        self.assertEqual(rb.count(lines), {'document': 1, 'code': 0})

    def test_new_reviewer_does_not_reset(self):
        lines = [review(1, 'code'), rnd(1), 'Review R2: S tree %s reviewer other mode code' % SHA, rnd(2)]
        self.assertEqual(rb.count(lines)['code'], 2)

    def test_explicit_limit_is_shared_not_per_phase(self):
        lines = [review(1, 'document'), rnd(1, ph='document'), review(2, 'code'), rnd(2, ph='code')]
        self.assertTrue(rb.allowed(lines)['code']['automatic_allowed'])
        a = rb.allowed(lines, explicit_limit=2)
        self.assertEqual(a['shared']['used'], 2)
        self.assertFalse(a['code']['automatic_allowed'])

    def test_phase_of_unrelated_line_is_none(self):
        self.assertIsNone(rb.phase(['Task 1: pending'], 0))


class Cli(unittest.TestCase):
    def run_cli(self, text, *args):
        return subprocess.run([sys.executable, str(HERE / 'round_budget.py'), *args], input=text,
                              capture_output=True, text=True)

    def test_exit_codes(self):
        ok = self.run_cli(review(1, 'code') + '\n' + rnd(1, ph='code') + '\n')
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(json.loads(ok.stdout)['code']['used'], 1)
        full = ''.join(rnd(k, ph='code') + '\n' for k in range(1, 4))
        self.assertEqual(self.run_cli(full).returncode, 1)
        self.assertEqual(self.run_cli('', '--limit', '0').returncode, 2)


if __name__ == '__main__':
    unittest.main()
