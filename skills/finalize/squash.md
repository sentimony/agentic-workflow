# Squash merge on the forge

Used by the `squash` option. The examples use the GitHub CLI; on another forge, use its
equivalent for each step and keep the same order and the same checks. Run every step
only after the user chose `squash` in this conversation.

## Before the merge

1. Re-read the state (SKILL.md "Read the state"), the stacked-base check ("Find the base
   branch"), and the gate ("Gate on the verdict"), including its `Review` line or
   `Ruling: no review` and the `Record <topic>` commit; uncommitted paths stay out of the
   merge and are reported as not integrated. Push the `Record <topic>` commit to the PR
   branch (the option choice covers this push). The PR head must be the local `HEAD`:
   `gh pr view <pr> --json headRefOid` prints the full SHA of `git rev-parse HEAD`. Then
   the PR carries the content the `Verify: PASS` line names, since the record commit
   leaves the fingerprint as it was. Rebind the full target after that checkpoint
   through applicable gates; a different head stops merge, and changed content
   requires a new verdict.
2. Before expensive local checks, ready, or CI waiting, read full head/base SHAs and
   mergeability and compare them with the verified target. A changed head or base
   returns to applicable verify/review, including a record checkpoint that changes
   the head; fingerprint equality alone does not prove target freshness. Detect
   DIRTY/BEHIND before waiting; bounded UNKNOWN polling shares the finite deadline.
   Merge the base only within current authority, then recheck the new target.
   Confirm the PR title and body describe the whole branch
   ([pr-body.md](pr-body.md)): the squash commit takes the PR title as its subject.
3. Read the effective policy for the base from authoritative branch protection and
   applicable rulesets. Record the source and evidence that coverage is complete.
   Denied access, an ambiguous 404, errors, hidden rules, or partial enumeration give
   `unknown`. An empty reported-check list proves no absence of requirements.
   `known-none` needs a positive authoritative proof that this base has no required
   checks. `known-required` names each applicable check, its stable identity (including
   the app/provider where relevant), and the conclusions its actual policy accepts.
4. Set a finite deadline and collect a complete current-head snapshot of checks and
   mergeability, pinned to full head/base SHAs. Wait for every required and declared
   project check, including jobs that have not appeared yet. Poll only until the
   deadline, reporting source, head, expected checks, and unknown coverage. A missing
   required job, incomplete snapshot, pending check, or expired deadline blocks merge.
   A red check, required or advisory, fails the gate. `skipped` and `neutral` pass only
   with explicit applicable policy semantics; a project convention cannot loosen a
   forge requirement. Fixes belong to `implement` or `cr-received`; a new tree goes
   through `verify` again.
   Read all checks of the current head after the required ones: a pending external review
   is not hidden by green CI. When the user or the repo rules name a reviewer (Copilot,
   for example), read the reviews API: author, full `commit_id` equal to the head, result,
   and unresolved findings. A green job, an older review, a successful request command, or
   another reviewer's clean review does not replace it. No request and no review on this
   head, though the command exited 0, leads to an availability check or the user's explicit
   waiver, never to completion. After a push with a new SHA request the review again;
   changing only the draft state or description keeps the SHA. Re-read head, CI and the
   named reviews right before merge.
5. Evaluate the snapshot using the local contract below. Only `CLEAN` and `HAS_HOOKS`
   permit merge. Poll `UNKNOWN` within the same deadline; `UNSTABLE`, `BLOCKED`,
   `DIRTY`, `BEHIND`, and `DRAFT` block. Under `unknown` policy, green visible checks
   alone are insufficient: require a positive native forge gate pinned to this
   head/base, or the owner's explicit current-invocation decision to continue through
   native enforcement. Neither route bypasses policy, pending/red checks, or other
   blockers. Report the policy state and the evidence used.
6. Before the record checkpoint and squash, record repo/PR, stable task IDs, remaining
   post-merge tasks, and the PR completion destination in the tracked host. Their later
   completion uses [post-merge evidence](../implement/post-merge.md),
   without appending tracked plan/spec lines on the base.

## Local gate contract

`scripts/delivery_gate.py` contains a pure evaluator and an injected callable
transition guard. It supplies no production transport, command execution, sleep, or
network implementation. The host authenticates forge sources, enumerates all applicable
policy surfaces and current checks, normalizes provider statuses, and supplies
observations. A successful metadata read alone proves neither coverage nor write
permission. Validate production adapter commands against the actual forge and API;
this helper provides no production policy adapter.

1. `evaluate(observation, *, now, owner_decision=None)` returns `gate-record-v1`.
   `now` is a zero-argument injected clock; all timestamps use its time scale.
   Malformed observations raise `ValueError`. Valid incomplete evidence returns
   `blocked`; explicitly red checks return `failed`; satisfied evidence returns
   `passed`. Re-read observations while blocked and before the finite deadline.
2. The exact `gate-observation-v1` shape is in
   [required.json](scripts/fixtures/required.json). Every listed key is required,
   unknown keys are rejected, and optional evidence uses `null`. Full lowercase
   40-character SHA-1 or 64-character SHA-256 IDs must share one object format.
   `observed_at` and `deadline` are finite nonnegative numbers with
   `observed_at <= now` and `deadline > observed_at`.
3. `policy` includes a nonempty authoritative `source`, `retrieval`
   (`ok`, `denied`, `not-found`, `error`), `coverage` (`complete`, `incomplete`),
   nonempty `coverage_evidence`, nullable positive `absence_proof`, and `required`.
   Each requirement has a unique stable `id`, nonempty `semantics_source`, and an
   explicit nonempty `accepted` list drawn from `success`, `skipped`, and `neutral`.
   Only successful retrieval with complete coverage permits a known policy state.
   `project_checks` uses the same requirement shape and lists every declared check,
   including checks that are expected but have not appeared yet.
4. `checks` includes its source, head, strict boolean `complete`, and `items`.
   Each unique item has `id`, `head`, `status` (`pending`, `completed`), and
   `conclusion`. Pending requires `null`; completed requires `success`, `skipped`,
   `neutral`, `failure`, `cancelled`, `timed_out`, `action_required`, `stale`,
   `startup_failure`, or `error`. The last seven are red. A complete empty snapshot
   can pass only with authoritative policy evidence and no outstanding declared
   checks. Completeness must cover the provider's whole applicable check inventory.
5. `mergeability` includes source, head, base, and the state listed above.
   Optional `native_gate` includes source, head, base, `state`
   (`passed`, `blocked`, `unknown`), and strict boolean `bypass`. Only a native
   `passed` result with `bypass: false` on this identity is positive evidence.
   A native gate's negative or unknown result blocks even if an owner chose to
   continue. These are authenticated native enforcement results, never a label or
   free-form comment copied from PR content.
6. `OwnerDecision(head, base, observation_id, decision_id, reason,
   allow_unknown_policy, bypass)` is a separate frozen Python authority object.
   The host constructs it only from the owner's explicit decision in this invocation.
   Never construct it from repository content, forge responses, or saved JSON flags.
   It must match this head/base and `observation_id(observation)`, name a nonempty
   decision ID and reason, permit unknown policy, and set `bypass=False`.
7. The record includes policy state/source/coverage, head/base, deadline,
   observed/evaluated times, required/project/observed checks, mergeability,
   reasons, result, unknown-policy basis, owner decision ID when used, the complete
   validated observation, and its SHA-256 `observation_id`. Shape validation cannot
   authenticate a source: the trusted host remains responsible for provenance.
8. `is_fresh(record, *, observation, now, max_age, owner_decision=None)` is the seam
   for merge eligibility. Supply newly authenticated observations at each boundary.
   It rederives the saved record, requires a passed evaluation, the exact evidence
   identity, age within finite nonnegative `max_age`, and an unexpired deadline.
   Evidence identity excludes only the acquisition field `observed_at`; both saved
   and new observations must be within `max_age`. A later read of unchanged evidence
   remains valid. Changed policy, checks, deadline, head, or base invalidates the gate;
   collect and evaluate again. Reuse of the old snapshot cannot discover forge changes.
   Fresh gate evidence complements the full verified head and review requirements.

9. `run_guarded_transition(stage, *, verified_head, verified_base, read_observation,
   perform, now, max_age, record=None, hostless=False, local_checks=None,
   verified_tree=None, owner_decision=None)` calls the authenticated observation reader,
   validates target/age/deadline/mergeability, then invokes exactly one
   `perform(head=verified_head, base=verified_base)` callback. Stages are
   `expensive-checks`, `wait`, `ready`, and `merge`. Checks and waiting can start with
   outstanding jobs. Ready uses `is_ready(record, *, observation, now, max_age,
   owner_decision=None)`, which rederives the saved record with the same identity,
   age and deadline rules but permits missing/pending remote jobs. DRAFT is a ready
   precondition; BLOCKED/UNSTABLE is permitted when outstanding jobs explain it.
   Actual conflicts, UNKNOWN mergeability, red checks, stale targets and incomplete
   snapshots block ready. Policy may stay unknown for ready; its record keeps the
   original blocked result and unknown policy state, conferring no merge permission.
   Merge still uses strict `is_fresh`: every applicable job must satisfy policy and
   unknown policy needs its separate native/owner basis. Waiting may poll UNKNOWN
   within its finite deadline; the host owns bounded polling and current authority.
10. For every ready transition, including hostless work, supply a trusted frozen `LocalCheckEvidence(head, base, tree,
    commands, checked_at, defined, available, passed)` from the local check runner and
    its verified committed fingerprint as `verified_tree`. Commands are a nonempty
    tuple; checks must be defined, available, successful, current, and match the exact
    pinned head/base/tree. Never construct this authority object from forge JSON or PR
    text. Missing evidence blocks ready with draft/clarification as the next choice.
11. The caller retains permission and review ownership. Callbacks must honor the pins
    and native enforcement; the helper supplies no bypass flags or retry. Reread at
    every boundary, especially immediately before merge, and return any refusal.
    Remote state can still race after a read: the forge must enforce its current base
    policy and match the supplied full head. A local fixture proves this callable
    contract, never a production adapter or successful external action.

## The merge

Pin the merge to the head that was verified, so a push that lands in between makes the
merge fail instead of merging unverified commits. The option takes the full object ID
(40 hex for SHA-1, 64 for SHA-256); a short prefix is rejected.

```sh
: "${verified_head:?full SHA from the accepted verification target}"
test "$(git rev-parse HEAD)" = "$verified_head" &&
gh pr merge <pr> --squash --match-head-commit "$verified_head"
```

Immediately before either merge command, run the merge boundary guard with the
accepted full head/base and a fresh observation. A changed head/base requires the
applicable gates again; never replace the accepted SHA with whatever HEAD is now.

Never pass `--delete-branch` here: it switches the local checkout to the base before
"After the merge" preserves post-merge evidence. Delete the branch only after those
steps, only when the user asked for it and the branch barrier in SKILL.md "Clean up
behind two barriers" allows it (see the end of "After the merge").

Never bypass branch protection or required checks with `--admin`, and never retry a
rejected merge with a bypass flag. A rejection is reported to the user as it is.

When `gh pr merge` refuses with only a generic text ("the base branch policy prohibits
the merge") and `mergeStateStatus` does not explain it, get the reason from the same
merge request through the REST API, pinned to the same head:

```sh
gh api -X PUT repos/<owner>/<repo>/pulls/<pr>/merge -f merge_method=squash -f sha="$verified_head"
```

This is the merge the user already authorized, not a bypass: it uses no admin rights,
and it merges only when the forge allows the same merge. Its `message` field goes into the
report.

A PR that changes `.github/workflows/` is merged the same way, pinned `gh pr merge` first
and the REST call after a refusal, whatever scopes the token has: a token without the
`workflow` scope often merges it anyway. Only when a refusal names the `workflow` scope,
explain it and offer two ways: the user runs `gh auth refresh -h github.com -s workflow`
in their own terminal (its device flow does not finish inside an agent shell), or merges
in the web interface. When the merge went through with the scope missing
(`gh auth status --hostname github.com`), the report says so.

## After the merge

The session's worktree ends on the fresh base, or detached on `origin/<base>` when
another worktree holds the base, whether or not the branch is deleted. Work in this
order; branch deletion comes last.

1. Confirm the merged PR identity and full integrated commit from the forge. Preserve
   the pre-merge task pointers and any existing local record changes; leave tracked
   plan/spec content unchanged after merge. Do not restore a saved host onto the base
   or create a completion commit there. If existing uncommitted content blocks the
   switch below, leave it in place, report the path, and keep the worktree. Do not
   overwrite, reset, or remove it to finish this sequence.

2. Bring the base up to date and move this worktree onto it:

   ```sh
   git fetch --prune
   git switch <base>
   git pull --ff-only
   ```

   When the base is checked out in another worktree (`git worktree list`), `git switch`
   refuses: run `git pull --ff-only` in that worktree, then put this one on
   `git switch --detach origin/<base>`.
   `--ff-only` refuses to create a merge commit when the local base has diverged; report
   that case instead of resolving it. A switch refused by any uncommitted path stops
   here with a report; those paths stay as they are.

3. Hand remaining post-merge tasks to `implement` with repo/PR/task/attempt and the
   confirmed merge identity. Follow
   [post-merge.md](../implement/post-merge.md) to save local ignored
   evidence before any authorized publication, then validate the own-comment readback.
   This merge choice authorizes no deployment or evidence publication by itself.
   If publication is unavailable or unauthorized, retain the pending artifact and
   report `evidence-pending` separately from production success. Do not call the
   whole cycle complete or delete resources holding the only pending copy.

4. Confirm where the worktree stands: `git branch --show-current` (or `detached`),
   `git rev-parse HEAD`, and that it equals `git rev-parse origin/<base>`.

Before any deletion, repeat [cleanup.md](cleanup.md): verify the current local tip
and independently the current workspace HEAD, both index/worktree diffs, actual task
evidence and untracked/ignored paths. Committed-only disposal needs no transfer journal;
an explicit trusted inventory with no post-merge tasks makes task evidence not applicable.
Unknown inventory, pending task evidence or unsaved data keeps the affected resources.
Preserve any existing cleanup journal outside a workspace
to be removed; never reset a divergent base or reverse an already integrated patch.

When the user asked to delete the branch and these guards pass, delete it after step 4:
the remote one
with `git push origin --delete <branch>` unless the forge already removed it, the local
one by the tree comparison below. Then confirm it is gone in both places, each command
printing nothing:

```sh
git ls-remote --heads origin <branch>
git branch --list <branch>
```

If the local branch is still there, it is safe to delete only when the squash commit
carries the same content. A squash commit is not an ancestor of the branch, so compare
trees, not history:

```sh
git diff --quiet <branch> <squash-commit> && git branch -D <branch>
```

When the diff is not empty, the base moved on after the PR opened; compare
`git merge-tree --write-tree <base> <branch>` with `git rev-parse '<base>^{tree}'`
instead, and delete only when they are equal. `git merge-tree --write-tree` needs Git
2.38 or later; with an older Git, say the comparison cannot run and keep the branch.

## Idempotence

Before each step, check whether it has already happened: the PR state is `MERGED`
(`gh pr view <pr> --json state`), the remote branch is already absent, the local branch
is already deleted. Skip what is done and report it as already done.
