# Changelog

## [0.0.13] - 2026-11-13

1. Description rewritten as a thesis followed by `Use when ...` without `You MUST`, cutting
   its context cost (`20261111-2220`).

## [0.0.12] - 2026-11-07

1. Comment names `transfer-context`, the new name of `context-transfer`.
2. The description names the replaced devflow skills `plan-execution` and `plan-orchestration`
   (were `inline-plan-dev` and `subagent-plan-dev`).

## [0.0.11] - 2026-11-07 - [0.0.22](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.22)

1. Name the skill in `Next step` as inline code in the host's invocation form
   (`/<skill>` in Claude Code, `$<skill>` in Codex) (`20261024-2217`).

## [0.0.10] - 2026-11-04 - [0.0.20](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.20)

1. Report the ordered plan task checklist after each confirmed completion, preserving
   task numbers and distinguishing done, active, blocked and pending tasks.

## [0.0.9] - 2026-11-04 - [0.0.19](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.19)

1. Keep pending post-merge evidence in `~/.sentimony/agentflow/implement/<project>/`
   instead of the gitignored `.delivery-evidence/` with an `info/exclude` entry; a
   populated legacy folder keeps being used until the new location holds data, then the
   new one wins and the legacy folder is reported as unused (`20261104-0706`). `PendingStore` takes an
   optional `home` and refuses symlinks, foreign owners and an unusable `HOME`.

## [0.0.8] - 2026-11-01

1. Use the shared manual/auto stage transition contract and return orchestrated results
   to resolve-issue; preserve current permissions, critical user decisions and delivery gates.

## [0.0.7] - 2026-11-01 - [0.0.16](https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.16)

1. Record post-merge task evidence in an authorized own PR comment with canonical
   readback; preserve the integrated commit, deployment identity and task/attempt.
   Post-merge tasks leave tracked plan/spec content on the base unchanged.
2. Persist evidence in an ignored, atomic local store before publication; unknown
   write outcomes recover through lookup/readback without duplicating an attempt.
   Report production success separately from evidence-pending publication.
3. Clarify that hostless ready PRs still require fresh project checks. The evidence
   helper has an injected transport contract; no production forge adapter is supplied.

## [0.0.6] - 2026-10-30

- Align review intake, gate evidence, and the narrow authorized automatic review replies.

## [0.0.5] - 2026-10-29

- `--auto` in `argument-hint`: a local `Next step` (`verify`, `plan-craft`) starts in the
  same turn, and the turn stops on the user's decisions, the Round rule, an `Outward`
  action, `INCOMPLETE` or `BLOCKED`, and the `finalize` option choice.
- Commits follow the shared checkpoint rule: `Initial dirty state` names staged paths
  too, a task commit holds exactly the task's paths (own hunks for dirty files), content
  the user staged stays staged, and the record gets `Commits: allowed | ask once |
  forbidden` after `Base`: the answer to the user's and project's commit policy, with
  `ask once` only while the question is open and a later answer appended as a new line.
- Work without a plan records into the spec's `## Verification record`, or only into the
  report when there is no spec; appending there does not reset the spec's approval.
- Re-entry after a `FAIL`: each failing claim returns its task to `pending` with a
  `Ruling`, a claim without a task goes to `plan-craft`, and a spec without a plan is a
  candidate too; each cycle is an automatic `verify` round.
- `Next step` order: spec draft, user decisions, Round rule, `plan-craft`, then `verify`.
- Equal fixes that change neither the spec, a public contract, data, nor security are
  chosen with `Ruling: <choice> over <alternative> - ...`; a task that removes an
  accepted fix writes `Ruling: R<n>-F<k> superseded by Task <n> - ...`.
- An `Outward` task runs only after a full `PASS` and the user's confirmation, under
  `--auto` too.
- Round rule: only automatic rounds count, a user call past the limit runs one more
  round with a `Ruling`, and the same cause twice escalates in every round.
- Subagents are the default for `Execution: unset`, read from the field's first word;
  parallel subagents work in their own worktrees, return a `Verify:` line the controller
  appends, and are asked for `Learnings:` and `Requests:` lines; their commits are
  integrated locally without push or force.
- Resume: a failure explained only by an unfinished task is checked again once that task
  is `done`, and only a higher-numbered task can explain it.

## [0.0.4] - 2026-10-28

- Without a plan argument, the plan is chosen among unfinished ones by `Branch`; zero or
  several matches get one question listing the candidates.
- The no-plan route reads the spec path from the argument or from the `- spec <path>`
  handoff, and the minimal journal records `Spec: <path>` instead of `Spec: none` when a
  spec exists; a spec argument takes the unfinished plan whose `Spec` names it and goes
  to the no-plan route only without one, a `no plan needed` handoff skips the plan
  search, and `argument-hint` and the argument line name `<spec-path>` (review R1-F3).
- A file listed in `Initial dirty state` goes into a commit only with the task's own
  hunks; when they cannot be separated the task is `blocked - missing permissions` until
  the user decides (review R1-F2).
- On resume, a `done` task whose `Files` overlap a later `done` task with a trace
  (an `in progress` task triggers nothing) reruns its own check and goes back to
  `pending` with a `Ruling` if it fails, unless that later task's `Produces`, a plan
  revision after spec re-approval, or the partial work of an `in progress` task explains
  the failure; step 3 names this recheck
  (review R1-F4).
- In a separate worktree the plan and spec stay authoritative in the controller's
  checkout, only the controller writes the journal, and tasks and subagents get absolute
  paths to that copy.
- `Base` is the full object ID of `HEAD`.

## [0.0.3] - 2026-10-27

- The journal reference names every record line plan-craft writes, matching its list
  (review R4-F1 on PR #14).
- The journal names the record lines `plan-craft` writes on a revision after spec
  re-approval (the marker and the delta tasks) and where they go (review R3-F1, F2 on
  PR #14).
- The spec's `Status` is checked in Step 1, before `Base` is written; a resume against a
  draft spec with no marked task stops too. On resume, a `blocked - conflicting intent`
  task whose spec is approved again goes back to `pending` (journal Resume rule), so
  the plan can reach all tasks `done` (review R2-F1, F2 on PR #14).
- A draft spec stops a fresh start, while on resume only the tasks the spec change
  touches wait and independent tasks continue; after the new yes `plan-craft` revises
  the plan in place (review R1-F1 on PR #14).
- A deviation that would materially change an approved spec no longer updates the spec
  in the same pass: the skill sets the spec's `Status` back to `draft`, blocks the
  affected tasks, and ends with `Next step: specify` until a new explicit yes; a plan whose
  spec is a draft does not start. A new `Approval invariant` section is shared with
  `specify`, `plan-craft`, and `cr-received` (request 20261027-0206).
- Journal lines go inside the record's `text` block, before its closing fence, never
  after it (request 20261025-1800).

## [0.0.2] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; version bump only, the text is unchanged.

## [0.0.1] - 2026-10-22

- Initial release: one skill that executes a plan inline or through subagents, replacing
  devflow `inline-plan-dev` and `subagent-plan-dev`.
- Clean start with `Base`, `Root`, `Branch`, and `Initial dirty state` in the plan's
  execution record and a baseline check before the first task.
- Test-first tasks, root cause before a fix, task boundaries, and a closed list of five
  blockers.
- Approach drift is adapted and recorded as a `Ruling`; goal drift waits for the user; a
  deviation that changes a spec decision updates the spec in the same pass.
- Subagent mode with `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, and `BLOCKED`
  statuses and an explicitly named subagent model; parallel tasks only with shown
  independence.
- Shared Round rule with a `Round <loop> <n>` counter in the journal.
- Resume rule: a `done` task without a trace in the tree or the history goes back to
  `pending`.
- Standalone use: a plan-journal for one or two obvious edits, otherwise
  `Next step: plan-craft`.
- Every result ends with a `Next step` line.

[0.0.8]: https://github.com/sentimony/agentic-workflow/releases/tag/v0.0.18
