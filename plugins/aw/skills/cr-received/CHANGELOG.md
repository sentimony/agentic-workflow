# Changelog

## [0.0.7] - 2026-10-30

- Align review intake, gate evidence, and the narrow authorized automatic review replies.

## [0.0.6] - 2026-10-29

- `--auto` in the arguments starts the next local step (`verify`, `plan-craft`) in the
  same turn; it stops on a user decision, the Round rule, `ESCALATE`, `INCOMPLETE` or
  `BLOCKED`, and before the `finalize` choice; a chain that `finalize`, `cross-cr`, or
  `plan-craft` started returns to that skill.
- Each round's fixes and record lines are committed locally as
  `Address R<n> findings: <IDs>`, with only the session's own paths and under the commit
  policy of the user's and project's instructions.
- The Round rule counts only automatic rounds; a round the user starts past the limit runs
  once and is recorded with a `Ruling`; the same cause twice always escalates.
- An `ESCALATE` no longer holds back independent records, and it stays open in `Blocking`
  across rounds until a `Ruling: R<n>-F<k> escalation decided` line closes it.
- A `Ruling: R<n>-F<k> superseded by ...` line records an accepted fix that a later task,
  finding, or marker removed on purpose.
- Failing checks are classed as `caused by fix`, `pre-existing`, `environment`, `flaky`,
  or `tool unavailable`; only a passing check resolves a finding. A test is shown to fail
  without its fix in a temporary detached worktree, never with `git stash`.
- A ruling to leave code as it is leaves a durable trail (a comment by the line and, for
  the owner's decision or after the user's yes, a sentence in `AGENTS.md`); the return
  block gains `Durable rulings: <paths or none>`.
- Without a plan, record lines go to the spec's `## Verification record`, and appending
  there does not reset the spec's approval. The anchor uses the `## Committed tree`
  fingerprint recipe; a review of an uncommitted boundary keeps its identity only while
  `HEAD` and the uncommitted state (without the record host, by the same commands as
  `cr-request`) are unchanged. `Previous verification` is `stale` whenever `Changed paths`
  is not `none`, and only a `Commits` line that says `allowed` or `forbidden` answers the
  commit-policy question.
- The argument may be several review paths (the `cross-cr` findings line lists one per
  reviewer), or `PR #<n>`, the form the CI review's `Next step` line passes: the
  latest review on that pull request, the CI auto-review by default, read through a tool
  the user already configured.

## [0.0.5] - 2026-10-28

- The fingerprint recipe in `references/tree-fingerprint.md` records the full object ID
  (40 hex characters in a SHA-1 repository, 64 in a SHA-256 one) and removes its
  temporary index with a `trap` on exit.

## [0.0.4] - 2026-10-27

- The approval invariant says that after the new yes `plan-craft` revises the existing
  plan in place instead of writing a second one (review R1-F1 on PR #14).
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
