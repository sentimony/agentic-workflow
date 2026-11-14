# Changelog

## [0.0.22] - 2026-11-14

1. Owner adapter: `owner_context.target: working` reviews uncommitted work through the private working tree (identity boundary `working-tree`, base commit required); the embedded diff carries untracked content with the same secret, lock-file, binary, non-UTF-8 and outside-symlink filters, and freshness recomputes the tree. `committed` is unchanged. `--metrics` reports `brief_metrics` for diagnostics; the core rejects extra fields in an accepted `prepare` response, so it is not part of the default payload (`20261107-0020`).
2. `scripts/round_budget.py` with tests counts per-phase round budgets; the Round rule section references it instead of repeating the per-phase text, behavior unchanged (`20261030-0851`).
3. Reads `Snapshot` lines for the whitespace check and reports `Delta` (`20261101-1158`).

## [0.0.21] - 2026-11-13

1. Flat layout: reference files moved next to SKILL.md; no content change.

## [0.0.20] - 2026-11-13

1. `Next step` inside a review loop needs no user decision under `--auto`; agreed independent work starts in the same turn while a transition awaits the user (`20261024-2324`).
2. `## Scoped tree` recipe added to the shared `tree-fingerprint.md` copy.

## [0.0.19] - 2026-11-13

1. Description rewritten as a thesis followed by `Use when ...` without `You MUST`, cutting
   its context cost (`20261111-2220`).

## [0.0.18] - 2026-11-12

1. A re-review brief is narrow by default: the fix diff, the `Received` and `Ruling` lines
   of the round, the sections the diff touches and the repository files needed to check a
   fact; a whole document is read again only when no diff exists, and the result says so
   (`20261030-0851`).
2. Review budgets are kept per phase, `document` and `code`: a new journal form
   `Round review <n>: [document|code] <cause>`, no reset when the reviewer, model or mode
   changes, `R<n>` IDs keep counting, and one explicit user round count covers both phases
   (`20261030-0851`).
3. The failure-paths lens separates a test that plans the operational error from a check
   of the success conditions and does not ask to remove runtime error handling only for the
   test (`20261031-2048`).
4. Whitespace of a prepared target is checked through a private index with an explicit
   inventory that includes untracked files (`scripts/target_whitespace.py`, with tests);
   a path that was dirty before the work is compared with its captured original after a
   hash check, and a missing or unreadable before-snapshot is `unverified` instead of being
   assumed to be `HEAD` (`20261101-1158`).
5. A re-review for a reviewer in an isolated clone receives the diff between the recorded
   trees as unchanged `git diff` stdout, checked with `git apply --check --reverse`, and
   reads files in a clone of the current commit instead of resolving a tree ID that may
   exist only in the host repository (`20261101-1208`).
6. The owner adapter embeds the diff of the committed boundary for a reviewer without a
   shell when the host sets `embed_diff`: byte count and SHA-256, the left-out paths
   (possible secret by name, lockfile, binary file), a 262144-byte limit that blocks with
   a reason instead of cutting, a reverse-apply check against the target tree, a block
   when the diff is not valid UTF-8, and quoted names for paths with control characters
   (`20261107-0020`).
7. `--exclude <path>` names untracked files outside the change as a coverage gap and lets
   them pass the clean-target check, and `previous_tree` gives a re-review only the fix
   diff, with a note and the full diff when that tree is missing (`20261107-0020`,
   `20261101-1208`).

## [0.0.17] - 2026-11-07

1. Comments name `transfer-context`, the new name of `context-transfer`.
2. Decouple review presentation and transport from a specific caller; preserve full
   local archives and support caller-specified output requirements.

## [0.0.16] - 2026-11-07 - [0.0.22](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.22)

1. Add a prose-only review kind to the brief and the review kinds list: the same read-only
   reviewer limited to the text of a document or article, recorded as `mode document`,
   with code reported as UNASSESSED (20261003-0939). A clean prose-only review ends with
   `Next step: none - <document path> reviewed`.

## [0.0.15] - 2026-11-04 - [0.0.20](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.20)

1. Review the whole document when neither the previous tree nor head provides a usable
   diff for a re-review, and state in the result that the diff was unavailable.

## [0.0.14] - 2026-11-04 - [0.0.19](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.19)

1. Trace assertions across callback, hook, and handler boundaries so a broad catch cannot
   turn a failed assertion into a passing test (20261031-2048).
2. Add the `Status R<n>: R<m>-F<k> ADDRESSED | NOT ADDRESSED - <evidence>` journal line,
   count `NOT ADDRESSED` findings in the `Next step` number, and stop requiring
   `Merge readiness` in document reviews, in the brief and in the owner adapter
   (20261030-0854).
3. Write the skill in local `Next step` lines as inline code in invocation form
   (`/<skill>` in Claude Code, `$<skill>` in Codex) (20261024-2217).
4. Save the local review archive to `~/.sentimony/agentflow/cr-request/<project>/<run-id>/`
   instead of `.cross-review/local/` with an `info/exclude` entry; the safety checks, unique
   run IDs and the `INCOMPLETE` handoff on a failed write stay. `scripts/project_slug.py`
   prints the archive root (`20261104-0706`).

## [0.0.13] - 2026-11-01

1. Use the shared manual/auto stage transition contract and return orchestrated results
   to resolve-issue; preserve current permissions, critical user decisions and delivery gates.

## [0.0.12] - 2026-11-01 - [0.0.17](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.17)

1. Keep HEAD provenance separate from content freshness, preserving review validity
   after commits that only change the excluded record host.
2. Bind receiver intake before launch; preserve immutable original evidence and
   report post-fix committed/working/document identities after accepted fixes.

3. Add the installed owner adapter for standalone cross-agent protocol 1; retain
   target freshness, complete review grammar, qualified IDs and intake in this workflow.
4. Reject partial domain results and persist only host-allowlisted review artifacts.

5. Retire active cross-cr routes in favor of standalone cross-agent and its
   workflow owner, preserving review round and reviewer continuity.

## [0.0.11] - 2026-10-30

- Align the automatic outward exception with authorized defer actions and the bounded REJECT reply.
- Separate yngwald review/issue/reply/ledger publication from API-only thread resolve
  as `github-actions[bot]`. Keep the PAT unchanged, isolate the short-lived write
  GITHUB_TOKEN from reviewers and model-output parsers, and require independent
  completion readback while preserving yngwald source-author checks.

- Share a compact local/CI result: verdicts, severity counts, readiness, and next step;
  local calls link the full host-owned review archive, while CI retains one Details
  block and the unchanged two-line footer grammar.
- Define `review-actions` v1: nullable current source IDs in the agent draft,
  confirmed previous identities, independent addressed/defer states, and a canonical
  ledger in the publisher's own review body after real review IDs exist. Track action
  progress and API-backed host disposition events; `REJECT` of a finding stays
  separate from `DECLINED` defer, with unknown history reported explicitly.
- Archive completed local reviews under the session repository's
  `.cross-review/local/<run-id>/`, with private permissions, Git exclusion, a shared
  root resolver, and `INCOMPLETE` on archive failure. The host writes archives only
  after the reviewer finishes; snapshots and briefs omit them. The owner accepts
  possible reads by same-host subagents and CLI reviewers without mandatory deny-read.
- Permit at most one focused test after a side-effect check; tests that write run in
  a private isolated copy with an original-status/fixture-hash comparison. Keep
  credentials, production access, and external writes outside that permission;
  unsafe or unavailable checks remain review gaps. Include a hermetic fixture recipe.
- Preserve unfavorable verdicts without findings and surface their evidence gap for
  a user ruling instead of inventing fixes or a PASS.

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
- CI `Next step` line (request 20261030-0141): a clean review always ends with
  ``Next step: `/verify <plan path>` -> `/finalize` squash``, or
  ``Next step: `/verify` -> `/finalize` squash`` when neither the PR description nor the
  diff names a plan, instead of a bare `/verify` with a reason; a review with findings
  ends with `` Next step: `/cr-received PR #<n>` `` and no reason. CI cannot match a
  `Verify` line (the host is outside the repository, or `HEAD^{tree}` includes it), so
  the `/finalize` row of the CI table is gone.
  The "CI footer grammar" regular expression accepts arguments inside the skill span, a
  ` -> ` tail, and a line without a reason, and has samples for the new forms. The local
  `Next step: <skill> - <reason>` grammar is unchanged.
- New `references/compact.md` (request 20261030-0208) describes the compact result the CI
  review posts: the one-row `Intent | System | Craft | Critical | Important | Minor`
  table, the `Readiness` line, one collapsed `<details>` block with `Findings`, `Target`,
  `Axis verdicts`, and `Set aside, open questions, and review gaps`, the blank lines
  around `<details>`, and the footer. `SKILL.md` links it; the workflow prompt keeps its
  full description of the format until a release tag carries this file.
- Under `--auto`, a clean document review starts `implement` or `plan-craft` in the same
  turn, and a clean review of a spec that is not approved ends with
  `Next step: none - <spec path> is a draft, awaiting approval` instead of `plan-craft`.
  A plan review that `plan-craft` started returns to it on `REVIEWER UNAVAILABLE` too, as
  `plan-craft` goes on to `implement` then.

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

[0.0.13]: https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.18
