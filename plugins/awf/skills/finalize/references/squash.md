# Squash merge on the forge

Used by the `squash` option. The examples use the GitHub CLI; on another forge, use its
equivalent for each step and keep the same order and the same checks. Run every step
only after the user chose `squash` in this conversation.

## Before the merge

1. Re-read the state (SKILL.md "Read the state") and the gate ("Gate on the verdict"),
   including its rule that nothing outside the plan is uncommitted. The PR head must be
   the local `HEAD`: `gh pr view <pr> --json headRefOid` prints the full SHA of
   `git rev-parse HEAD`. Then the PR carries the content the `Verify: PASS` line names;
   a different head stops the merge, and a later push needs a new verdict.
2. Confirm the PR title and body describe the whole branch
   ([pr-body.md](pr-body.md)): the squash commit takes the PR title as its subject.
3. Wait for the required checks. Read them, do not guess:

   ```sh
   gh pr checks <pr> --required --watch
   ```

   A failing or pending required check stops the merge. Report it; the fix belongs to
   `implement` or `cr-received`, and the new tree goes back through `verify`.

## The merge

Pin the merge to the head that was verified, so a push that lands in between makes the
merge fail instead of merging unverified commits. The option takes the full 40-character
SHA; a short prefix is rejected.

```sh
head="$(git rev-parse HEAD)"
gh pr merge <pr> --squash --match-head-commit "$head"
```

Delete the branch, in this command (`--delete-branch`) or after it, only when the user
asked for it and the branch barrier in SKILL.md "Clean up behind two barriers" allows
it.

Never bypass branch protection or required checks with `--admin`, and never retry a
rejected merge with a bypass flag. A rejection is reported to the user as it is.

## After the merge

In the worktree that has the base checked out (`git worktree list`), or after
`git switch <base>` when none has:

```sh
git fetch --prune
git pull --ff-only
```

`--ff-only` refuses to create a merge commit when the local base has diverged; report
that case instead of resolving it.

When the user asked to delete the branch, confirm it is gone in both places, each
command printing nothing:

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
