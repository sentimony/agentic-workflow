# Records, States, and the Summary

## Anchor commands

Read-only, from the worktree that will be fixed. `--no-ext-diff --no-textconv` keeps
local diff drivers from rewriting the output.

    git rev-parse --show-toplevel
    git branch --show-current
    git rev-parse HEAD
    git status --porcelain=v1 --untracked-files=all
    git diff --no-ext-diff --no-textconv --name-status <reviewed-head> HEAD
    git diff --no-ext-diff --no-textconv HEAD | git hash-object --stdin
    git ls-files --others --exclude-standard

The current tree matches the reviewed target when HEAD, the base, the included paths,
and the uncommitted fingerprint all match the review's identity record. Any difference
moves the affected findings to a recheck against current code.

## Finding record

    ID: <reviewer's ID, or F1, F2, ...>
    Source: <reviewer or tool, and where the item lives>
    Reviewer wording: <verbatim>
    Reviewer severity and confidence: <as labelled, or missing>
    Claim: <the smallest precise statement of the alleged problem>
    Location: <current file, symbol, or boundary>
    Assessment: <state>
    Evidence: <what was checked and what it showed>
    Actual impact: <judged from the code>
    Disposition: <ACCEPT | PARTIAL | REJECT | DEFER | ESCALATE>
    Rationale: <why this disposition, and why the remedy differs if PARTIAL>
    Related: <primary record, dependents>
    Resolution evidence: <check, result, why it proves the finding>

## Assessment states

- `UNASSESSED` - not checked yet; never the final state of a material record.
- `VALID` - reachable and has the stated impact on the current tree.
- `PARTIALLY VALID` - real, but narrower, different, or less severe than claimed.
- `INVALID` - not reachable, contradicted by evidence, or based on a wrong premise.
- `STALE` - may have held for the reviewed revision but not for the current tree.
- `DUPLICATE` - the same root cause as a named primary record.
- `NEEDS DECISION` - cannot be settled without information or a ruling the user holds.

Assessment and disposition are separate: a `VALID` finding can be `DEFER`, and a
`PARTIALLY VALID` one can be `ACCEPT` once rescoped.

## Summary

    Reviewed target: <identity>
    Current tree: <identity; drift and its effect>
    Uncovered axes: <UNASSESSED axes and why>

    ACCEPT n | PARTIAL n | REJECT n | DEFER n | ESCALATE n

    Resolved:  <ID - change - evidence>
    Rejected:  <ID - assessment - evidence>
    Deferred:  <ID - owner - where tracked>
    Escalated: <ID - decision needed - options>
    Open questions: <from the review and from verification>
    Checks run: <commands and results>
    Re-review: <needed for which scope, or not needed - reason>

Report counts as they are; a rejected or deferred finding is a result, not a failure to
hide.
