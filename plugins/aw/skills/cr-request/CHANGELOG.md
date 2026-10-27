# Changelog

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
