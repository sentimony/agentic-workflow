# Execution record, plan-journal, and resume

The plan is the single state file of a change. Its last section, `## Execution record`,
is the journal every skill in the chain reads and extends.

Contents: line format, lines this skill writes, plan-journal, resume.

## Line format

The whole chain uses one format. New lines go at the end of the record: inside its
```` ```text ```` block when it has one, right before the closing fence and never after it
(plan-craft's `references/plan-template.md`, "Execution record format"). Existing lines
are not rewritten, except the state of a `Task` line.

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

## Lines this skill writes

`implement` writes `Base`, `Root`, `Branch`, `Initial dirty state`, `Task`, `Ruling`,
`Deferred`, and its own `Round` lines. `Verify`, `Review`, `Finding`, and `Received`
belong to other skills; read them, never write them. `plan-craft` writes only these
record lines (its SKILL.md, step 5): `Base: unset` and `Task <n>: pending` placeholders
of a new plan, `Task <n>: pending` for the new tasks of a revision after review, and,
on a revision after spec re-approval, the marker
`Ruling: plan revised after spec re-approval - <spec path>` followed by the delta
`Task <n>: pending` lines, appended at the end of the record right before the closing
fence like every new line. `verify` counts only the code reviews after the last marker.

- **Start.** `plan-craft` leaves the placeholder `Base: unset`, meaning execution has not
  begun. Fill that placeholder line with the real values (it is a placeholder, like a
  `pending` task state, not a record), then add `Initial dirty state` under it:

  ```text
  Base: 3f9c2a7e1b4d8f6a0c5e9b2d7f1a4c8e6b3d0f92   Root: /path/to/repo   Branch: feature-x
  Initial dirty state: none
  ```

  `Base` is the full 40-character SHA of `HEAD` before the first task. `Root` is the
  absolute path of the working tree the tasks run in (the worktree, when one was made).

- **Task state.** Change the state of the task's own line in place. Every state except
  `pending` carries evidence: a command and what it returned.

  ```text
  Task 2: in progress - started at 3f9c2a7
  Task 2: done - npm test -- parser -> 14 passed
  Task 4: blocked - missing credentials: <API_TOKEN> for the staging API
  ```

- **Ruling.** One line per decision, with the reason and what it costs if the decision is
  wrong. The agent rules on its own only on approach drift and on a choice the spec
  treats as equal, where the options do not differ in behavior. A goal drift, options
  that change behavior, and a defect with several reasonable fixes (Step 7 of the skill)
  go to the user, and the ruling says it is awaiting the user in the decision:

  ```text
  Ruling: use the renamed parseConfig instead of loadConfig - the plan predates the rename - low, a call site
  Ruling: awaiting user - retry with backoff or fail fast on timeout - both fit the spec - behavior on outages
  ```

- **Deferred.** Out-of-scope items noticed during a task, with an owner or a place:

  ```text
  Deferred: flaky date test in utils - follow-up issue
  ```

- **Round.** `Round task-<n> <k>: <cause>` for each round of task `<n>` as Step 7 of the
  skill defines it (another try at a failing check, or a changed re-dispatch after
  `NEEDS_CONTEXT` or `BLOCKED`); a mechanical fix rerun inside the same round adds no
  line.

Keep the journal proportional: a short plan needs one line per task and nothing more.

## Plan-journal

When there is no plan and the change is one or two obvious edits, create the smallest
plan that can hold the journal. Path: the project's plans folder when its instructions or
existing files define one, else `docs/plans/YYYYMMDD-HHMM-<topic>.md`. Credentials never
appear in it; use placeholder names such as `<API_TOKEN>`.

```markdown
# <topic>

**Spec:** none

**Goal:** <one sentence with the domain values of the request: names, numbers, behavior>

**Execution:** inline

### Task 1: <title>

**Files:** <paths>

**Check:** <command> -> <expected result>

**Commit:** `git add -A -- <paths>`

## Execution record

Base: unset
Task 1: pending
```

With no task block (a single edit that needs none), the record still gets `Base` and
`Initial dirty state`, and the evidence (command and result) goes into a `Ruling` line;
the report repeats it. Such a plan-journal has no `Task` lines to be `done`: it is
finished once `Base` is set and that evidence is written, and the next step is `verify`.
While `Base` is still `unset` it is unfinished, as in plan-craft's rule. A plan that
already exists with an unfinished journal is never overwritten; a new change gets a new
file.

## Resume

When `Base` is already set, execution is being resumed:

1. Read the whole record, the plan, and `git log <Base>..HEAD` with `git status`.
2. For every task marked `done`, look for its trace: a commit in that range touching the
   task's `Files`, or the task's changes present in the working tree. A `done` task with
   no trace in the tree or the history goes back to `pending`, and a `Ruling` line says
   why.
3. A task `in progress` is inspected: keep the partial work that matches the task, rerun
   its check, and continue from there.
4. Continue `Round` counters from the last recorded number for each loop.
5. A `Ruling` awaiting the user stays open until the user answers; do not decide it
   because the session is new.
6. A task `blocked - conflicting intent: spec <path> back to draft` whose spec now reads
   `Status: approved` goes back to `pending`: change the state of its own line in place
   and add a `Ruling`. It then runs as its task section now reads, after `plan-craft`
   revised the plan; the delta tasks `plan-craft` added are ordinary `pending` lines.
   While the spec is still a draft, the line stays `blocked`.

   ```text
   Task 3: pending
   Ruling: Task 3 back to pending - spec docs/specs/x.md approved again - low, the task section was revised
   ```
