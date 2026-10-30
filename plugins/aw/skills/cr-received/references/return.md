# Return Block, Journal Lines, and the Repeat Call

## Repeat call

Check this before step 1. A review counts as already resolved when all of these hold:

- the record (the plan's `## Execution record`, or without a plan the spec's
  `## Verification record`) has a `Received R<n>` line for this review round;
- the review itself is unchanged: the same thread update time for a PR, or the same
  content (`sha256`) for a saved file;
- the reviewed head SHA in the review is the one the earlier records were made against;
- the current tree fingerprint (the `## Committed tree` recipe in
  [tree-fingerprint.md](tree-fingerprint.md)) equals the `Tree` recorded in the identity
  record after the fixes.

Then print the decision table rebuilt from that `Received` line and its records, and the
return block with `Previous verification` worked out against the current tree. Edit no
file and append no journal line. A mismatch in any item is new input: resolve again from
step 1, keep the earlier records and their IDs, and decide only what is new or changed.

Without a plan or a spec record, the same check runs against the records still in the
conversation.

## Journal lines

When the plan is known, append at the end of its `## Execution record`; without a plan,
at the end of the spec's `## Verification record` when it has one. Write inside the
record's ```` ```text ```` block right before the closing fence when it has one (never
after the fence), in exactly this format; existing lines are never rewritten:

```text
Received R<n>: <ID> <ACCEPT|REJECT|PARTIAL|DEFER|ESCALATE|OUTDATED>, ... Re-review: <needed|not needed>
Ruling: <decision> - <reason> - <cost if wrong>
Ruling: R<n>-F<k> escalation decided - <owner's decision> - <cost if wrong>
Ruling: R<n>-F<k> superseded by <Task <n> | R<m>-F<k> | marker> - <reason> - <cost if wrong>
Deferred: <item> - <owner or place>
Round <loop> <n>: <cause>
```

- `Received` - one line per review round, listing only that review's records by ID. A
  record whose assessment is `OUTDATED` is listed as `OUTDATED`; every other record
  gets its disposition.
- `Ruling` - one line per judgement call: a `PARTIAL` remedy chosen instead of the
  suggested one, a set-aside row ruled in or out, a reading of an unclear contract, a
  conflict between two findings settled by the governing contract.
  `escalation decided` closes an open `ESCALATE`, written only from the user's words;
  `superseded` marks an accepted fix that a later task, finding, or marker removed on
  purpose, and needs no user consent.
- `Deferred` - one line per `DEFER`, naming the item, its owner, and where it is tracked.
- `Round review <n>` - one line per review round, with the mechanism the findings hit
  as the cause. `n` equals the review number `R<n>` of the `Received` line; skip the line
  when the journal already has `Round review <n>` from `cr-request`.

Without a plan or a spec record, write nothing: the same lines go under
`Rulings for the execution record` in the return block. The record lines go into the
round commit `Address R<n> findings: <IDs>` (step 9 of `SKILL.md`).

## Return block fields

```text
Changed paths: <paths or none>
Previous verification: stale | still valid (tree unchanged)
Checks to rerun: <per finding>
Re-review: needed (<reason>) | not needed (<reason>)
Blocking: <open ESCALATE items of all rounds or none>   Deferred: <DEFER items with owner>
Rulings for the execution record: <lines or none>
Durable rulings: <paths or none>
Route: verify | specify | plan-craft (<why>)
```

- `Changed paths` - every path the fixes touched, untracked files included.
- `Previous verification` - `stale` whenever `Changed paths` is not `none`, even when
  the fixes are still uncommitted and the committed fingerprint has not moved, and
  whenever the tree fingerprint moved since the last `Verify` line, a durable-ruling
  comment included; `still valid (tree unchanged)` only when neither holds.
- `Checks to rerun` - for each resolved ID, the command that proves it.
- `Re-review` - the step 8 decision and its reason.
- `Blocking` lists every `ESCALATE` still open, from this round and every earlier one,
  under its original ID, until a `Ruling: R<n>-F<k> escalation decided - ...` line closes
  it; `Deferred` lists every `DEFER` with its owner. A pending or failed defer action
  blocks.
- `Durable rulings` - the paths that got a comment or an `AGENTS.md` sentence for a ruling
  to leave code as it is (step 5 of `SKILL.md`); `none - document review` for a spec or
  plan review.
- `Route` - `verify` after code fixes; `specify` when a fix needs a spec decision
  changed; `plan-craft` when the plan needs new or changed tasks.

Document variant (review of a spec or plan): `Changed paths` lists the changed sections
as `§<heading>`, `Previous verification` gives the new `sha256` of the file, and `Route`
is `plan-craft` for a plan or `specify` for a spec. An accepted fix that materially
changes an approved spec (a decision, behavior, contract, or criterion) sets its `Status`
to `draft` in the same edit, and `Changed paths` lists `§Status` too; a typo-level fix
keeps `approved`.

The line right after the block is `Next step:` naming the same skill as `Route`, except
that any `ESCALATE` makes it `Next step: none - awaiting user`.

## Replies to the reviewer

Replies state facts: what changed and where, or why the finding does not hold, with
the evidence. No praise or thanks in place of a fix, and no fix announced before it
is verified. A correction of your own earlier pushback is one factual line. Post
replies to a review thread when authorized, in that same thread. Under `--auto`,
already authorized defer issue and reply actions may proceed. With CI, the host only
proposes a defer and replies; the yngwald reviewer accepts or declines the proposal
on the same head, and trusted publish creates the issue, replies, and resolves the
thread after acceptance. Without CI, the host decides from evidence and
authorization and uses the configured repository account for those actions. An
accepted Minor or Important defer creates one issue in the code repository with
thread link, origin ID, severity, reason, and owner. Record the `DEFERRED #<issue>`
and API evidence of issue, reply, and resolve in the existing host before the gate
closes. Pending or failed writes block; retry reuses the issue and completes only
missing actions. Critical findings cannot use this mechanism. `DECLINED` declines
defer and leaves the finding unresolved.

The host may also reply REJECT only in the current PR/head's yngwald finding thread.
Include human-readable evidence and the schema-valid `cr-received-disposition:v1`
marker defined in `cr-request/references/review-actions.md`: repository, PR, origin
review ID, original finding ID, reviewed SHA, disposition, reason, and remaining
required fields. The API reader takes actor and time from the comment container,
never marker JSON. REJECT is distinct from DECLINED and does not resolve a thread or
create an issue. Before writing, check PR/head, root author, finding key, and all
existing markers; matching disposition, reason, and reviewed head reuse the existing
reply. A changed marker or head fails closed as `marker_conflict`, pending
reconciliation, without write or treating an old disposition as the new one. Recheck
head before POST; after an ambiguous POST read back rather than blindly retry.
Serialize host writers per finding. These guards do not grant a write token to the
reviewer.
