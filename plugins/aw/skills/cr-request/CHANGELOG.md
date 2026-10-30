# Changelog

## [0.0.10] - 2026-10-29

- A re-review may report a finding outside the fix diff only when the fix caused it,
  tagged `[regression]` with evidence of the link, in `SKILL.md`, the `Re-review kind` of
  `references/brief.md`, and `references/lenses.md`; the finding header has a
  `[regression]` slot next to `[plan-mandated]`. Older code stays out of scope, and a
  rejected finding stays closed.
- The reviewer never runs a test that writes into the tree, reaches an external service,
  or needs credentials; it lists such a test under `Not checkable from the diff` with the
  reason.
- `references/brief.md` names the object the CI review is published as: a PR review
  (event `COMMENT`) or a conversation comment, and which one the PR list counts; the
  sentence sits after the `Not checkable` paragraph, outside what `cross-cr` sends to
  reviewers (request 20261025-1922).
- Record host: the plan, else the spec's `## Verification record`, else none; `Review`,
  `Finding`, and `Round` lines go to that host. The fingerprint uses the `Committed tree`
  or `Working tree` recipe by boundary and leaves the host out.
- Round rule: only automatic rounds count; a user-started round past the limit runs once
  and is recorded with a `Ruling` line; the same cause twice escalates in any round.
- `--auto` starts `cr-received` or `verify` in the same turn and stops at the user's
  decisions, the Round rule, and before the `finalize` option choice; `Next step` lines,
  the CI one included, never carry it. A chain that `finalize`, `cross-cr`, or
  `plan-craft` started for a step it owns returns to that skill: a clean plan review goes
  back to `plan-craft` and `implement`, not to `verify`.
- The skill never creates a spec's `## Verification record`; until `implement` or `verify`
  does, the `Review` and `Finding` lines stay in the result. A clean document review ends
  with `implement - <plan path>` or `plan-craft - <spec path>`, not `verify`.
- `Uncommitted state` leaves the record host out and hashes each untracked file with the
  same two commands `cr-received` uses.
- CI `Next step` line (request 20261030-0141): a clean review without a full
  `Verify: PASS` on the tree ends with
  ``Next step: `/verify <plan path>` -> `/finalize` squash``, or
  ``Next step: `/verify` -> `/finalize` squash`` when neither the PR description nor the
  diff names a plan, instead of a bare `/verify` with a reason; a review with findings
  ends with `` Next step: `/cr-received PR #<n>` `` and no reason.
  The "CI footer grammar" regular expression accepts arguments inside the skill span, a
  ` -> ` tail, and a line without a reason, and has samples for the new forms. The local
  `Next step: <skill> - <reason>` grammar is unchanged.
- New `references/compact.md` (request 20261030-0208) describes the compact result the CI
  review posts: the one-row `Intent | System | Craft | Critical | Important | Minor`
  table, the `Readiness` line, one collapsed `<details>` block with `Findings`, `Target`,
  `Axis verdicts`, and `Set aside, open questions, and review gaps`, the blank lines
  around `<details>`, and the footer. `SKILL.md` links it; the workflow prompt keeps its
  full description of the format until a release tag carries this file.

## [0.0.9] - 2026-10-28

- The fingerprint recipe in `references/tree-fingerprint.md` records the full object ID
  (40 hex characters in a SHA-1 repository, 64 in a SHA-256 one) and removes its
  temporary index with a `trap` on exit.

## [0.0.8] - 2026-10-27

- The CI footer grammar follows the `claude-review.yml` validator: every `\r` removed,
  blank lines dropped, trailing whitespace stripped, the regexes stated for bash with a
  note on other dialects, and the fixture table matches the validator (review R1-F2 on
  PR #14).
- `references/brief.md` gives the CI footer grammar: POSIX extended regular expressions
  for the signature and the `Next step` line, and accepted and rejected samples a
  workflow validator can use as fixtures. The grammar is part of the contract: a change
  to it changes the contract, and the review workflow updates its validator and pinned
  revision with it (request 20261026-2315).
- The invocable `Next step` form (``Next step: `/<skill>` · <reason>``), introduced in
  0.0.6 for the CI body, is now fixed by that grammar; the switch of every aw skill's
  local `Next step` lines is left for a separate decision (request 20261024-2217).
- Journal lines go inside the record's `text` block, before its closing fence, never
  after it (request 20261025-1800).

## [0.0.7] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; version bump only, the text is unchanged.

## [0.0.6] - 2026-10-26

- A closing line the caller requires now goes right before the `Next step` line, which
  stays the very last line. The CI auto-review body ends with
  ``Reviewed with: `/cr-request` <version> skill``, then
  ``Next step: `/cr-received` · <n> findings to rule on``; the workflow may append
  ` · In <m> min <s> sec` to the signature line.

## [0.0.5] - 2026-10-26

- Dispatch the reviewer in the foreground in a non-interactive run (`claude -p`, a CI
  action) and write the result before the final message, which ends the run.
- A closing line the caller requires stays the very last line; the CI auto-review
  signature is now ``Reviewed with: `/cr-request` <version> skill``.

## [0.0.4] - 2026-10-22

- Add a summary to the result: findings per severity and merge readiness, next to
  the verdicts; severities are limited to `Critical`, `Important`, and `Minor`.
- Open the description with "You MUST use this when", say it replaces devflow
  `review-request`, and cover spec and plan review.
- Add a `Tree` field to the identity record for every boundary, with the shared
  fingerprint recipe in `references/tree-fingerprint.md`.
- Add the base-to-working-tree boundary: one diff from the merge-base to the files on
  disk, plus untracked files.
- Take chain inputs: spec and plan paths, `Base` from the execution record, scope
  `task <n>` or `branch`, and `Verify:` lines as signals.
- Name findings `R<n>-F<k>` (`R<n>-<reviewer>-F<k>` with several reviewers) and never
  renumber earlier rounds.
- Append `Review`, `Finding`, and `Round review <n>` lines to the plan's execution record
  when the plan is known; the full result stays in the response.
- Add the round rule shared by the chain.
- Add the re-review mode: each previous finding is `ADDRESSED` or `NOT ADDRESSED`, new
  findings only inside the fix diff, rejected findings stay closed without new evidence.
- Add the document mode for a spec or plan: `sha256` identity, `§<heading>` locations,
  and document lenses for the same three axes.
- Report `REVIEWER UNAVAILABLE` instead of a pass when the reviewer fails; an unchanged
  target after a clean result gets one line and a suggestion of another reviewer.
- End every result with a `Next step` line; in the CI auto-review it goes right before
  the closing `Reviewed with: cr-request skill` line.
- Scan the diff stat and untracked files for possible secrets before sending any diff.
- Add a `When not to use` section.
- Brief: add the `Reviewer model` field; the reviewer model is always named.
- Brief: add the `Review kind`, `Review round`, `Scope`, `Spec`, `Plan`, and
  `Previous findings` fields.
- Brief: add `Requirements from the conversation` as a source separate from the spec.
- Brief: add `Requirements not checkable from the diff`, and the matching result field,
  kept apart from `UNASSESSED`.
- Brief: add `Others' changes in scope (not assessed)`; the reviewer gives them no
  verdict or finding.
- Brief: keep the reviewer unbiased - no severity discount for the author's rationale,
  and plan-required defects are findings marked `plan-mandated`.
- Brief: add the reviewer test policy - no full suite rerun, at most one focused test
  for a specific doubt.
- Brief: add evidence attribution - `Evidence source` per finding and an
  `Evidence attribution` field in the result.
- Brief: add instructions for the re-review and document kinds, and `§<heading>`
  locations.
- Brief: state that the skill adds the closing lines, with the CI order `Next step`,
  then `Reviewed with: cr-request skill`.

## [0.0.3] - 2026-10-18

- Hand the review result to `cr-received`, the new name of `cr-receive`.

## [0.0.2] - 2026-10-18

- Hand the review result to `cr-receive`.
- Accept a prepared target: an identity record with the diff, log, and base copies
  captured by the caller, for runs without Git access.

## [0.0.1] - 2026-10-18

- Initial release: target pinning, intent gathering, risk-sized depth, a reviewer brief
  with Intent, System, and Craft verdicts, and evidence-backed findings with confidence.
