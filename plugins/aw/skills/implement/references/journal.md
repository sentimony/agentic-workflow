# Execution record, spec record, and resume

The plan is the single state file of a change. Its last section, `## Execution record`,
is the journal every skill in the chain reads and extends. Without a plan, the spec's
`## Verification record` takes the same lines.

Contents: line format, lines this skill writes, record in the spec, resume.

## Line format

The whole chain uses one format. New lines go at the end of the record: inside its
```` ```text ```` block when it has one, right before the closing fence and never after it
(plan-craft's `references/plan-template.md`, "Execution record format"). Existing lines
are not rewritten, except the state of a `Task` line.

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

## Lines this skill writes

`implement` writes `Base`, `Root`, `Branch`, `Commits`, `Initial dirty state`, `Task`,
`Ruling`, `Deferred`, and its own `Round` lines. `Verify`, `Review`, `Finding`, and `Received`
belong to other skills; read them, never write them, except the `Verify:` line a
subagent returns, which the controller appends verbatim. `plan-craft` writes only these
record lines (its SKILL.md, step 5): `Base: unset` and `Task <n>: pending` placeholders
of a new plan, `Task <n>: pending` for the new tasks of a revision after review, and,
on a revision after spec re-approval, the marker
`Ruling: plan revised after spec re-approval - <spec path>` followed by the delta
`Task <n>: pending` lines, appended at the end of the record right before the closing
fence like every new line. `verify` counts only the code reviews after the last marker.

- **Start.** `plan-craft` leaves the placeholder `Base: unset`, meaning execution has not
  begun. Fill that placeholder line with the real values (it is a placeholder, like a
  `pending` task state, not a record), then add under it the `Commits` line with the
  commit-policy answer (skill, step 5; `ask once` only while the question is open, and a
  later answer is a new `Commits` line) and `Initial dirty state`, with each path someone
  already staged marked `(staged)`:

  ```text
  Base: 3f9c2a7e1b4d8f6a0c5e9b2d7f1a4c8e6b3d0f92   Root: /path/to/repo   Branch: feature-x
  Commits: allowed
  Initial dirty state: README.md, src/config.ts (staged)
  ```

  `Base` is the full object ID of `HEAD` before the first task. `Root` is the
  absolute path of the working tree the tasks run in (the worktree, when one was made).

- **Task state.** Change the state of the task's own line in place. Every state except
  `pending` carries evidence: a command and what it returned.

  ```text
  Task 2: in progress - started at 3f9c2a7
  Task 2: done - npm test -- parser -> 14 passed
  Task 4: blocked - missing credentials: <API_TOKEN> for the staging API
  ```

- **Ruling.** One line per decision, with the reason and what it costs if the decision is
  wrong. The agent rules on its own on approach drift, on a choice the spec treats as
  equal, on a fix chosen among options that change neither the spec, a public contract,
  data, nor security (Step 7 of the skill, the `over` form), on a task that removes an
  accepted fix (`superseded`), and on a task returned to `pending` after a `FAIL`. A goal
  drift and any other choice between fixes go to the user, and the ruling says it is
  awaiting the user in the decision:

  ```text
  Ruling: use the renamed parseConfig instead of loadConfig - the plan predates the rename - low, a call site
  Ruling: early return over a guard flag - same behavior, shorter diff - low, one function
  Ruling: R2-F1 superseded by Task 6 - Task 6 removes the retry R2-F1 added - medium, the retry may still be wanted
  Ruling: Task 3 back to pending - Verify FAIL on AC4 - low, the task reruns
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

## Record in the spec

Without a plan, nothing new is created in the plans folder. With a spec, the edit's lines
go into the spec's `## Verification record`, its optional last section. The first skill
that writes there (`implement` or `verify`) adds it as a ```` ```text ```` block whose first
line is `Branch: <name>`, followed by `Commits`, `Initial dirty state`, `Task`, `Verify`,
`Round`, `Review`, `Finding`, `Received`, `Ruling`, and `Deferred` lines under the same
append rules as a plan's record. Appending there is not a material change of the spec,
and the tree fingerprint leaves the record host out. With no spec either, there is no
record file: the evidence and the `Verify:` line appear in the report only. Credentials
never appear in a record; use placeholder names such as `<API_TOKEN>`.

````markdown
## Verification record

```text
Branch: fix-timeout
Commits: allowed
Initial dirty state: none
Task 1: done - npm test -- client -> 9 passed
```
````

A plan-journal started before 0.0.5 stays valid and is read and finished as before: it
is finished once `Base` is set and its evidence (a `Task` line or a `Ruling`) is written.

## Resume

When `Base` is already set, execution is being resumed:

1. Read the whole record, the plan, and `git log <Base>..HEAD` with `git status`.
2. For every task marked `done`, look for its trace: a commit in that range touching the
   task's `Files`, or the task's changes present in the working tree. A `done` task with
   no trace in the tree or the history goes back to `pending`, and a `Ruling` line says
   why.

   A `done` task whose `Files` overlap the `Files` of any later-numbered `done` task
   with a trace reruns its own `GREEN` or `Check`; a later task still `in progress`
   holds partial work and triggers no recheck. Passing, it stays `done`. Failing where
   that later task's `Produces`, a later `Ruling: plan revised after spec re-approval`
   marker, or the partial work of a task still `in progress` accounts for the failure, it
   stays `done` with a `Ruling` line naming that task or marker. Only a task with a higher
   number than the rechecked one can account for its failure. A failure that only the
   partial work of an unfinished task explains is checked again as soon as that task is
   `done`, and that recheck follows this same rule. Any other failure sends it back to
   `pending` with a `Ruling` line naming the check, and it runs as an ordinary task.
   Other `done` tasks stay `done` on their trace.

   ```text
   Task 2: pending
   Ruling: Task 2 back to pending - its Check failed after Task 4 edited the same file - medium, the later edit may have broken it
   ```
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
7. The last `Verify` line is a `FAIL`: each failing claim returns the task that covers it
   to `pending` with a `Ruling` naming the claim, and a claim with no task goes to
   `plan-craft` (skill, step 1, re-entry after `FAIL`).
