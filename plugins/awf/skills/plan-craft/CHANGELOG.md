# Changelog

## [0.0.1] - 2026-10-22

- Initial release: turns an approved spec, or requirements agreed in the conversation,
  into a plan with a header, tasks mapped to acceptance criteria, and an execution record
  with `Base: unset` and `Task <n>: pending` placeholders.
- Says when a change needs no plan, orders tasks risk first, and plans stateful logic as
  behavior and invariants.
- Never replaces a plan whose execution record is unfinished; a new plan is a new file.
- Checks the plan before handoff, calls `scope-check` after every save when installed,
  and asks for the execution mode at the end.
- Replaces devflow `plan-crafting`.
