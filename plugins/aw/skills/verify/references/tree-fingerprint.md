# Tree fingerprint

A verdict or a review belongs to the exact content it saw. The fingerprint is a Git tree
ID without the record host: the plan that holds the `## Execution record`, or the spec
that holds the `## Verification record`. The host is left out because the chain writes
its record lines there: a fingerprint that included it would go stale with every
`Verify`, `Review`, or `Received` line.

There are two recipes in this file:

- `## Committed tree` - `HEAD^{tree}` without the host. Uncommitted paths are outside it.
  `verify`, `finalize`, and `cr-received` use it.
- `## Working tree` - committed, staged, unstaged, and untracked files as they are now,
  without ignored ones and without the host. `cr-request` uses it for an uncommitted
  target, and `verify` uses it only while the work under verification is uncommitted
  itself (its `Verify` line then ends with `working`).

Both recipes are fail-closed. Run each block from the repository root as one script
(`sh`, `bash`, or `zsh`), with `<host-path>` replaced by the host's path relative to the
root; drop that line when there is no host or the host lives outside the repository.
Every step is joined with `&&`, so the first failing step stops the chain; the tree ID
is printed only by the last step, after all others succeeded; the `trap` removes the
temporary index on success and on failure. A run that exits non-zero or prints no ID has
no fingerprint: `verify` returns `BLOCKED (fingerprint failed: <step>)`, naming the step
from the error output, and the `finalize` gate fails. Never fall back to a partial
result or to a plain `git write-tree` on the real index. The chain is used instead of
`set -e`, which is ignored when the call is wrapped in `||` or `&&`.

## Committed tree

```sh
tmp="$(mktemp)" &&
trap 'rm -f "$tmp"' EXIT &&
GIT_INDEX_FILE="$tmp" git read-tree HEAD &&
GIT_INDEX_FILE="$tmp" git rm -q --cached --ignore-unmatch -- '<host-path>' &&
GIT_INDEX_FILE="$tmp" git write-tree
```

Outside a repository or without `HEAD`, `git read-tree HEAD` fails and no ID is printed.
When the host is not in `HEAD`, the result equals `git rev-parse 'HEAD^{tree}'`.

## Working tree

The recipe starts from a copy of the real index, so the real index and the staging area
do not change:

```sh
tmp="$(mktemp)" &&
trap 'rm -f "$tmp"' EXIT &&
index="$(git rev-parse --git-path index)" &&
{ if [ -f "$index" ]; then cp "$index" "$tmp"; else rm -f "$tmp"; fi; } &&
GIT_INDEX_FILE="$tmp" git add -A &&
GIT_INDEX_FILE="$tmp" git rm -q --cached --ignore-unmatch -- '<host-path>' &&
GIT_INDEX_FILE="$tmp" git write-tree
```

An unreadable untracked file makes `git add -A` fail, and no ID is printed. Without the
host line and on a clean tree, the result equals `git rev-parse 'HEAD^{tree}'`.

## Validity

- A recorded verdict or review is valid only while the current fingerprint, taken with
  the same recipe, equals the recorded one. For the committed tree, a new commit that
  changes content makes it stale; for the working tree, any edit does, including a
  whitespace fix or a new untracked file.
- A rebase, a merge, or an amend that leaves the content identical keeps the fingerprint;
  one that changes the content needs a new verification.
- Record the full object ID: 40 hex characters in a SHA-1 repository, 64 in a SHA-256
  one. A short prefix is for display only and is rejected as a recorded fingerprint.
