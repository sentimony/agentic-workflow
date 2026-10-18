# Target Pinning

The target identity makes a review reproducible and lets anyone tell when it is stale.

## Identity record

    Repository root:
    Branch or worktree:
    Boundary: range | commits | file-set | working-tree
    Base: <ref as given and resolved SHA>
    Effective base: <merge-base SHA the diff starts from>
    Head: <resolved SHA>
    Included paths:
    Excluded paths and reason:
    Uncommitted state: none | tracked patch hash + untracked file hashes
    Captured at:

## Read-only commands

Run from the target worktree. `--no-ext-diff --no-textconv` keeps local diff drivers from
rewriting the output.

    git rev-parse --show-toplevel
    git branch --show-current
    git rev-parse HEAD
    git status --porcelain=v1 --untracked-files=all

Committed range against a base. Resolve the merge-base once and use it everywhere, so
the log, the diff, and the identity share one boundary:

    git rev-parse --verify <base>^{commit}
    git merge-base <base> HEAD
    git log --oneline <merge-base>..HEAD
    git diff --no-ext-diff --no-textconv --stat <merge-base> HEAD
    git diff --no-ext-diff --no-textconv <merge-base> HEAD

When the merge-base differs from the resolved base, the base branch moved on; say so in
the brief.

Working tree on top of HEAD:

    git diff --no-ext-diff --no-textconv --cached
    git diff --no-ext-diff --no-textconv
    git ls-files --others --exclude-standard

Plain `git diff` omits untracked files: list them and give the reviewer their full
content.

Fingerprint for uncommitted state:

    git diff --no-ext-diff --no-textconv HEAD | git hash-object --stdin
    git hash-object <each included untracked file>

## Prepared target

A caller that cannot grant Git access, such as a CI job with a narrow allowlist, can
capture the target itself: the identity record, the commit log, the diff stat, the full
diff, and base copies of modified, deleted, and type-changed files. Review from those
files, name them in the brief as the target, and tell the reviewer to read them instead of
running Git. Check that the identity names the same head the files came from; a mismatch
is a wrong target.

## Base discovery

When the user names no base, take the merge-base with the default branch
(`git merge-base origin/HEAD HEAD`, falling back to `main` or `master`). State the choice in
the brief. If the branch has no upstream and no obvious parent, ask.

## Fail fast

Stop before dispatch when the base does not resolve, the diff is empty, or the boundary
mixes the change with unrelated edits that cannot be labelled. A reviewer cannot repair a
wrong target.

## Stale review

A review is stale when HEAD, the base, the included paths, or the uncommitted
fingerprint differ from its identity record. A stale PASS is not evidence.
