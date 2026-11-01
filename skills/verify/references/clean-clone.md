# Clean clone of `HEAD`

`verify` judges the committed tree. When `git status --porcelain` lists any uncommitted
path other than the record host, the checks run in a clean clone of the pinned `HEAD`,
so uncommitted changes, including someone else's, neither help nor break them. The same
clone serves a project that runs its checks in a fresh clone to match CI.

A copy of the files without `.git` (`git ls-files -co | rsync -R`, `cp -r`) is not a
clean checkout: a test that reads Git fails in it, or passes for another reason than in
CI.

## Recipe

Run from the repository root, with `<tmp>` a new empty directory outside the repository
and `<HEAD SHA>` the full SHA pinned in step 1:

```sh
git clone -q --no-checkout . '<tmp>' &&
git -C '<tmp>' checkout -q --detach '<HEAD SHA>'
```

Nothing is applied on top: no diff, no untracked files. Uncommitted paths stay out of
the verdict and are listed in the report.

## Check before trusting it

Compute the fingerprint inside the clone with the `## Committed tree` recipe in
[tree-fingerprint.md](tree-fingerprint.md), run there with the same `<host-path>`, and
compare it with the fingerprint pinned in step 1. Equal means the clone holds the tree
under verification; run the project's checks there. Different means the clone is not
the pinned commit: fix it, and never record checks from that clone as evidence for the
pinned tree.

A `working` run (SKILL.md step 1) judges the working tree itself and runs its checks
there, without a clone.
