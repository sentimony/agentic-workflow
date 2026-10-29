# Changelog

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
