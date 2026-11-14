# Context digest

A `Verify` verdict is bound to two identities: the tree of the implementation
([tree-fingerprint.md](tree-fingerprint.md)) and the digest of the requirements context
(plan, spec, owner rulings). `scripts/context_digest.py <host-path>` prints the digest.

## What the digest sees

Input is UTF-8 with CRLF read as LF. A section ends at the next `## ` heading outside a
fenced block, or at the end of the file.

1. The record host without its record section (plan without `## Execution record`, spec
   without `## Verification record`).
2. For a plan, the spec named by its `Spec:` header (absolute path, or relative to the
   repo root), by the same rule, status line included. `Spec: none` adds nothing.
3. From the record sections, only the `Ruling:` and `Deferred:` lines, verbatim and in
   file order, except `Ruling: round ...` (written by `verify`) and `Ruling: no review ...`
   (written by `finalize` during the gate): appending them must not invalidate a `PASS`.

`Verify`, `Round`, `Review`, `Finding`, `Received`, `Task`, `Base`, `Root`, `Branch`,
`Commits`, and `Initial dirty state` lines are not part of the digest. Findings and
dispositions block through `record_gate.py --blockers` instead
([record-gate.md](record-gate.md)).

The hash is SHA-256 whatever the repository object format: `sha256:<64 hex>`. With no
record host the digest is `none`.

## Failure

The script exits 2 with empty stdout when the host or the named spec is missing or
unreadable, a record heading appears twice, or a fenced block is not closed. `verify`
then returns `BLOCKED (context digest failed: <reason>)` and writes no `Verify` line; the
`finalize` gate stops too. A `Verify` line without `context` (written before this
format) fails the gate with `context-missing`; it is never rewritten, a new `Verify` is
appended.
