import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan_structure as ps  # noqa: E402

TEMPLATE = (HERE.parent / 'plan-template.md').read_text(encoding='utf-8')

PLAN = '''# Demo - implementation plan

**Spec:** none

**Goal:** Demo.

**Architecture:** Small.

**Stack:** python

**Base check:** project default

**Execution:** unset

## Global constraints

1. Keep it small.

## Review focus

Look at the parser first.

## Acceptance criteria

1. AC1: it works.

## Files

| File | Change | Task |
| --- | --- | --- |
| `a.py` | new | 1 |

## Tasks

### Task 1: First

Body mentions `## Review focus` in a span.

```text
## Not a heading
```

**Covers:** AC1

## Short conclusion

1. Done.

## Next step

```text
go
```

## Execution record

```text
Base: unset
Task 1: pending
```
'''


def naive_replace(text, title, body):
    """Mutation: a replacement that stops at the NEXT-NEXT heading and swallows one `##`."""
    inv = [h for h in ps.inventory(text) if h[0] == 2]
    i = next(k for k, h in enumerate(inv) if h[1] == title)
    lines = text.splitlines()
    return '\n'.join(lines[:inv[i][2] + 1] + ['', body, ''] + lines[inv[i + 2][2]:]) + '\n'


class Structure(unittest.TestCase):
    def test_lost_intermediate_heading_fails_with_constraints_and_criteria_intact(self):
        after = naive_replace(PLAN, 'Global constraints', '1. Keep it small.')
        self.assertIn('1. Keep it small.', after)
        self.assertIn('AC1: it works.', after)
        problems = ps.check(PLAN, after)
        self.assertEqual(problems, ['heading lost: ## Review focus'])
        self.assertIn('required heading missing: ## Review focus', ps.required(after, TEMPLATE))

    def test_correct_replacement_keeps_inventory(self):
        after = ps.replace_section(PLAN, 'Global constraints', '1. New rule.')
        self.assertIn('1. New rule.', after)
        self.assertNotIn('Keep it small', after)
        self.assertEqual(ps.check(PLAN, after), [])
        self.assertEqual(ps.required(after, TEMPLATE), [])

    def test_neighbours_untouched(self):
        after = ps.replace_section(PLAN, 'Review focus', 'New focus.')
        for keep in ('1. Keep it small.', 'AC1: it works.', '| `a.py` | new | 1 |'):
            self.assertIn(keep, after)

    def test_nested_heading_belongs_to_section_and_survives_other_edits(self):
        after = ps.replace_section(PLAN, 'Review focus', 'New focus.')
        self.assertIn('### Task 1: First', after)
        removed = ps.replace_section(PLAN, 'Tasks', 'None.')
        self.assertIn('heading lost: ### Task 1: First', ps.check(PLAN, removed))
        self.assertEqual(ps.check(PLAN, removed, intended={'Task 1: First'}), [])

    def test_fenced_and_span_headings_ignored(self):
        titles = [t for _, t, _ in ps.inventory(PLAN)]
        self.assertNotIn('Not a heading', titles)
        self.assertEqual(titles.count('Review focus'), 1)

    def test_longer_fence_closes_only_with_longer_fence(self):
        text = '# T\n````md\n```\n## Inner\n```\n````\n## Real\n'
        self.assertEqual([t for _, t, _ in ps.inventory(text)], ['T', 'Real'])

    def test_formatting_changes_do_not_change_tasks_or_record(self):
        reformatted = PLAN.replace('\n\n## Tasks', '\n\n\n\n## Tasks').replace('## Files', '  ## Files')
        self.assertEqual(ps.check(PLAN, reformatted), [])
        self.assertEqual(ps.required(reformatted, TEMPLATE), [])

    def test_level_change_is_a_loss(self):
        after = PLAN.replace('## Review focus', '### Review focus')
        self.assertTrue(ps.check(PLAN, after))

    def test_legacy_does_not_require_execution_record(self):
        old = PLAN.split('## Execution record')[0]
        self.assertIn('required heading missing: ## Execution record', ps.required(old, TEMPLATE))
        self.assertEqual(ps.required(old, TEMPLATE, legacy=True), [])

    def test_legacy_still_requires_other_headings(self):
        old = PLAN.split('## Execution record')[0].replace('## Review focus', 'Review focus')
        self.assertIn('required heading missing: ## Review focus', ps.required(old, TEMPLATE, legacy=True))

    def test_acceptance_criteria_optional(self):
        no_ac = PLAN.replace('## Acceptance criteria\n\n1. AC1: it works.\n\n', '')
        self.assertEqual(ps.required(no_ac, TEMPLATE), [])

    def test_missing_header_field_reported(self):
        self.assertIn('required header field missing: **Goal:**', ps.required(PLAN.replace('**Goal:**', 'Goal:'), TEMPLATE))


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / 'plan_structure.py'), *args],
                              capture_output=True, text=True)

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d, 'a.md'), Path(d, 'b.md')
            a.write_text(PLAN)
            b.write_text(naive_replace(PLAN, 'Global constraints', 'x'))
            r = self.run_cli('diff', str(a), str(b))
            self.assertEqual((r.returncode, r.stdout.strip()), (1, 'heading lost: ## Review focus'))
            self.assertEqual(self.run_cli('diff', str(a), str(b), '--allow-removed', 'Review focus').returncode, 0)
            self.assertEqual(self.run_cli('diff', str(a), str(a)).returncode, 0)
            self.assertEqual(self.run_cli('diff', str(a), str(Path(d, 'missing.md'))).returncode, 2)
            self.assertEqual(self.run_cli('required', str(a), '--template', str(HERE.parent / 'plan-template.md')).returncode, 0)
            self.assertEqual(self.run_cli('required', str(b), '--template', str(HERE.parent / 'plan-template.md')).returncode, 1)
            self.assertEqual(self.run_cli('bogus').returncode, 2)


if __name__ == '__main__':
    unittest.main()
