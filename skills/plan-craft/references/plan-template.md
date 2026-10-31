# Plan template

Contents: skeleton, field notes, execution record format and writers.

Copy the skeleton below into the new plan file and fill every placeholder. Field keys and
their values (`Spec`, `Execution`, `Covers`, `pending`, `unset`) stay literal English
tokens even when the rest of the plan follows the language of the project's other plans.
Headings and prose may use that language; the keys may not.

## Skeleton

````markdown
# <Topic> - implementation plan

**Spec:** <path> | none

**Goal:** <one or two sentences: the observable outcome when every task is done>

**Architecture:** <how the pieces fit, in a short paragraph; the order of work and why>

**Stack:** <languages, frameworks, tools, and test runners the tasks rely on>

**Execution:** inline | subagents | unset [- <reason, under `--auto`>]

## Global constraints

<Copied word for word from the spec's `Decisions`, `Out of scope`, and `Security Model`
sections. With `Spec: none`, the constraints the user stated in the conversation.>

## Review focus

<Inputs and failure modes the spec expects that no test in this plan covers; where a
reviewer of the finished change should look first.>

## Acceptance criteria

<Only with `Spec: none`: the criteria taken from the conversation, one per line,
`AC<n>: <checkable predicate>`, numbered from 1 without gaps. With a spec, omit this
section; the spec holds the criteria.>

## Files

| File | Change | Task |
| --- | --- | --- |
| `<path>` | <new, modified, or deleted, and what for> | <n> |

## Tasks

### Task <n>: <title>

<Self-contained for a fresh agent that never saw the conversation: the context it needs,
when it is done, and what it must not touch.>

**Files:** `<path>`, `<path>`

**Consumes:** <exact signatures, formats, or files this task relies on, and which task
produces them>

**Produces:** <exact signatures, formats, or files this task leaves for later tasks>

**Covers:** AC<n>, AC<n>

**Depends on:** Task <n> | none

**RED:** `<command>` -> <expected failing output>

**GREEN:** `<command>` -> <expected passing output>

<When the task has no test seam, replace RED and GREEN with one line:>

**Check:** `<command or observable check>` -> <expected result>

**Commit:** `git add -A -- <paths>` (in `Initial dirty state`: own hunks only)

<Only for an action that leaves the repository (deploy, production, publication,
external service), never for pushing or merging the work branch:>

**Outward:** <what and where>

## Execution record

```text
Base: unset
Task <n>: pending
```
````

## Field notes

Spec precedence, the word-for-word constraints, stateful logic, `n/a`, the record
placeholders, and when a record is unfinished are rules of SKILL.md steps 1-5.

- `Execution` stays `unset` until the user chooses; then it becomes `inline` or
  `subagents` and nothing else. Under `--auto` SKILL.md step 7 picks the value without a
  question and adds its reason after it (`inline - two tasks`); the value stays the
  first word.
- `Produces` and `Consumes` of neighboring tasks must name the same signature or format
  with the same spelling.
- `Covers` lists only criteria this task makes observable. A criterion no task covers is
  a hole in the plan.
- An exact expected output in `RED`, `GREEN`, or `Check` that follows from a formatting
  rule is computed by a script, never by hand (SKILL.md step 5); a run of existing code
  gives it only for behavior the spec says does not change,
  for example `**GREEN:** ... -> <expected> (computed: <command that reproduces it>)`; a
  value that could not be computed reads `check during execution`.
- `Commit` names the task's own paths. A bare `git add .` or `git add -A` without paths
  sweeps in unrelated edits. A file listed in `Initial dirty state` takes only the task's
  own hunks (`implement` step 5).
- A task is self-contained for a fresh agent: files, context, when it is done, check
  commands, and what not to touch; its dependencies are explicit in `Depends on`.
- `Outward: <what and where>` marks a task that acts outside the repository. It runs
  only after a full `PASS` and a closed review, with its own confirmation, also under
  `--auto`; a `Check` that acts outward moves into such a task. A criterion only such
  tasks cover is `deferred to Task <n>` in the `verify` report and does not block `PASS`.
  Already authorized defer issue/reply actions and the bounded REJECT reply in
  `cr-received` may proceed under `--auto`; other outward gates remain in force.

## Execution record format

The record is the last section of the plan. In a plan from this template its lines sit
inside a ```` ```text ```` block, and later skills add new lines at the end of that block,
right before its closing ```` ``` ````, never after it at the end of the file: a line
after the fence renders as a paragraph, and a skill reading the block misses it. Append
with an edit that inserts before the fence, not with `>>`. A record without a fence (one
started before aw 0.0.11) takes new lines at its end. Existing lines are never
rewritten, except the state of a task line.

Record host: the plan when there is one (argument, conversation, or `Branch:` of its record);
otherwise the spec (argument, conversation, or `Branch:` of its `## Verification record`;
before the first write there, only the argument or the conversation); otherwise none. With
no host there is no verdict file: the `Verify:` line is printed in the report only, and the
`finalize` gate does not apply.

A spec's `## Verification record` is its optional last section: the same fenced block,
first line `Branch: <name>`, then the same lines under the same rules. The first skill
that writes there (`implement` or `verify`) creates it. The tree fingerprint excludes the
record host, plan or spec.
Appending lines to a spec's `## Verification record` is not a material change and does
not reset its approval.

```text
Base: <full SHA>   Root: <path>   Branch: <name>
Commits: allowed | ask once | forbidden
Initial dirty state: <paths or none>
Task <n>: pending | in progress | done | blocked - <evidence: command -> result>
Ruling: <decision> - <reason> - <cost if wrong>
Deferred: <item> - <owner or place>
Verify: <verdict> <full|compact> tree <tree SHA> <YYYY-MM-DD HH:MM> [working]
Review R<n>: <Summary line> tree <tree SHA> reviewer <model> mode <code|document|re-review>
Finding R<n>-F<k>: <severity> <location> - <title>
Received R<n>: <ID> <ACCEPT|REJECT|PARTIAL|DEFER|ESCALATE|OUTDATED>, ... Re-review: <needed|not needed>
Round <loop> <n>: <cause>
```

Named `Ruling` forms:

```text
Ruling: R<n>-F<k> superseded by <Task <n> | R<m>-F<k> | marker> - <reason> - <cost if wrong>
Ruling: R<n>-F<k> escalation decided - <owner's decision> - <cost if wrong>
Ruling: round R<n> started by the user past the limit - <user's words> - <cost if wrong>
Ruling: no review - <user's reason> - <cost if wrong>
Ruling: <choice> over <alternative> - <reason> - <cost if wrong>
Ruling: spec re-approved - <YYYY-MM-DD>
Ruling: plan revised after spec re-approval - <spec path>
```

| Writer | Lines |
| --- | --- |
| `specify` | `Ruling: spec re-approved - <YYYY-MM-DD>` in the spec's record |
| `plan-craft` | `Base: unset`, `Task <n>: pending` (placeholders of a new plan, new tasks of a revision); on a revision after spec re-approval, `Ruling: plan revised after spec re-approval - <spec path>` before the delta tasks; `Ruling: R<n>-F<k> superseded by ...` |
| `implement` | `Base`, `Root`, `Branch`, `Commits`, `Initial dirty state`, `Task`, `Ruling` (`<choice> over <alternative>`, `superseded by`, others), `Deferred`; as orchestrator, a subagent's `Verify` line verbatim; with no plan, the spec's record starting with `Branch` |
| `verify` | `Verify` (ending in `working` on uncommitted own work); with no plan, the spec's record starting with `Branch`; with no plan and no spec, no file |
| `cr-request` | `Review`, `Finding` |
| `cr-received` | `Received`, `Ruling` (`superseded by`, `escalation decided`, others), `Deferred` |
| `finalize` | `Ruling: no review - <user's reason> - <cost if wrong>` |
| a skill that starts a round past the limit (`verify`, `cr-request`, `cross-cr`) | `Ruling: round R<n> started by the user past the limit - ...` |
| any skill with a loop | `Round` |
