# Changelog

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
