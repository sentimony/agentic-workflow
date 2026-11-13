# Changelog

## [0.0.13] - 2026-11-13

1. Forge identity preflight before a batch push or PR: repository ID per target, same-ID targets merged only after comparing blobs and trees, effective account and rights checked before the first push (`20261101-0351`).
2. Squash gate reads all checks of the head and verifies named reviewers through the reviews API on the full head SHA; a missing review is never completion (`20261029-2038`).
3. Every publishing or integrating route first reads the criteria `verify` deferred to `finalize`; after the PR opens they are checked against CI on the head SHA, and `merge` and `squash` refuse while one is unchecked or red (a local `merge` needs the user's waiver or goes through `pr`) (`20261029-2232`).
4. `## Scoped tree` recipe added to the shared `tree-fingerprint.md` copy; agreement test of the four copies in CI (`20261029-2037`).

## [0.0.12] - 2026-11-13

1. Description rewritten as a thesis followed by `Use when ...` without `You MUST`, cutting
   its context cost (`20261111-2220`).

## [0.0.11] - 2026-11-07 - [0.0.22](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.22)

1. Name the skill in `Next step` as inline code in the host's invocation form
   (`/<skill>` in Claude Code, `$<skill>` in Codex); `none` stays plain text
   (`20261024-2217`).

## [0.0.10] - 2026-11-04 - [0.0.20](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.20)

1. Summarize current reviewer-relevant decisions in PR bodies, link the complete
   record, and keep open risks, deferred items, and outstanding checks visible.

## [0.0.9] - 2026-11-01

1. Use the shared manual/auto stage transition contract and return orchestrated results
   to resolve-issue; preserve current permissions, critical user decisions and delivery gates.

## [0.0.8] - 2026-11-01 - [0.0.16](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.16)

1. Evaluate effective required policy as known-required, known-none or unknown;
   positively prove absence and wait for delayed checks within a finite deadline.
   Fresh target guards precede checks, ready, waiting and pinned native merge.
2. Require fresh local verification for every ready transition, including hostless
   PRs. Ready may start missing/pending remote jobs; actual conflicts, red checks and
   stale or invalid evidence still block it. Unknown merge policy stays unknown, and
   merge waits for all applicable checks. Other hostless integration semantics remain.
3. Preserve post-squash evidence through the implement evidence contract instead of
   restoring new tracked record lines onto the base. Removing transferred duplicate
   hunks requires canonical evidence and the captured ownership journal.
4. Guard branch/workspace disposal separately with current authority, current branch
   and workspace integration or retention, data checks and explicit trusted post-merge
   task inventory. No actual tasks makes evidence not applicable; committed-only/local
   merges need no fabricated patch, PR or deployment. Unknown inventory or actual
   pending evidence blocks disposal. Preserve foreign staging and local artifacts;
   automatic mode supplies no force-cleanup permission.
5. Block whole-clone removal when common Git storage is inside the removal root.
   Linked-worktree eligibility requires surviving common data and retaining refs
   outside that root; no external-retention framework is implied.

## [0.0.7] - 2026-11-01 - [0.0.15](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.15)

1. Use the agentflow plugin identity in current references while preserving skill
   behavior and historical state.

## [0.0.6] - 2026-10-30

- Align review intake, gate evidence, and the narrow authorized automatic review replies.

## [0.0.5] - 2026-10-29

- Gate: the record host is the plan, else the spec with its `## Verification record`, else
  none, and without a host there is no gate. `merge`, `squash`, and a ready `pr` need a
  full `PASS` on the committed tree (recipe `## Committed tree`), never one that ends with
  `working`; `merge` and `squash` also need a `Review` line with mode `code` or
  `re-review` after a code review, counted after the latest re-approval marker (else after
  `Base`), or `Ruling: no review - <user's reason> - <cost if wrong>`, which `finalize`
  appends from the user's words. `pr --draft` opens a draft without a verdict and its body
  says `not verified on this tree`; turning it ready passes the `pr` gate.
- The record host is committed alone as `Record <topic>` once `merge`, `squash`, or `pr`
  is chosen and before its action, by the checkpoint commit rule and the commit policy;
  other uncommitted paths no longer fail the gate and are reported as not integrated.
- `--auto`: a gate failure that `verify` or `cr-request` heals runs that step in the same
  turn and returns to the chosen option once that chain's `Next step` is `finalize`; the
  option choice confirms its integration and push, while branch and worktree deletion keep
  their own confirmation. After a successful `merge`, `squash`, `pr`, `keep`, or `discard`,
  `--auto` starts `session-learnings` (recording mode, without `--auto`) in the same turn
  once no cleanup confirmation or record-commit question is pending; otherwise it follows
  the user's answer (user decision 2026-10-30).
- Squash: a PR that changes `.github/workflows/` is merged by the pinned `gh pr merge`,
  then the REST call; the `workflow` scope is explained only when a refusal names it
  (request 20261027-1356). The pinned head is the full object ID, 40 hex for SHA-1 and
  64 for SHA-256.
- Before `pr` and `squash`, the remote base must hold the branch's fork point; otherwise
  the report gives the count of foreign commits and advises pushing the base or targeting
  the stacked PR's branch, with `Stacked on #<n>` in the PR body (request 20261029-0012).
  Work on the base branch itself skips this check, and so does the branch the work moved
  onto, when the conversation says so or the user confirms it after the commit list.
  `pr-body.md` reads the PR's commits as `origin/<base>..HEAD`, and on the work-on-base
  path the `Record <topic>` commit comes after the new branch, the work commit, and the
  `verify` run, right before the push.
- A worktree this session created that `git worktree remove` refuses is removed with
  `--force` only after a confirmation that names its paths (request 20261029-1347).
- Work on the base branch: `merge` is hidden, and `pr` creates a branch from `HEAD`,
  commits, verifies or goes as a draft, pushes, and opens the PR; the report says how far
  the local base is ahead of `origin/<base>` (request 20261026-2322).
- Unfinished `Outward` tasks do not block integration; the report and the PR body's
  `Deferred` list them, and `finalize` never runs them.

## [0.0.4] - 2026-10-28

- The fingerprint recipe in `references/tree-fingerprint.md` records the full object ID
  (40 hex characters in a SHA-1 repository, 64 in a SHA-256 one) and removes its
  temporary index with a `trap` on exit.

## [0.0.3] - 2026-10-27

- Squash: `UNKNOWN` merge state is read again up to five times, `HAS_HOOKS` goes on,
  `--delete-branch` is not used and the branch is deleted only after the journal and
  base steps, and the worktree always ends on the base or detached on `origin/<base>`
  (review R1-F3, F6 on PR #14).
- After a squash the worktree always ends on the fresh base, with or without branch
  deletion, or detached on `origin/<base>` when another worktree holds the base; the
  report gives the branch, `HEAD`, and whether it equals `origin/<base>`
  (request 20261024-2226).
- Before the merge, a PR that changes `.github/workflows/` needs the `workflow` scope on
  the CLI token; a merge refused with a generic text gets its reason from the same merge
  through the REST API, pinned to the same head (request 20261026-1946).
- A repository without required checks waits for all PR checks, and a `mergeStateStatus`
  other than `CLEAN` stops the merge; the report says which checks were read
  (request 20261026-2331, no required checks).
- The uncommitted journal is saved and restored to `HEAD` before switching to the base,
  then written back; the diff must show only added record lines, and the report names
  the journal's fate (request 20261026-2331, uncommitted journal after squash).

## [0.0.2] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; the text changes only that name.

## [0.0.1] - 2026-10-22

- Initial release: replaces devflow `branch-finish`. Reads the Git state before every
  action, takes the base branch from the strongest source, and integrates only with a
  full `Verify: PASS` on the current tree fingerprint and nothing but the plan left
  uncommitted, otherwise hands back to `verify`.
- Six options: `merge`, `pr`, `squash`, `keep`, `discard` (explicit request only, with
  the commits that will be lost), and `pause` (wip commit with a continuation note).
- Squash merge recipe pinned to the verified head, PR title and body template with
  rulings and deferred items from the execution record, and cleanup behind a workspace
  barrier and a branch barrier.

[0.0.9]: https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.18
