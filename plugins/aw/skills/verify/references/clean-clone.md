# Clean clone of an uncommitted tree

Some projects run their checks in a fresh clone (`git clone -q . <tmp>`) to match CI. A
clone takes only committed content, while `verify` often runs on an uncommitted tree that
the user or `finalize` commits later. Rebuild the pinned tree in the clone instead.

A copy of the files without `.git` (`git ls-files -co | rsync -R`, `cp -r`) is not a
clean checkout: a test that reads Git fails in it, or passes for another reason than in
CI.

## Recipe

Run from the repository root, with `<tmp>` a new empty directory outside the repository:

```sh
git clone -q . '<tmp>'
git diff --binary HEAD | git -C '<tmp>' apply --index
```

Then copy only the untracked files that the fingerprint covers (not ignored, not the
plan), keeping their paths (bash, for `read -d ''`):

```bash
git ls-files -z --others --exclude-standard -- . ':!<plan-path>' |
  while IFS= read -r -d '' f; do
    mkdir -p "<tmp>/$(dirname "$f")" && cp -p "$f" "<tmp>/$f"
  done
```

Drop the `':!<plan-path>'` pathspec when there is no plan or it lives outside the
repository.

## Check before trusting it

Compute the fingerprint inside the clone with the recipe in
[tree-fingerprint.md](tree-fingerprint.md), run there with the same `<plan-path>`, and
compare it with the fingerprint pinned in step 1. Equal means the clone holds the tree
under verification; run the project's checks there. Different means the rebuild missed
something: fix the rebuild, and never record checks from that clone as evidence for the
pinned tree.
