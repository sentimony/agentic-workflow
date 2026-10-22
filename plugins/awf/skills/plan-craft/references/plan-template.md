# Plan template

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

<Copied word for word from the spec: decisions, out-of-scope items, security rules.
With `Spec: none`, the constraints the user stated in the conversation.>

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

Write one `Task <n>: pending` line per task, in task order. These two kinds of line are
the only ones `plan-craft` writes into the record; `Base: unset` means execution has not
started.

## Field notes

- `Spec` names the spec the plan serves; the spec ranks above the plan. `none` only when
  the requirements came from the conversation (then the `Acceptance criteria` section is
  required).
- `Global constraints` is a copy, not a summary. A paraphrase drifts from the spec the
  first time someone edits one of the two.
- `Execution` stays `unset` until the user chooses; then it becomes `inline` or
  `subagents` and nothing else.
- `Produces` and `Consumes` of neighboring tasks must name the same signature or format
  with the same spelling.
- `Covers` lists only criteria this task makes observable. A criterion no task covers is
  a hole in the plan.
- `Commit` names the task's own paths. A bare `git add .` or `git add -A` without paths
  sweeps in unrelated edits.
- Stateful logic (caches, retries, ordering, rollback) is written as behavior, invariants,
  and named race scenarios in `Produces` and the steps, not as finished code. Full code
  belongs only to mechanical steps.
- A dimension that does not apply (parallel waves, shared state, isolation) gets
  `n/a: <reason>` once in `Architecture`, not an empty section.

## Execution record format

The record is the last section of the plan. Later skills append lines at the bottom and
never rewrite existing ones, except the state of a task line:

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
| `verify` | `Verify` |
| `cr-request` | `Review`, `Finding` |
| `cr-received` | `Received`, `Ruling`, `Deferred` |
| any skill with a loop | `Round` |

A record is finished when every `Task` line says `done`. Any task line in another state
makes it unfinished, including a plan whose `Base` is still `unset`. A plan with an
unfinished record is never replaced in place; a different plan goes into a new file.
