# Records, States, and the Summary

## Fields of a cr-request result

- **Target reviewed** - the identity the findings belong to (step 2).
- **Axis verdicts** - `FINDINGS` and `UNASSESSED` axes are open; an `UNASSESSED` axis
  is a coverage gap to report, never a pass.
- **Findings** - become records (step 3). Confidence sets how much independent checking a
  claim needs before code changes; severity is the reviewer's label, not a fact.
- **Suggestions** - optional; they enter the fix scope only when the user asks.
- **Set aside** - each row gets a one-line ruling, kept out of scope or turned into a
  finding by evidence; the ruling goes into a `Ruling` journal line.
- **Open questions** - go to the user; never answer them with a code change.
- **Merge readiness** - an opinion; it neither blocks nor authorizes anything.

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

The tree fingerprint comes from the `## Committed tree` recipe in
[tree-fingerprint.md](tree-fingerprint.md).

## Identity record

    Reviewed head: <full SHA from the review, or unknown>
    Base: <base ref and SHA, or unknown>
    Included paths: <paths or whole tree>
    Uncommitted fingerprint: <diff hash and untracked files, or none>
    Tree: <fingerprint>

Keep one record for the reviewed target (`Tree` from the review when it states one) and
one for the current tree. The current tree matches the reviewed target when HEAD, the
base, the included paths, the uncommitted fingerprint, and `Tree` all match. Any
difference moves the affected findings to a recheck against current code. Every
disposition is bound to the current `Tree`: after any edit, earlier decisions on other
records stand only once rechecked against the new fingerprint.

## Finding record

    ID: <R<n>-F<k>, R<n>-<reviewer>-F<k>, the reviewer's own, or F1, F2, ...>
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

- `OPEN` - not checked yet; never the final state of a material record.
- `CONFIRMED` - reachable and has the stated impact on the current tree.
- `NARROWER` - real, but narrower, different, or less severe than claimed.
- `UNFOUNDED` - not reachable, contradicted by evidence, or based on a wrong premise.
- `OUTDATED` - may have held for the reviewed revision but not for the current tree.
- `SAME CAUSE` - the same root cause as a named primary record.
- `NEEDS RULING` - cannot be settled without information or a ruling the user holds.

Assessment and disposition are separate: a `CONFIRMED` finding can be `DEFER`, and a
`NARROWER` one can be `ACCEPT` once rescoped.

## Dispositions

- `ACCEPT` - valid; fix now.
- `PARTIAL` - the concern is valid, the suggested remedy is not; fix it your way and say
  why.
- `REJECT` - invalid, stale, or covered by another record, with the evidence.
- `DEFER` - valid and non-blocking, with an owner and a place to track it; never for a
  blocker.
- `ESCALATE` - needs a decision the user or another owner makes: product scope,
  architecture, security posture, a public contract, or a conflict with an earlier user
  decision. It stays open across rounds until a `Ruling: R<n>-F<k> escalation decided`
  line; records that do not depend on it are fixed in the same pass.

## Evidence for findings on a spec or plan

A document finding cites a section (`§<heading>`) and has no test to fail. Use one of:

- a one-off reproduction: run the command, read the file, or query the repository the
  section relies on, and record what it showed;
- a pointer to coverage elsewhere: the plan step or task that already handles the point
  (for example, deferred to `Task <n>`), quoted by heading;
- a scoped re-review: after the edit, only the changed section goes back to `cr-request`
  in document mode, not the whole file.

The resolution evidence of a document fix is the edited section and the file's new
`sha256`.

## Summary

    Reviewed target: <identity>
    Current tree: <identity; drift and its effect>
    Uncovered axes: <UNASSESSED axes and why>

    ACCEPT n | PARTIAL n | REJECT n | DEFER n | ESCALATE n

    Resolved:  <ID - change - evidence>
    Rejected:  <ID - assessment - evidence>
    Deferred:  <ID - owner - where tracked>
    Set aside: <row - ruling>
    Escalated: <ID - decision needed - options; open ones from earlier rounds too>
    Open questions: <from the review and from verification>
    Checks run: <commands, results, and the class of each failure>
    Re-review: <needed for which scope, or not needed - reason>

Report counts as they are; a rejected or deferred finding is a result, not a failure to
hide.
