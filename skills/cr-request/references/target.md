# Target Pinning

The target identity makes a review reproducible and lets anyone tell when it is stale.

## Identity record

    Repository root:
    Branch or worktree:
    Boundary: range | commits | file-set | working-tree | base-to-working-tree | document
    Base: <ref as given and resolved SHA>
    Effective base: <merge-base SHA the diff starts from>
    Head: <resolved SHA>
    Tree: <full fingerprint from tree-fingerprint.md>
    Document: <path> sha256 <hash>   (document boundary only)
    Included paths:
    Excluded paths and reason:
    Others' changes in scope (not assessed): <paths and whose, or none>
    Uncommitted state: none | tracked patch hash + untracked file hashes
    Captured at:

`Tree` is filled for every boundary, including a committed range, from
[tree-fingerprint.md](tree-fingerprint.md): `Committed tree` for a committed range or
commits, `Working tree` when the boundary holds uncommitted changes. Both leave out the
record host (the plan or the spec that holds the record). It is what the record's `Review`
line and `cr-received` compare against. Take it before writing anything to the record.

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

Base to working tree: one diff from the merge-base to the files on disk, so committed,
staged, and unstaged changes arrive together, plus the untracked files:

    git merge-base <base> HEAD
    git log --oneline <merge-base>..HEAD
    git diff --no-ext-diff --no-textconv --stat <merge-base>
    git diff --no-ext-diff --no-textconv <merge-base>
    git ls-files --others --exclude-standard

Use it when the task or branch is partly committed; the `Tree` field then names exactly
the state the reviewer saw.

Fingerprint for uncommitted state (`Uncommitted state`):

    git diff --no-ext-diff --no-textconv HEAD -- . ':(exclude)<host-path>' | git hash-object --stdin
    git ls-files --others --exclude-standard -- . ':(exclude)<host-path>' | git hash-object --stdin-paths

`<host-path>` is the record host relative to the root; drop the `-- . ':(exclude)...'`
part when there is no host in the repository. Leaving the host out keeps the record lines
appended after a review from changing the uncommitted state. `cr-received` uses the same
two commands, so the recorded and the current state compare. `--stdin-paths` unquotes the
C-quoted names that `ls-files` prints under `core.quotePath`, so untracked names with
non-ASCII bytes, quotes, tabs, or newlines hash as they are.

## Secret scan before sending

Read the `--stat` output and the untracked list before any diff goes to a reviewer. A
path that looks like it holds secrets (`.env` files, private keys, credential or token
files, cloud config) is excluded with the reason `possible secret`; its content is never
pasted into the brief. Tell the user which paths were excluded.

## Others' changes

Paths inside the boundary that this change did not make - the journal's
`Initial dirty state`, edits from another session, generated files - go into
`Others' changes in scope (not assessed)`. The reviewer may read them for context and
gives them no verdict or finding.

## Document target

For a spec or plan review, the boundary is the file itself:

    shasum -a 256 <path>

(`sha256sum <path>` where `shasum` is missing). Record the path and hash under
`Document`, and still record `Tree`. The reviewer reads the whole file and the
documents it names; locations are `§<heading>`. A document review is stale when the
hash changes.

## Re-review diff

The base of a re-review is the `Tree` of the previous round, taken from its `Review`
line or identity record. Tree IDs are valid diff endpoints:

    git diff --no-ext-diff --no-textconv --stat <previous tree> <current tree>
    git diff --no-ext-diff --no-textconv <previous tree> <current tree>

The current tree is the fresh fingerprint. If the previous tree object is missing,
fall back to the previous `Head` and say so in the brief.

## Prepared target

A caller that cannot grant Git access, such as a CI job with a narrow allowlist, can
capture the target itself: the identity record, the commit log, the diff stat, the full
diff, and base copies of modified, deleted, and type-changed files. Review from those
files, name them in the brief as the target, and tell the reviewer to read them instead of
running Git. Check that the identity names the same head the files came from; a mismatch
is a wrong target. Take `Tree` from the caller's identity. Without it, when Git is
allowed, run the `Committed tree` recipe in [tree-fingerprint.md](tree-fingerprint.md)
with `'<head>'` in place of `HEAD`, so the record host stays out;
`git rev-parse '<head>^{tree}'` gives the same ID only when the host is not committed.
Else write `Tree: unknown - <reason>`.

## Base discovery

When the user names no base, use the `Base` line of the plan's execution record if it is
set (not `unset`; a spec's `## Verification record` has no `Base`); otherwise take the
merge-base with the default branch (`git merge-base origin/HEAD HEAD`, falling back to
`main` or `master`). State the choice in the brief. If the branch has no upstream and no
obvious parent, ask.

## Fail fast

Stop before dispatch when the base does not resolve, the diff is empty, or the boundary
mixes the change with unrelated edits that cannot be labelled. A reviewer cannot repair a
wrong target.

## Stale review

A review is stale when the `Tree` (or the document `sha256`), the base, or the included
paths differ from its identity record. A new HEAD with the same `Tree`, such as an amend
or a rebase that keeps the content, leaves it valid. A stale PASS is not evidence.
