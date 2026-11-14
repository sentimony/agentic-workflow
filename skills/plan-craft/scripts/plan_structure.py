#!/usr/bin/env python3
"""Structural integrity of a plan document: heading inventory, section replacement, checks.

Exit codes of the CLI: 0 ok, 1 structural loss, 2 read or usage error.
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HEADING = re.compile(r'^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$')
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
HEADER_KEYS = ('Spec', 'Goal', 'Architecture', 'Stack', 'Base check', 'Execution')
# Sections that may legitimately be absent from a valid plan.
OPTIONAL = {'Acceptance criteria'}
LEGACY_OPTIONAL = {'Execution record'}


def _walk(text):
    """Yield (index, line, heading-or-None) with headings only outside fenced blocks."""
    fence = None
    for i, line in enumerate(text.splitlines()):
        m = FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
                fence = None
            yield i, line, None
            continue
        if m:
            fence = m.group(1)
            yield i, line, None
            continue
        h = HEADING.match(line)
        yield i, line, ((len(h.group(1)), h.group(2).strip()) if h else None)


def inventory(text):
    """Return [(level, title, line)] of headings; fenced blocks and inline mentions are skipped."""
    return [(h[0], h[1], i) for i, _, h in _walk(text) if h]


def replace_section(text, title, new_body):
    """Replace the body of section `title`; its boundary is the next heading of the same or a
    higher level, so nested headings belong to the section and are replaced with it."""
    inv = inventory(text)
    hits = [h for h in inv if h[1] == title]
    if len(hits) != 1:
        raise ValueError('section %r found %d times' % (title, len(hits)))
    level, _, start = hits[0]
    end = next((ln for lv, _, ln in inv if ln > start and lv <= level), None)
    lines = text.splitlines()
    end = len(lines) if end is None else end
    body = new_body.strip('\n').splitlines()
    out = lines[:start + 1] + [''] + body + [''] + lines[end:] if body else lines[:start + 1] + [''] + lines[end:]
    return '\n'.join(out) + ('\n' if text.endswith('\n') else '')


def check(before, after, intended=()):
    """Return problems: headings of `before` missing or re-leveled in `after`, unless intended."""
    a = Counter((lv, t) for lv, t, _ in inventory(before))
    b = Counter((lv, t) for lv, t, _ in inventory(after))
    problems = []
    for (lv, t), n in sorted(a.items()):
        if t in intended:
            continue
        if b[(lv, t)] < n:
            moved = [x for x in b if x[1] == t]
            problems.append('heading changed level: %s -> %s' % ('#' * lv + ' ' + t, '#' * moved[0][0] + ' ' + t)
                            if moved else 'heading lost: %s' % ('#' * lv + ' ' + t))
    return problems


def template_headings(template):
    """Level-2 headings of the skeleton block of plan-template.md."""
    lines = template.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith('````markdown')), None)
    if start is None:
        raise ValueError('no skeleton block in template')
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == '````'), None)
    if end is None:
        raise ValueError('skeleton block is not closed')
    return [t for lv, t, _ in inventory('\n'.join(lines[start + 1:end])) if lv == 2]


def required(text, template, legacy=False):
    """Return problems: required skeleton headings and header fields missing from the plan."""
    skip = OPTIONAL | (LEGACY_OPTIONAL if legacy else set())
    have = {t for lv, t, _ in inventory(text) if lv == 2}
    problems = ['required heading missing: ## %s' % t for t in template_headings(template)
                if t not in skip and t not in have]
    if not any(lv == 1 for lv, _, _ in inventory(text)):
        problems.append('required heading missing: # <title>')
    for key in HEADER_KEYS:
        if not re.search(r'^\*\*%s:\*\*' % re.escape(key), text, re.M):
            problems.append('required header field missing: **%s:**' % key)
    return problems


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as e:
        raise SystemExit('error: cannot read %s: %s' % (path, e)) from None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('diff')
    d.add_argument('before')
    d.add_argument('after')
    d.add_argument('--allow-removed', action='append', default=[], metavar='TITLE')
    r = sub.add_parser('required')
    r.add_argument('plan')
    r.add_argument('--template', required=True)
    r.add_argument('--legacy', action='store_true')
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        raise SystemExit(2 if e.code else 0) from None
    try:
        if args.cmd == 'diff':
            problems = check(_read(args.before), _read(args.after), set(args.allow_removed))
        else:
            problems = required(_read(args.plan), _read(args.template), args.legacy)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2
    except ValueError as e:
        print('error: %s' % e, file=sys.stderr)
        return 2
    for line in problems:
        print(line)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
