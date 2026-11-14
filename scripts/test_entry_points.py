"""Contract of the entry-point skills: resolve-issue, resolve-pr, resolve-ci, resume-task."""
import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / 'skills'
ENTRY = ('resolve-issue', 'resolve-pr', 'resolve-ci', 'resume-task')
# resolve-issue is an orchestrator: it returns stage results and has no `Next step` line.
NEXT_STEP_EXEMPT = ('resolve-issue',)
# Skills whose Security Model must deny own push, merge or forge writes.
DENY_WRITES = ('resolve-pr', 'resolve-ci', 'resume-task')

DENIAL = re.compile(r'performs no push, merge or forge write|writes nothing to the forge|changes nothing')
OWN_WRITE = re.compile(r'\b(pushes|merges|force-pushes|posts a comment|writes to the forge)\b', re.I)
ASK_AND_STOP = re.compile(r'Without [^.]*?, ask which [^.]*? and stop')
NEXT_FORM = re.compile(r'Next step: `/<skill>`|`Next step: none - ')


def norm(text):
    return re.sub(r'\s+', ' ', text)


def split(text):
    """(frontmatter dict, body before Security Model, Security Model section or None)."""
    m = re.match(r'---\n(.*?)\n---\n', text, re.S)
    front = {}
    for line in (m.group(1).splitlines() if m else []):
        if re.match(r'^[a-z-]+:', line):
            k, v = line.split(':', 1)
            front[k] = v.strip().strip('"')
    rest = text[m.end():] if m else text
    parts = re.split(r'^## Security Model\n', rest, maxsplit=1, flags=re.M)
    return front, parts[0], (parts[1] if len(parts) == 2 else None)


def problems(name, text):
    front, body, security = split(text)
    out = []
    if front.get('name') != name:
        out.append('%s: frontmatter name %r differs from the directory' % (name, front.get('name')))
    hint = front.get('argument-hint', '')
    if not re.match(r'^<[^>]+>', hint):
        out.append('%s: argument-hint has no required <...> argument first' % name)
    if ('[--auto]' in hint) != ('--auto' in body):
        out.append('%s: argument-hint and body disagree about --auto' % name)
    if security is None:
        out.append('%s: no Security Model section' % name)
    flat = norm(body)
    if not ASK_AND_STOP.search(flat):
        out.append('%s: no "ask which ... and stop" rule for a missing argument' % name)
    if name not in NEXT_STEP_EXEMPT and not NEXT_FORM.search(flat.split('The last line of the result')[-1]):
        out.append('%s: result does not end with a Next step line in the contract form' % name)
    if name not in NEXT_STEP_EXEMPT and 'The last line of the result' not in flat:
        out.append('%s: no last-line Next step rule' % name)
    if OWN_WRITE.search(flat):
        out.append('%s: body claims its own push, merge or forge write' % name)
    if name in DENY_WRITES and not (security and DENIAL.search(norm(security))):
        out.append('%s: Security Model does not deny own push, merge or forge writes' % name)
    return out


def read(name):
    return (SKILLS / name / 'SKILL.md').read_text(encoding='utf-8')


class EntryPoints(unittest.TestCase):
    def test_real_skills_hold_the_contract(self):
        for name in ENTRY:
            with self.subTest(skill=name):
                self.assertEqual(problems(name, read(name)), [])


class Negative(unittest.TestCase):
    """Mutations of an in-memory copy; each must fail for the described loss only."""

    def mutated(self, name, old, new):
        text = read(name)
        pattern = re.compile(re.escape(old).replace(r'\ ', r'\s+'))  # tolerate line wrapping
        self.assertEqual(len(pattern.findall(text)), 1, '%r must occur once in %s' % (old, name))
        return pattern.sub(lambda _: new, text)

    def test_missing_step_1_ask_and_stop(self):
        cases = {'resolve-pr': 'Without a PR argument, ask which PR to take and stop;',
                 'resolve-ci': 'Without a run, job or PR argument, ask which failure to take and stop.',
                 'resume-task': 'Without a plan, spec or branch argument, ask which task to resume and stop.',
                 'resolve-issue': 'Without an issue argument, ask which issue to take and stop;'}
        for name, sentence in cases.items():
            with self.subTest(skill=name):
                found = problems(name, self.mutated(name, sentence, 'Infer the target from the branch;'))
                self.assertEqual(len(found), 1)
                self.assertIn('ask which', found[0])

    def test_direct_command_instead_of_next_step(self):
        for name in ('resolve-pr', 'resolve-ci', 'resume-task'):
            with self.subTest(skill=name):
                text = read(name)
                head, tail = text.split('The last line of the result', 1)
                tail = tail.split('## Security Model')
                mutated = head + 'The last line of the result is the command `git push` to run.\n\n## Security Model' + tail[1]
                found = problems(name, mutated)
                self.assertEqual(len(found), 1)
                self.assertIn('Next step', found[0])

    def test_missing_security_model(self):
        for name in ENTRY:
            with self.subTest(skill=name):
                found = problems(name, self.mutated(name, '## Security Model', '## Notes'))
                self.assertTrue(any('no Security Model' in p for p in found))

    def test_own_push_claim(self):
        for name in ENTRY:
            with self.subTest(skill=name):
                text = read(name)
                mutated = text.replace('\n## Security Model', '\nThe skill pushes the branch when green.\n\n## Security Model', 1)
                found = problems(name, mutated)
                self.assertEqual(len(found), 1)
                self.assertIn('push, merge or forge write', found[0])

    def test_security_model_without_denial(self):
        cases = {'resolve-pr': 'performs no push, merge or forge write itself',
                 'resolve-ci': 'writes nothing to the forge',
                 'resume-task': 'changes nothing'}
        for name, phrase in cases.items():
            with self.subTest(skill=name):
                found = problems(name, self.mutated(name, phrase, 'may do anything'))
                self.assertEqual(len(found), 1)
                self.assertIn('does not deny', found[0])

    def test_wrong_name_and_auto_hint(self):
        for name in ENTRY:
            with self.subTest(skill=name):
                text = read(name)
                self.assertTrue(any('differs from the directory' in p
                                    for p in problems(name, text.replace('name: %s\n' % name, 'name: other\n', 1))))
        found = problems('resolve-ci', self.mutated('resolve-ci', 'argument-hint: "<run-url|pr-url|#number>"',
                                                       'argument-hint: "<run-url|pr-url|#number> [--auto]"'))
        self.assertEqual(len(found), 1)
        self.assertIn('--auto', found[0])
        found = problems('resolve-pr', self.mutated('resolve-pr', '"<pr-url|#number> [--auto]"', '"[<pr-url|#number>] [--auto]"'))
        self.assertTrue(any('required' in p for p in found))


if __name__ == '__main__':
    unittest.main()
