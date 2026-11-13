# Whitespace of a working-tree target

Plain `git diff --check` skips untracked files and counts hunks that were already in the
working tree before the change. In a `working` run (SKILL.md step 1) check the target
through a private index instead; the real index and the working files are never touched.
A run in a clean clone of `HEAD` checks committed content and uses `git diff --check
<base> HEAD` directly.

## Recipe

Run from the repository root. `<host>` is the record host relative to the root.

```sh
idx="$(mktemp -d)/index"
git diff --name-only HEAD -- . ':(exclude)<host>'
git ls-files --others --exclude-standard -- . ':(exclude)<host>'
GIT_INDEX_FILE="$idx" git read-tree HEAD
GIT_INDEX_FILE="$idx" git add -A -- . ':(exclude)<host>'
after="$(GIT_INDEX_FILE="$idx" git write-tree)"
git diff --check HEAD "$after" -- . ':(exclude)<dirty path>'
```

The first two commands print the inventory (changed tracked paths, then untracked ones);
list it in the report. Add one `':(exclude)<dirty path>'` to the last command for every path
of the record's `Initial dirty state`: those paths are checked in the next section, never
against `HEAD`, because `HEAD` would put someone else's whitespace on this change. Exit
code 2 from the last command means whitespace findings; 0 means clean.

## Paths that were dirty before the work

A path in the record's `Initial dirty state` carries someone else's hunks. Its own delta is
the diff from the captured original (the bytes taken before the change, with their sha256)
to the current file:

1. Check the sha256 of the captured bytes first. A mismatch makes the path
   `not verified: snapshot hash mismatch`.
2. Start a second private index from `HEAD` (`read-tree HEAD`), put the captured bytes of
   this path into it with `git hash-object -w --stdin` and
   `git update-index --add --cacheinfo <mode>,<blob>,<path>`, take its tree as the before
   tree, and run `git diff --check <before tree> "$after" -- ':(literal)<path>'`, where
   `$after` is the tree of the recipe above. The pathspec keeps every other path, including
   other initially dirty files, out of this comparison.
3. With no captured original the path is `not verified: no before-snapshot`. `HEAD` is never
   assumed to be the "before" of a dirty file.
4. List such paths as others' changes in the report; they get no verdict of their own.

`cr-request` ships the same recipe as a tested helper (`scripts/target_whitespace.py`,
`check_whitespace`); `verify` does not depend on it.
