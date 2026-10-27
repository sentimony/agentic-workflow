# Changelog

## [0.0.4] - 2026-10-27

- An accepted fix that materially changes an approved spec sets its `Status` back to
  `draft` in the same edit and routes to `specify`, which asks for a new explicit yes; a
  typo-level fix keeps `approved`. A new `Approval invariant` section is shared with
  `specify`, `plan-craft`, and `implement` (request 20261027-0206).
- Journal lines go inside the record's `text` block, before its closing fence, never
  after it (request 20261025-1800).

## [0.0.3] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; version bump only, the text is unchanged.

## [0.0.2] - 2026-10-22

- Description opens with "You MUST use this when", names the trigger contexts (review
  findings, PR comments, CI or static-analysis output, reviewer suggestions), and states
  that the skill replaces devflow review-resolution.
- Identity record gains `Tree: <fingerprint>` from the shared tree fingerprint recipe
  (`references/tree-fingerprint.md`); decisions are bound to it.
- The report ends with the chain return block (changed paths, previous verification,
  checks to rerun, re-review, blocking and deferred items, rulings, route) and a
  `Next step` line; a document variant covers spec and plan reviews.
- With a known plan, appends `Received`, `Ruling`, `Deferred`, and `Round` lines to its
  execution record.
- Step 8 uses the shared Round rule and the `Round review <n>` journal counter instead of
  its own limits; a re-review always goes to a fresh reviewer with a full brief.
- Idempotent repeat call on an already resolved review, reviewer-prefixed IDs
  (`R<n>-F<k>`, `R<n>-<reviewer>-F<k>`), owner and tracking place required for `DEFER`,
  triage order, a ruling for every set-aside row, and evidence forms for findings on a
  spec or plan.
- New `references/return.md`; cr-request result fields and dispositions move to
  `references/records.md` to keep the body short.

## [0.0.1] - 2026-10-18

- First release under this name; awf 0.0.2 shipped the same skill as `cr-receive`.
- Initial release: intake shaped by the cr-request result contract, anchoring findings to
  the reviewed target, one record per finding, separate verification of claim and remedy,
  five dispositions, dependency-ordered minimal fixes with per-finding evidence, a bounded
  re-review loop, and factual replies.
