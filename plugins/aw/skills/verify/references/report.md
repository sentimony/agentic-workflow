# Verify report

The report is the answer `verify` returns. The full matrix is required before
`cr-request` and before `finalize`; a compact report is enough for an intermediate check.
Both end with exactly one `Next step` line.

## Full report

```text
HEAD: <full SHA>   Branch: <name or detached>
Tree: <full tree ID>
Working state: staged <n or none>, unstaged <n or none>, untracked <n or none>
Plan: <path or none>   Spec: <path or none>

Claims:
C1 (AC1): <observable promise>
C2 (Task 3): <observable promise>
C3 (journal): <observable promise>
C4 (R1-F2): <observable promise>
C5 (caller): <observable promise>

Matrix:
C1 | <check command> | `passed`
C2 | <check command> | `failed`
C3 | <check command> | `n/a: <reason>`
C4 | <check command> | `passed`
C5 | <check command> | `not verified: <reason>`

Bar check: <weakening found, with path and line, or none>
Review blockers: <IDs with severity and disposition, or none>
Verdict: PASS | FAIL | INCOMPLETE (<owner> - <next action>) | BLOCKED (<what stops the check>)
Journal: Verify: <verdict> full tree <tree SHA> <YYYY-MM-DD HH:MM>
Next step: <skill> - <one-line reason>
```

## Compact report

```text
Verdict: <verdict>   Tree: <full tree ID>
<only rows whose status is not passed, in the matrix form>
Journal: Verify: <verdict> compact tree <tree SHA> <YYYY-MM-DD HH:MM>
Next step: <skill> - <one-line reason>
```

A compact `PASS` lists no rows. A compact report never stands in for the full matrix:
`finalize` and a clean `cr-request` look for a full `Verify: PASS` on the current tree.

## Claims

- Number claims `C1`, `C2`, and so on before any check runs.
- Sources, all of them when present: every `AC<n>` of the spec the plan names, every task
  of the plan with its `Produces` and `Covers` fields, the `Task`, `Ruling`, and
  `Deferred` lines of the journal, each finding of any review round that a
  `Received` line marks `ACCEPT` or `PARTIAL`, and the words of the caller ("fixed the
  login redirect", "all tests pass").
- The source tag in parentheses is `AC<n>`, `Task <n>`, `journal`, `R<n>-F<k>` (or
  `R<n>-<reviewer>-F<k>` with several reviewers, as `cr-received` keeps it), or `caller`.
  A claim that comes from an acceptance criterion always names its `AC<n>`.
- A finding claim promises that the cited problem is gone; for `PARTIAL`, the promise is
  the remedy the `Received` and `Ruling` lines chose, not the reviewer's full suggestion.
  Its check is the command `cr-received` lists under `Checks to rerun` when that return
  block is in the conversation; a failing one points back at the finding.
- A claim is one observable promise. "Done" or "works" is split until each part has a
  check that could fail.
- Without a plan, the sources are the caller's words and the diff from the base the
  caller names, or from `HEAD` when none is named.

## Row statuses

Each status sits in a code span:

- `passed` - the check ran on the current tree and its output shows the claim holds.
- `failed` - the check ran and its output contradicts the claim.
- `n/a: <reason>` - the claim does not apply to this change, for a stated reason.
- `not verified: <reason>` - no check ran, or its output does not decide the claim. A
  missing tool, missing access, missing credentials, or a check outside the session's
  reach is always `not verified`, never `n/a`.

The check command is the exact command run, or the exact file and line read for a claim
that only reading can decide. "Looked fine" is not a command.

## Verdicts

- `PASS` - every row is `passed` or `n/a`, the bar check found nothing unreported, and no
  review blocker is open.
- `FAIL` - at least one row is `failed`.
- `INCOMPLETE` - no row failed, but a row is `not verified` or a review blocker is open.
  Name the owner (the user, `implement`, `cr-received`, CI, a named person) and the next
  action that would decide it.
- `BLOCKED` - the verification itself cannot move: the tree cannot be read, the project
  cannot be built at all, or the claims cannot be formed. Name what stops it.

Any `not verified`, any `failed`, or any open review blocker rules out `PASS`.

## Review blockers

Read the journal of the plan:

- every round counts, document reviews included: a new round does not close an old finding;
- each `Finding` of any round with severity `Critical` or `Important` is a blocker until
  a `Received` line gives its ID a disposition; `REJECT`, `OUTDATED`, and `DEFER`
  close it, and `ACCEPT` and `PARTIAL` mark it fixed, with its claim (tag `R<n>-F<k>`)
  checked in this run over the current tree as the proof;
- any `ESCALATE` in any `Received` line is a blocker until the user decides it;
- when the `cr-received` return block is in the conversation, every item of its
  `Blocking:` field other than `none` is a blocker too.

Blockers come from every round. The choice of the next step
(SKILL.md step 10) is different: there only a `Review` line with `mode code`, or
`mode re-review` after a code review, counts as a review of the implementation, so a
journal with only spec or plan reviews leads to `cr-request`, not `finalize`. When the
journal holds the marker `Ruling: plan revised after spec re-approval - <spec path>`,
only the code reviews after the last marker count for that choice.

## Journal lines

Append at the end of `## Execution record`, inside its ```` ```text ```` block before the
closing fence when it has one; never rewrite an existing line:

```text
Verify: <verdict> <full|compact> tree <tree SHA> <YYYY-MM-DD HH:MM>
Round <loop> <n>: <cause>
```

`<YYYY-MM-DD HH:MM>` is the output of `date '+%Y-%m-%d %H:%M'` run right after the
re-pin (SKILL.md step 7), never a time written from memory.

For this skill `<loop>` is `verify` and the cause lists each failing claim by its source
tag and promise, for example `Round verify 2: AC3 - login redirects to /home`. `C<n>`
numbers are reassigned every run, so they never form the cause; the same tag and promise
in two rounds is the same cause for the Round rule. A `Round` line is written only when
the verdict is `FAIL` and the previous `Verify` line (the one before this run's) is not
a `FAIL` on this fingerprint, a revert to an earlier tree included; a repeated `FAIL` on
the same fingerprint writes only a new `Verify` line, no `Round`. It is numbered one
above the last `Round verify` line in the journal.

Credentials and secrets never enter the plan-journal a standalone run creates, its Goal
included; use placeholder names such as `<API_TOKEN>`.

The plan-journal has this shape:

```text
# <topic>

**Spec:** none

**Goal:** <one sentence with the domain values of the request>

**Execution:** inline

## Execution record

Branch: <name>
Verify: <verdict> <full|compact> tree <tree SHA> <YYYY-MM-DD HH:MM>
```

The `Branch` line lets `finalize` find the journal in a later session.

It lives in the project's plans folder, or in `docs/plans/YYYYMMDD-HHMM-<topic>.md`.
