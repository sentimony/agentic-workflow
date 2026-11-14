# Record gate

`scripts/record_gate.py` reads a record host (plan or spec) and answers two questions for
`verify` and `finalize`. It uses only the standard library, writes nothing, and calls
neither `git` nor the network: the caller passes the fingerprint and the digest
([context-digest.md](context-digest.md)).

```text
record_gate.py --blockers <host>
record_gate.py --gate <host> --tree <fingerprint> --context <digest> [--integrate merge|squash|pr]
```

Exit codes: 0 no blockers or gate open, 1 blockers or gate closed, 2 error with empty
stdout (unreadable host, two record headings, an unparseable `Verify`, `Review`,
`Finding`, or `Received` line). Only lines inside the record's `text` block are read, in
the format of [journal.md](../implement/journal.md).

## Blockers

`--blockers` prints `{"blockers": [{"id", "severity", "why"}]}`. A blocker is a
`Finding R<n>-F<k>` with `Critical` or `Important` severity, of any round and any review
mode, with no `Received` disposition (`REJECT`, `OUTDATED`, `DEFER`, `ACCEPT`, `PARTIAL`),
a `Critical` finding whose last disposition is `DEFER` (a Critical finding escalates, it is
never deferred), or any `ESCALATE` with no later `Ruling: R<n>-F<k> escalation decided - ...`. The last
disposition of an ID wins. `ACCEPT` and `PARTIAL` close a blocker here because `verify`
proves the fix as a claim. The freshness of GitHub evidence for `DEFER` is not read:
`verify` and `finalize` keep that check.

## Gate

`--gate` prints `{"ok": bool, "reasons": [...]}` for `merge`, `squash`, and a ready `pr`
(`--integrate`, default `merge`). It needs: the latest `Verify` is `PASS`, `full`, not
`working` or `scoped`; its `tree` equals `--tree`; its `context` equals `--context`; a code
review for `merge` and `squash`; no open blocker; no pending `Re-review: needed`. In
the gate, `ACCEPT` and `PARTIAL` close a blocker only with a later full `Verify: PASS`.

A code review is a `Review` line with `mode code` (a re-review follows one, a document
review never counts) after the last re-approval marker (`Ruling: plan revised after spec
re-approval - ...` in a plan, `Ruling: spec re-approved - ...` in a spec record), else
after the plan's last `Base` line, or anywhere in a spec record. `Ruling: no review - ...`
after the same boundary counts in its place. `--integrate pr` does not need it.

## Refusal codes

| Code | Meaning |
| --- | --- |
| `no-verify` | the record has no `Verify` line |
| `verify-not-pass` | the latest verdict is not `PASS` |
| `verify-compact` | the latest `Verify` is `compact` |
| `verify-working` | the latest `Verify` judged the working tree |
| `verify-scoped` | the latest `Verify` is `scoped` |
| `tree-mismatch` | its tree differs from the current fingerprint |
| `context-missing` | its line has no `context` (written before this format) |
| `context-mismatch` | its digest differs from the current digest |
| `no-code-review` | `merge` or `squash` without a code review or `Ruling: no review` |
| `re-review-needed` | the latest `Re-review: needed` has no later `Review` |
| `open-blocker:<id>` | a blocker is open (one code per ID) |
