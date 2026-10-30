# Changelog

## [0.0.5] - 2026-10-29

- `--auto` in the arguments (`argument-hint` `[--auto]`): the `direct` route starts
  `implement --auto` and an approved spec starts `plan-craft --auto` in the same turn;
  the turn still stops on the user's decisions, the Round rule, `Outward`, `INCOMPLETE`
  or `BLOCKED`, and the `finalize` option choice. `--auto` never approves a spec and is
  never written into a spec, plan, or record.
- After the explicit yes the skill commits the spec and its spec-index line locally as
  `Approve spec <topic>`, with only its own paths and under the user's and project's
  commit policy (one question per chain when it asks first, no commit when it forbids).
- The spec template has an optional last section `## Verification record` for work
  without a plan: a fenced block that starts with `Branch: <name>` and takes the plan
  record's lines and append rules. Appending to it does not reset approval, and a
  re-approval of a spec with that section appends `Ruling: spec re-approved - <date>`.
- The coverage check for `note` traces criteria to `Goal` or a decision, without
  `Behavior` and `Contract`. A decision names a rejected alternative only when one was
  considered; `Rejected:` in the template is optional. An explicitly accepted risk still
  approves a spec.

## [0.0.4] - 2026-10-28

- An entry of the assumptions list is material when its opposite would change a decision
  or an acceptance criterion; a material entry that stays `assumed` moves `note` to
  `design` and, before approval, becomes an open question or a named risk.
- An open question whose answer would change Behavior, Contract, or an acceptance
  criterion is marked `blocking`; the spec template gives the `blocking:` form with the
  risk it names, a general yes does not approve the spec while a `blocking` question is
  unresolved (an explicitly accepted risk does not block), and the result names each
  `blocking` question.

## [0.0.3] - 2026-10-27

- The existing plan path is passed to `plan-craft` after a re-approval whether that
  plan is finished or not (review R2-F3 on PR #14).
- After a re-approval of a spec that already has a plan, `specify` passes that plan's
  path to `plan-craft`, which revises it in place; the approval invariant says so in
  every copy. The Result table has a row for an approved spec with `plan-craft`
  installed, and `specify` gives its result before `plan-craft` runs. The Step 2 route
  check covers only `note` and `design`: the `direct` route ends at Step 0 (review
  R1-F1, F4, F5 on PR #14).
- Questions come in rounds: round 1 asks every open decision, each later round only what
  the answers left unclear, at most eight, each opened by `Round <k>/8`. After a round
  with nothing unclear the skill goes on to the draft spec itself, without asking leave;
  after round 8 the rest goes under `Open questions`.
- After the user's explicit yes the skill sets `Status: approved` and starts `plan-craft`
  on the spec in the same turn, without asking whether to plan; the result of
  `plan-craft` ends the turn, and the `Next step: plan-craft` line remains only when
  `plan-craft` is not installed (request 20261027-0303).
- No longer calls `scope-check`.
- External audit (request 20261027-0206):
  - an `Approval invariant` shared with `plan-craft`, `implement`, and `cr-received`: a
    draft spec is never planned around as `Spec: none`, a material change to an approved
    spec returns it to draft, and no skill approves on the user's behalf;
  - the route from Step 0 is provisional: after the evidence register the skill confirms
    or revises it, heavier on a contradiction, lighter only when no design item and no
    user decision remain;
  - approaches are compared only when more than one is viable; otherwise the spec says
    why the alternatives were ruled out instead of inventing a second;
  - a recommended answer comes with its reason only when evidence or a constraint
    supports it; a choice that rests on the user's priorities gets the consequences of
    each option instead;
  - every register entry has an exact source (`path:line`, command output, or the
    user's words); a user statement verifies a requirement, not a technical fact; a
    material `assumed` entry becomes an open question or a risk before approval;
  - an acceptance-criteria coverage check before saving, and a six-item fresh-reader
    checklist with a verdict per item, defects, and questions, without new scope;
  - a large request splits into separate specs only where a part can be approved,
    built, and accepted alone;
  - a shorter description.

## [0.0.2] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; version bump only, the text is unchanged.

## [0.0.1] - 2026-10-22

- First release: route triage (`direct`, `note`, `design`), evidence register,
  questions with a recommended answer, two approaches, a fresh-reader check, a spec
  with `AC<n>` criteria, and an explicit approval barrier.
- The `direct` route hands `implement` one sentence with the request's domain values;
  secrets appear only as placeholder names.
- Calls `scope-check` after each save when it is installed.
- Ends every result with a `Next step` line.
