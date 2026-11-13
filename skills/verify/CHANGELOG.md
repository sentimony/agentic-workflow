# Changelog

## [0.0.13] - 2026-11-13

1. Description rewritten as a thesis followed by `Use when ...` without `You MUST`, cutting
   its context cost (`20261111-2220`).

## [0.0.12] - 2026-11-12

1. A weakening of a test or threshold that no `Ruling` or user decision covers and that
   breaks no claim is no longer a `FAIL`: the bar-check line reads `needs ruling`, the
   verdict is `INCOMPLETE` owned by the user, no `Round verify` line is written, and an
   unchanged tree is re-evaluated from the new `Ruling` without repeating the matrix
   (`20261024-2324`).
2. Whitespace of a `working` run is checked through a private index with an explicit
   inventory that includes untracked files; a path that was dirty before the work is
   checked against its captured original after a hash check, and without one it is
   `not verified` instead of being compared with `HEAD` (`20261101-1158`).

## [0.0.11] - 2026-11-07 - [0.0.22](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.22)

1. Name the skill in the `Next step` line as inline code in the host's invocation form
   (`/<skill>` in Claude Code, `$<skill>` in Codex); `none` stays plain text
   (`20261024-2217`).

## [0.0.10] - 2026-11-04 - [0.0.20](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.20)

1. Initialize required submodules at their pinned commits before clean-clone checks;
   report affected checks as not verified when initialization is unavailable.

## [0.0.9] - 2026-11-01

1. Use the shared manual/auto stage transition contract and return orchestrated results
   to resolve-issue; preserve current permissions, critical user decisions and delivery gates.

## [0.0.8] - 2026-11-01 - [0.0.17](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.17)

1. Replace active legacy cross-cr routing with standalone cross-agent delegation
   through the workflow owner, preserving its round and reviewer continuity.

## [0.0.7] - 2026-11-01 - [0.0.16](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.16)

1. Prepare private mutable dependency paths for committed-tree checks; shared writable
   dependencies need a proven write-free contract across the full subprocess tree.
   The environment recipe is cooperative and provides no OS containment.
2. Check current PR head/base before expensive verification and invalidate applicable
   evidence after target changes. A hostless ready PR requires fresh project checks
   on its committed target, with commands and results in the report and PR body.
3. Keep undefined or unavailable checks explicitly not verified; offer draft or
   clarification without creating a tracked record host solely for a gate.

## [0.0.6] - 2026-10-30

- Align review intake, gate evidence, and the narrow authorized automatic review replies.
- Require the issue/reply/resolve defer evidence for GitHub source threads; local and
  document reviews retain owner and issue, plan-task, or follow-up tracking.

## [0.0.5] - 2026-10-29

- The verdict belongs to the committed tree: the fingerprint is `HEAD^{tree}` without the
  record host. Uncommitted paths are listed in the report and outside the verdict; when
  there is any besides the host, checks run in a clean clone of `HEAD`
  (`references/clean-clone.md` no longer applies a diff). Work that is itself
  uncommitted (`Commits: forbidden`, no answer to the commit-policy question yet) is
  judged on the working tree, and its `Verify` line ends with `working`. The description
  no longer ties `verify` to the moment before a commit.
- `references/tree-fingerprint.md` (shared by `verify`, `cr-request`, `cr-received`, and
  `finalize`) has two fail-closed recipes, `## Committed tree` and `## Working tree`: one
  `&&` chain each, the ID printed only after every step succeeded, the temporary index
  removed by a `trap`. A failed recipe gives `BLOCKED (fingerprint failed: <step>)`.
- Re-pin restarts at most twice; a third change gives
  `BLOCKED (tree keeps changing: <paths or commits>)`.
- Record host, in one order: the plan, then the spec with its `## Verification record`
  (created by the first write), then none. No plan-journal is created any more: with no
  host the `Verify:` line is printed in the report only.
- A claim covered by `Ruling: R<n>-F<k> superseded by ...` is `n/a: superseded` and the
  `Ruling` is checked; an `ESCALATE` blocks until `Ruling: R<n>-F<k> escalation decided`.
  A criterion covered only by `Outward` tasks is `deferred to Task <n>` and does not
  block `PASS`; after `PASS` and a closed review the next step is
  `implement - Task <n> (outward, needs confirmation)`.
- Round rule: only automatic rounds count; a user-started round past the limit runs once
  and is recorded with `Ruling: round R<n> started by the user past the limit`.
- `--auto` starts the next local skill (`implement`, `cr-request`, `cr-received`) in the
  same turn and stops at the user's decisions, the Round rule, `Outward`, and the
  `finalize` choice; a chain that `finalize`, `cross-cr`, or `plan-craft` started for a
  step it owns returns to that skill (gate healing, next cross-cr round, clean plan
  review). Every `FAIL` -> `implement` cycle is an automatic round. Work counts as
  uncommitted while the latest `Commits` line says `forbidden` or `ask once`.

## [0.0.4] - 2026-10-28

- A single fresh command run on the fingerprint can be the evidence for several claims
  when its output covers each of them.
- `Round verify` is written on a `FAIL` unless the previous `Verify` line (before this
  run's) is a `FAIL` on the same fingerprint, so a revert to an earlier tree starts a
  round too; a repeated `FAIL` on the same fingerprint writes only a `Verify` line.
- One blocker rule across rounds: every `Critical` or `Important` finding of any round,
  document reviews included, blocks until a `Received` line rules on it; a new round
  does not close an old finding. Claims come from the `ACCEPT` and `PARTIAL` findings of
  any round, so an accepted fix from an older round is proven too (review R1-F1).
- The report and the tree fingerprint reference say `<full tree ID>` and record the full
  object ID (40 hex characters in SHA-1, 64 in SHA-256); the recipe removes its
  temporary index with a `trap`.

## [0.0.3] - 2026-10-27

- The re-approval marker is checked as a claim: the plan's `Spec` names that path and
  the spec reads `Status: approved`; `references/report.md` counts only the code
  reviews after the last marker for the next step (review R4-F1, F2 on PR #14).
- The `Next step` table counts only the code `Review`, `Finding`, and `Received` lines
  after the last `Ruling: plan revised after spec re-approval` marker; with no code
  review after it, the next step is `cr-request` (review R3-F1 on PR #14).
- The time in the `Verify` line comes from `date '+%Y-%m-%d %H:%M'` right after the
  re-pin, never from memory (request 20261026-1911).
- The `Next step` table counts only `Review` lines in `code` mode, or `re-review` after a
  code review, as a review of the implementation: a journal with only spec or plan
  reviews leads to `cr-request`, not `finalize`; open blockers still come from every
  round (request 20261025-1712, verify).
- New `references/clean-clone.md`: rebuild an uncommitted tree in a fresh clone (`git
  clone`, `git diff --binary HEAD | git apply`, the untracked files the fingerprint
  covers) and compare fingerprints before trusting it; a copy without `.git` is not a
  clean checkout (request 20261025-2044, verify).
- Journal lines go inside the record's `text` block, before its closing fence, never
  after it (request 20261025-1800).

## [0.0.2] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; version bump only, the text is unchanged.

## [0.0.1] - 2026-10-22

- Initial release, replacing devflow verification-gate in the awf chain: claims numbered
  before checks from the spec criteria, plan tasks, journal, and the caller's words; a
  tree fingerprint pinned before and after checking; fresh evidence only; check
  equivalence; a bar check for weakened tests, suppressions, and lowered thresholds;
  suspiciously easy success; four verdicts with review blockers read from the journal;
  full and compact reports; the `Verify` journal line; the shared Round rule; a
  standalone mode that creates a plan-journal; and a `Next step` line.

[0.0.9]: https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.18
