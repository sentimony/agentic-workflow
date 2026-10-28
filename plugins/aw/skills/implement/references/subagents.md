# Subagent mode

In subagent mode this session is the controller. Subagents write code; the controller
decides, rechecks, and keeps the journal. A subagent never edits the execution record.

## The brief

Each brief stands on its own, because the subagent sees nothing of this conversation:

- **Goal** - the task's title and what it must produce (`Produces`), plus the plan's
  `Goal` in one line for orientation.
- **Scope** - the task's `Files`, the `Consumes` it can rely on, and the paths of the spec
  and plan to read. Point at files; do not paste conversation history. When the subagent
  works in a separate worktree, give absolute paths to the plan and spec in the
  controller's checkout: that copy is authoritative, and the subagent neither reads nor
  edits a copy of the plan inside the worktree.
- **Do not touch** - paths outside the task, the uncommitted changes listed in
  `Initial dirty state`, the execution record, Git history (no reset, stash, clean, or
  force operations).
- **How to check** - the task's `RED` and `GREEN` commands, or its `Check:`.
- **Rules carried over** - test first where there is a seam, root cause before a fix,
  the closed list of blockers from the skill, and the commit rule of the task when the
  subagent commits.
- **Report** - one status, the changed paths, the commands run with their results, and
  anything noticed but left alone.

Name the subagent model in every dispatch (for example "model: sonnet") instead of
relying on a default, and repeat it in the report so the journal can be read later
without guessing.

## Statuses

The subagent ends its report with exactly one of these:

| Status | Meaning | Controller action |
| --- | --- | --- |
| `DONE` | task finished, checks pass | rerun the checks, compare paths with `Files`, then mark `done` |
| `DONE_WITH_CONCERNS` | finished, with doubts | rerun the checks, weigh each concern; record a `Ruling` or a `Deferred` per concern |
| `NEEDS_CONTEXT` | cannot proceed without information | supply the missing context and dispatch again |
| `BLOCKED` | hit one of the five blockers, or cannot make progress | check the claim; a real blocker marks the task `blocked`, anything else is work to redo |

A status is a claim. The controller reruns the task's check on the tree itself before
writing `done`, because a subagent's report is not evidence.

## Retries

A task that came back `NEEDS_CONTEXT` or `BLOCKED` is not sent again unchanged. Change one
thing first: add the missing context, choose a stronger model (named explicitly), or split
the task into smaller ones. Each retry counts as a round under the Round rule and adds a
`Round task-<n> <k>: <cause>` line.

## Parallel dispatch

Several tasks go out at once only under the rules of the skill's Parallel tasks section:
shown independence, a separate isolated workspace per subagent (see
[isolation.md](isolation.md)), results integrated one by one with the checks rerun, and
overlap resolved before the next wave.

## Review inside execution

A self-review of a task by the controller is optional. The independent review of the
whole change is `cr-request` after `verify`; reviewing every task as well would review the
same code twice.
