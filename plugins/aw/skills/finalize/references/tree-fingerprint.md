# Tree fingerprint

A verdict or a review belongs to the exact content it saw, not to a commit. The
fingerprint is a Git tree ID of the working tree as it is now: committed, staged,
unstaged, and untracked files, without ignored ones and without the plan file that holds
the execution record. The plan is left out because the chain writes its journal lines
there: a fingerprint that included it would go stale with every `Verify`, `Review`, or
`Received` line.

## Recipe

Run from the repository root. The recipe writes to a temporary copy of the index, so the
real index and the staging area do not change:

```sh
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
index="$(git rev-parse --git-path index)"
if [ -f "$index" ]; then cp "$index" "$tmp"; else rm -f "$tmp"; fi
GIT_INDEX_FILE="$tmp" git add -A
GIT_INDEX_FILE="$tmp" git rm -q --cached --ignore-unmatch -- '<plan-path>'
GIT_INDEX_FILE="$tmp" git write-tree
rm -f "$tmp"
```

Replace `<plan-path>` with the plan's path relative to the root; drop that line when there
is no plan or the plan lives outside the repository. Without the line and on a clean tree,
the result equals `git rev-parse 'HEAD^{tree}'`.

## Validity

- A recorded verdict or review is valid only while the current fingerprint equals the
  recorded one. Any edit, including a whitespace fix or a new untracked file, makes it stale.
- A rebase, a merge, or an amend that leaves the content identical keeps the fingerprint;
  one that changes the content needs a new verification.
- Record the full object ID: 40 hex characters in a SHA-1 repository, 64 in a SHA-256 one.
  A short prefix is for display only.
