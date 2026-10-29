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
   leaves the fingerprint as it was; a different head stops the merge, and a later push
   of other content needs a new verdict.
2. Confirm the PR title and body describe the whole branch
   ([pr-body.md](pr-body.md)): the squash commit takes the PR title as its subject.
3. Wait for the required checks. Read them, do not guess:

   ```sh
   gh pr checks <pr> --required --watch
   ```

   When it prints `no required checks reported`, the branch has no required checks and
   the command waited for nothing: wait for all checks of the PR instead.

   ```sh
   gh pr checks <pr> --watch
   ```

   A failing or pending check, required or not, stops the merge. Report it; the fix
   belongs to `implement` or `cr-received`, and the new tree goes back through `verify`.
   Then read `gh pr view <pr> --json mergeStateStatus`. `CLEAN` and `HAS_HOOKS`
   (mergeable, with pre-receive hooks) go on. `UNKNOWN` means the forge is still
   computing: read it again after about 10 seconds, up to five times, and treat a state
   still `UNKNOWN` as a stop. Any other state (`UNSTABLE`, `BLOCKED`, `DIRTY`, `BEHIND`,
   `DRAFT`) stops the merge with the state in the report. The report says which checks
   were read: required, or all because none are required.

## The merge

Pin the merge to the head that was verified, so a push that lands in between makes the
merge fail instead of merging unverified commits. The option takes the full object ID
(40 hex for SHA-1, 64 for SHA-256); a short prefix is rejected.

```sh
head="$(git rev-parse HEAD)"
gh pr merge <pr> --squash --match-head-commit "$head"
```

Never pass `--delete-branch` here: it switches the local checkout to the base before
"After the merge" saves the record. Delete the branch only after those steps, only
when the user asked for it and the branch barrier in SKILL.md "Clean up behind two
barriers" allows it (see the end of "After the merge").

Never bypass branch protection or required checks with `--admin`, and never retry a
rejected merge with a bypass flag. A rejection is reported to the user as it is.

When `gh pr merge` refuses with only a generic text ("the base branch policy prohibits
the merge") and `mergeStateStatus` does not explain it, get the reason from the same
merge request through the REST API, pinned to the same head:

```sh
gh api -X PUT repos/<owner>/<repo>/pulls/<pr>/merge -f merge_method=squash -f sha="$head"
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

1. Save the record. The `Record <topic>` commit usually brought the record host into the
   squash with all its lines. When `git status --porcelain` still lists the host (the
   commit policy forbids commits, or lines were written after that commit), keep its
   content outside the repository and restore the file to `HEAD`, so the switch cannot
   fail on it (`<plan-path>` is the host, plan or spec):

   ```sh
   saved="$(mktemp)"
   cp '<plan-path>' "$saved"
   git checkout -- '<plan-path>'
   ```

   A host that `HEAD` does not track is moved aside instead (`mv '<plan-path>' "$saved"`):
   `git checkout` has no version to restore it to.

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
   that case instead of resolving it. A switch that uncommitted paths outside the host
   refuse stops here with a report; those paths stay as they are.

3. Put the record back: `cp "$saved" '<plan-path>'`, then `git diff -- '<plan-path>'`
   must show only added record lines. Anything else (the base lacks the host, or has
   another version of it) is reported, and the saved copy stays where the report says.
   The record lines stay uncommitted on the base; the report names them and asks whether
   to commit them.

4. Confirm where the worktree stands: `git branch --show-current` (or `detached`),
   `git rev-parse HEAD`, and that it equals `git rev-parse origin/<base>`.

When the user asked to delete the branch, delete it now, after step 4: the remote one
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
