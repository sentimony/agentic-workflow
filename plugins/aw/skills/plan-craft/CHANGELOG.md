# Changelog

## [0.0.5] - 2026-10-29

- `--auto`: the plan review and `implement` start in the same turn; the turn still
  stops on user decisions, the Round rule, `Outward`, `INCOMPLETE` or `BLOCKED`, and the
  `finalize` choice; `--auto` is never written into a plan, spec, or record.
- Checkpoint commits replace the old no-commit rule: `Plan <topic>` once `Execution` is
  written and `Revise plan <topic>: <reason>` per revision, local, own paths only, under
  the user's and project's commit policy.
- Under `--auto` the plan review is `cr-request` in document mode with up to three
  automatic rounds; the review chain returns to `plan-craft`, which starts `implement`
  after a clean round; `cross-cr plan` only when the user names it; an unavailable
  reviewer is one report line.
- Step 7 offers `implement` with subagents first and by default, `inline` with its
  reason; under `--auto` it picks without a question (`inline` for one or two tasks or
  tasks on the same files) and writes the reason after the value; a revision does not
  ask again. Tasks are self-contained for a fresh agent.
- An existing plan for the spec is revised before the "no plan needed" step; without a
  plan, `implement` writes into the spec's `## Verification record`, and plan-craft no
  longer mentions a journal of its own for such edits.
- Commands are checked against the project's script definitions, `--help` only for
  syntax they do not show; running existing code gives expected values only for
  behavior the spec keeps unchanged.
- New task field `Outward: <what and where>`; new record line
  `Ruling: R<n>-F<k> superseded by ...` written on a revision that removes an accepted
  fix.
- The template's record format adds `Commits`, `Verify ... [working]`, the record host
  order, the spec's `## Verification record`, and the named `Ruling` forms; the writers
  table adds `specify`, `finalize`, and round-past-limit writers, and `verify` no
  longer creates a journal without a plan.
- Approval invariant: appending to a spec's `## Verification record` does not reset its
  approval.

## [0.0.4] - 2026-10-28

- The `no plan needed` handoff carries the approved spec:
  `Next step: implement - no plan needed: <the edit> - spec <path>`; the Result table
  has a row for it.
- Tasks are ordered by dependencies (a removal comes only after nothing reads the old
  thing), and credential placeholder names such as `<API_TOKEN>` are not flagged as
  placeholders.
- A file listed in `Initial dirty state` takes only the task's own hunks in the commit
  line (see `implement` step 5).

## [0.0.3] - 2026-10-27

- One list of the record lines plan-craft writes (step 5 and the template's writer
  table): placeholders of a new plan, new tasks of a review revision, and the
  re-approval marker with its delta tasks (review R4-F1 on PR #14).
- The revision after spec re-approval appends the marker
  `Ruling: plan revised after spec re-approval - <spec path>` and then the delta tasks,
  at the end of the record before the closing fence; these are the only record lines
  plan-craft writes (review R3-F1, F2 on PR #14).
- The revision after spec re-approval comes first in step 3 and applies to a finished
  plan too; it adds delta tasks with new numbers and never edits a record line, and a
  blocked task is returned to `pending` by `implement` (review R2-F1, F3 on PR #14).
- A revision after spec re-approval edits the existing plan in place: delta tasks as
  new `Task <n>: pending` lines, record lines kept, `done` tasks never rewritten; the
  skill takes a spec path and a plan path together (review R1-F1 on PR #14).
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
