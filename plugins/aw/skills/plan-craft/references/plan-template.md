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

**Execution:** inline | subagents | unset

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

**Commit:** `git add -A -- <paths>`

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
  `subagents` and nothing else.
- `Produces` and `Consumes` of neighboring tasks must name the same signature or format
  with the same spelling.
- `Covers` lists only criteria this task makes observable. A criterion no task covers is
  a hole in the plan.
- An exact expected output in `RED`, `GREEN`, or `Check` that follows from a formatting
  rule is computed by a script or a run of existing code, never by hand (SKILL.md step 5),
  for example `**GREEN:** ... -> <expected> (computed: <command that reproduces it>)`; a
  value that could not be computed reads `check during execution`.
- `Commit` names the task's own paths. A bare `git add .` or `git add -A` without paths
  sweeps in unrelated edits.

## Execution record format

The record is the last section of the plan. In a plan from this template its lines sit
inside a ```` ```text ```` block, and later skills add new lines at the end of that block,
right before its closing ```` ``` ````, never after it at the end of the file: a line
after the fence renders as a paragraph, and a skill reading the block misses it. Append
with an edit that inserts before the fence, not with `>>`. A record without a fence (a
plan-journal) takes new lines at its end. Existing lines are never rewritten, except the
state of a task line:

```text
Base: <full SHA>   Root: <path>   Branch: <name>
Initial dirty state: <paths or none>
Task <n>: pending | in progress | done | blocked - <evidence: command -> result>
Ruling: <decision> - <reason> - <cost if wrong>
Deferred: <item> - <owner or place>
Verify: <verdict> <full|compact> tree <tree SHA> <YYYY-MM-DD HH:MM>
Review R<n>: <Summary line> tree <tree SHA> reviewer <model> mode <code|document|re-review>
Finding R<n>-F<k>: <severity> <location> - <title>
Received R<n>: <ID> <ACCEPT|REJECT|PARTIAL|DEFER|ESCALATE|OUTDATED>, ... Re-review: <needed|not needed>
Round <loop> <n>: <cause>
```

| Writer | Lines |
| --- | --- |
| `plan-craft` | `Base: unset`, `Task <n>: pending` (placeholders only) |
| `implement` | `Base`, `Root`, `Branch`, `Initial dirty state`, `Task`, `Ruling`, `Deferred` |
| `verify` | `Verify`; with no plan, a new plan-journal with `Branch` and `Verify` |
| `cr-request` | `Review`, `Finding` |
| `cr-received` | `Received`, `Ruling`, `Deferred` |
| any skill with a loop | `Round` |
