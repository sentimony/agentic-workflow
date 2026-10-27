# Return Block, Journal Lines, and the Repeat Call

## Repeat call

Check this before step 1. A review counts as already resolved when all of these hold:

- the plan's `## Execution record` has a `Received R<n>` line for this review round;
- the review itself is unchanged: the same thread update time for a PR, or the same
  content (`sha256`) for a saved file;
- the reviewed head SHA in the review is the one the earlier records were made against;
- the current tree fingerprint ([tree-fingerprint.md](tree-fingerprint.md)) equals the
  `Tree` recorded in the identity record after the fixes.

Then print the decision table rebuilt from that `Received` line and its records, and the
return block with `Previous verification` worked out against the current tree. Edit no
file and append no journal line. A mismatch in any item is new input: resolve again from
step 1, keep the earlier records and their IDs, and decide only what is new or changed.

Without a plan, the same check runs against the records still in the conversation.

## Journal lines

When the plan is known, append at the end of its `## Execution record`, inside the
record's ```` ```text ```` block right before the closing fence when it has one (never
after the fence), in exactly this format; existing lines are never rewritten:

```text
Received R<n>: <ID> <ACCEPT|REJECT|PARTIAL|DEFER|ESCALATE|OUTDATED>, ... Re-review: <needed|not needed>
Ruling: <decision> - <reason> - <cost if wrong>
Deferred: <item> - <owner or place>
Round <loop> <n>: <cause>
```

- `Received` - one line per review round, listing every record by ID. A record whose
  assessment is `OUTDATED` is listed as `OUTDATED`; every other record gets its
  disposition.
- `Ruling` - one line per judgement call: a `PARTIAL` remedy chosen instead of the
  suggested one, a set-aside row ruled in or out, a reading of an unclear contract, a
  conflict between two findings settled by the governing contract.
- `Deferred` - one line per `DEFER`, naming the item, its owner, and where it is tracked.
- `Round review <n>` - one line per review round, with the mechanism the findings hit
  as the cause. `n` equals the review number `R<n>` of the `Received` line; skip the line
  when the journal already has `Round review <n>` from `cr-request`.

Without a plan, write nothing: the same lines go under
`Rulings for the execution record` in the return block.

## Return block fields

```text
Changed paths: <paths or none>
Previous verification: stale | still valid (tree unchanged)
Checks to rerun: <per finding>
Re-review: needed (<reason>) | not needed (<reason>)
Blocking: <ESCALATE items or none>   Deferred: <DEFER items with owner>
Rulings for the execution record: <lines or none>
Route: verify | specify | plan-craft (<why>)
```

- `Changed paths` - every path the fixes touched, untracked files included.
- `Previous verification` - `stale` whenever the tree fingerprint moved since the last
  `Verify` line; `still valid (tree unchanged)` only when it did not.
- `Checks to rerun` - for each resolved ID, the command that proves it.
- `Re-review` - the step 8 decision and its reason.
- `Blocking` lists every `ESCALATE`; `Deferred` lists every `DEFER` with its owner. A
  `DEFER` never blocks.
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

Replies state facts: what changed and where, or why the finding does not hold, with the
evidence. No praise or thanks in place of a fix, and no fix announced before it is
verified. A correction of your own earlier pushback is one factual line. Post replies to
a review thread only when the user asks, in that same thread.
