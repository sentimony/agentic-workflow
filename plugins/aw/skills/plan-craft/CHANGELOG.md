# Changelog

## [0.0.3] - 2026-10-27

- A spec with `Status: draft` is no longer planned around as `Spec: none`: the skill
  writes nothing and stops with `Next step: specify`; the standalone case is only for
  work with no spec. A new `Approval invariant` section, shared with `specify`,
  `implement`, and `cr-received`: the skill never edits an approved spec's content, and a
  material change it needs sets `Status: draft` and goes back to `specify`
  (request 20261027-0206).
- No longer calls `scope-check`.
- An exact expected output that follows from a formatting rule is computed by a script
  or a run of existing code, marked as computed with the command that reproduces it, or
  marked `check during execution`; never written by hand (request 20261024-2246).
- The template says where journal lines go: inside the record's `text` block, right
  before its closing fence, never after it at the end of the file (request 20261025-1800).

## [0.0.2] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; version bump only, the text is unchanged.

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
