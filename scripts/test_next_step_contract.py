"""Keeps the `Next step` contract of the review loop in sync across the skills that state it."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / 'skills'
LOOP = ('verify', 'cr-request', 'cr-received')
ALL = LOOP + ('finalize',)
# verify and finalize carry only the shared base rule; the loop sentences live in the two
# skills that start the loop's `Next step` lines.
LOOP_TEXT = ('cr-request', 'cr-received')
RUN_CONTRACT = SKILLS / 'resolve-issue' / 'run-contract.md'

INDEPENDENT = re.compile(
    r"While the next transition waits for the user's answer, start agreed independent work "
    r"from the session queue in the same turn; stop only when there is none\.")
MANUAL = re.compile(r"in manual mode the line stays the request of the transition")
BASE_MANUAL = re.compile(r"Without `--auto`, finish this meaningful stage and request its next transition;")
AUTO_LOOP = re.compile(r"a `Next step` that names such a skill needs no user decision under `--auto`")
POINT_4 = re.compile(r"^4\. Manual mode completes a stage and waits\.", re.M)


def norm(text):
    return re.sub(r'\s+', ' ', text)


def read(name):
    return (SKILLS / name / 'SKILL.md').read_text(encoding='utf-8')


def problems(name, text):
    """Contract violations of one skill text (empty list when it holds)."""
    flat = norm(text)
    out = []
    if not INDEPENDENT.search(flat):
        out.append('%s: no sentence about independent work while a question waits' % name)
    if not BASE_MANUAL.search(flat):
        out.append('%s: manual mode no longer finishes the stage and requests the transition' % name)
    if name in LOOP_TEXT:
        if not MANUAL.search(flat):
            out.append('%s: manual mode no longer keeps the line as the transition request' % name)
        if not AUTO_LOOP.search(flat):
            out.append('%s: no rule that a review-loop Next step needs no decision under --auto' % name)
    return out


class Contract(unittest.TestCase):
    def test_real_skills_hold_the_contract(self):
        for name in ALL:
            with self.subTest(skill=name):
                self.assertEqual(problems(name, read(name)), [])

    def test_run_contract_keeps_manual_point_4(self):
        self.assertRegex(RUN_CONTRACT.read_text(encoding='utf-8'), POINT_4)

    def test_run_contract_negative(self):
        text = RUN_CONTRACT.read_text(encoding='utf-8')
        mutated = POINT_4.sub('4. Manual mode continues on its own.', text)
        self.assertNotEqual(mutated, text)
        self.assertIsNone(POINT_4.search(mutated))


class Negative(unittest.TestCase):
    """Each mutation is made on an in-memory copy of the real text."""

    def mutate(self, name, pattern):
        text = read(name)
        mutated, n = pattern.subn('', norm(text))
        self.assertEqual(n, 1, 'pattern must match exactly once in %s' % name)
        return mutated

    def test_missing_independent_sentence_fails_everywhere(self):
        for name in ALL:
            with self.subTest(skill=name):
                if not INDEPENDENT.search(norm(read(name))):
                    self.skipTest('%s does not carry the sentence yet' % name)
                found = problems(name, self.mutate(name, INDEPENDENT))
                self.assertEqual(len(found), 1)
                self.assertIn('independent work', found[0])

    def test_missing_base_manual_rule_fails_everywhere(self):
        for name in ALL:
            with self.subTest(skill=name):
                found = problems(name, self.mutate(name, BASE_MANUAL))
                self.assertTrue(any('finishes the stage' in p for p in found))

    def test_missing_manual_sentence_fails_in_loop_skills(self):
        for name in LOOP_TEXT:
            with self.subTest(skill=name):
                found = problems(name, self.mutate(name, MANUAL))
                self.assertEqual(len(found), 1)
                self.assertIn('manual mode', found[0])

    def test_missing_auto_loop_rule_fails_in_loop_skills(self):
        for name in LOOP_TEXT:
            with self.subTest(skill=name):
                found = problems(name, self.mutate(name, AUTO_LOOP))
                self.assertEqual(len(found), 1)
                self.assertIn('--auto', found[0])

    def test_reworded_manual_mode_fails(self):
        for name in LOOP_TEXT:
            with self.subTest(skill=name):
                text = norm(read(name)).replace('in manual mode the line stays the request of the transition',
                                                 'in manual mode the line runs the transition')
                self.assertTrue(any('manual mode' in p for p in problems(name, text)))


if __name__ == '__main__':
    unittest.main()
