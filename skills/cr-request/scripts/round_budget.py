#!/usr/bin/env python3
"""Per-phase automatic round budgets of the review loop (rule: round-budgets.md).

Reads journal lines (`Review`, `Round review`, `Ruling: round ... past the limit`) and
reports how many automatic rounds each phase used and whether another one is allowed.
Reads stdin or files; prints JSON; exit 0 when another automatic round is allowed in both
phases, 1 when a phase needs the user, 2 on usage errors.
"""
import argparse
import json
import re
import sys

DEFAULT_LIMIT = 3
REVIEW = re.compile(r'^Review R(\d+):.*\bmode (code|document|re-review)\b')
ROUND = re.compile(r'^Round review (\d+):\s*(?:(document|code)\b)?')
PAST_LIMIT = re.compile(r'^Ruling: round R(\d+) started by the user past the limit\b')
BOTH = 'both'


def _clean(lines):
    return [l.strip() for l in lines]


def phase(lines, i):
    """Phase of line `i`: 'document', 'code', 'both' (unknown, counts against both) or None."""
    lines = _clean(lines)
    last = BOTH  # phase of the nearest Review line seen so far
    for k, line in enumerate(lines[:i + 1]):
        m = REVIEW.match(line)
        if m:
            last = last if m.group(2) == 're-review' else m.group(2)
            if k == i:
                return last
            continue
        m = ROUND.match(line)
        if m and k == i:
            return m.group(2) or last
    return None


def _rounds(lines):
    """Yield (phase, user_started) for every `Round review` line, in order."""
    lines = _clean(lines)
    pending = False
    for i, line in enumerate(lines):
        if PAST_LIMIT.match(line):
            pending = True
        elif ROUND.match(line):
            yield phase(lines, i), pending
            pending = False


def count(lines):
    """Automatic rounds per phase; user-started rounds past the limit do not count."""
    out = {'document': 0, 'code': 0}
    for ph, user in _rounds(lines):
        if user:
            continue
        for key in out:
            if ph in (key, BOTH):
                out[key] += 1
    return out


def _shared_used(lines):
    return sum(1 for _, user in _rounds(lines) if not user)


def next_review_id(lines):
    """Next `R<n>`: IDs keep counting across phases and after user-started rounds."""
    ids = [int(m.group(1)) for l in _clean(lines) for m in (REVIEW.match(l), PAST_LIMIT.match(l)) if m]
    return 'R%d' % (max(ids, default=0) + 1)


def _entry(used, limit):
    remaining = max(0, limit - used)
    return {'used': used, 'limit': limit, 'remaining': remaining,
            'automatic_allowed': remaining > 0, 'last_automatic': remaining == 1}


def allowed(lines, explicit_limit=None):
    """Budget state per phase. An explicit limit covers both phases together (`shared`)."""
    if explicit_limit is None:
        counts = count(lines)
        return {'document': _entry(counts['document'], DEFAULT_LIMIT),
                'code': _entry(counts['code'], DEFAULT_LIMIT), 'shared': None,
                'next_review_id': next_review_id(lines)}
    shared = _entry(_shared_used(lines), explicit_limit)
    return {'document': dict(shared), 'code': dict(shared), 'shared': shared,
            'next_review_id': next_review_id(lines)}


def left_for_code(explicit_limit, document_rounds_planned):
    """Rounds an explicit shared limit leaves for the code review; say it before the first document review."""
    return max(0, explicit_limit - document_rounds_planned)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('files', nargs='*', help='journal files (default: stdin)')
    p.add_argument('--limit', type=int, help='round count the user gave for the whole chain')
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if args.limit is not None and args.limit < 1:
        print('error: --limit must be positive', file=sys.stderr)
        return 2
    try:
        lines = []
        for f in args.files or ['-']:
            lines += (sys.stdin if f == '-' else open(f, encoding='utf-8')).read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        print('error: %s' % e, file=sys.stderr)
        return 2
    result = allowed(lines, args.limit)
    print(json.dumps(result))
    return 0 if result['document']['automatic_allowed'] and result['code']['automatic_allowed'] else 1


if __name__ == '__main__':
    sys.exit(main())
