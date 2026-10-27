# Notes root, setup, note shape, declined notes, and chain size

Contents: which checkout is the root, the one-time setup and its local variant, the note
shape, declined notes, and how to measure the instruction chain they join.

The skill usually runs after the work is already squashed into the base branch, so a
tracked edit would need a branch and a pull request of its own. Recording therefore
writes into a gitignored folder that the next session still loads, and a later triage
moves each note to its real place.

## Where

The root is the main checkout of the repository the work happened in: where this session
edited files and committed, not the working directory the process started in. Take as
`<dir>` the directory of a file the session changed (in a linked worktree, if it still
exists, or in the main checkout itself) and run this with `bash -s -- <dir>`:

```bash
dir=$1
gitdir=$(git -C "$dir" rev-parse --path-format=absolute --git-dir)
common=$(git -C "$dir" rev-parse --path-format=absolute --git-common-dir)
if [ "$gitdir" = "$common" ]; then
  root=$(git -C "$dir" rev-parse --show-toplevel)
else
  first=$(git -C "$dir" worktree list --porcelain | sed -n '1s/^worktree //p')
  [ -n "$first" ] && root=$(git -C "$first" rev-parse --show-toplevel 2>/dev/null)
fi
echo "${root:-no main checkout}"
```

A main checkout prints itself, and a linked worktree prints its main checkout (the work
tree of the first `git worktree list` entry), also for a submodule. A linked worktree of a
bare repository or of a clone with a separate Git directory prints `no main checkout`:
then use the clone named in the brief, or else the worktree itself, and say in the report
that notes in a worktree are lost when it is removed. When the worktree was already
removed, use the clone named in the brief or the one the worktree path was created from,
and say so. When the session changed no files, use the repository of the working
directory. Outside a Git repository, use the working directory and skip the ignore step,
saying so in the report.

When the work spanned several repositories, the root is the one holding most of it. A
note about another of them goes into that repository's `docs/session-learnings/AGENTS.md`
only when that folder already exists and is ignored there (`git -C <other> check-ignore -q
docs/session-learnings/AGENTS.md` succeeds); otherwise it goes into the root's notes with
`Target` naming the other repository.

```text
<root>/.gitignore                         docs/session-learnings/
<local exclude file>                      docs/session-learnings/   (instead of .gitignore,
                                          in a checkout with someone else's work; path:
                                          git -C <root> rev-parse --git-path info/exclude)
<root>/docs/session-learnings/CLAUDE.md   @AGENTS.md
<root>/docs/session-learnings/AGENTS.md   the notes
<root>/docs/session-learnings/declined.md notes triage declined, never imported
<root>/CLAUDE.md                          @docs/session-learnings/CLAUDE.md   (Claude Code)
<root>/AGENTS.md                          pointer line   (Codex, Antigravity, or any host
                                                         when CLAUDE.md is only @AGENTS.md)
```

## Setup, each step only when missing

Write every line below with the file edit or write tool, never a shell heredoc or
`echo >>`. First decide whether the root checkout holds someone else's work:

```bash
git -C <root> status --porcelain --untracked-files=no
git -C <root> branch --show-current
git -C <root> symbolic-ref --short refs/remotes/origin/HEAD
```

The checkout is someone else's when the first command lists changes this session did not
make, or the current branch is neither the default branch (the third command without
`origin/`; when it fails, `main`, or `master` when there is no `main`) nor one this
session worked on. A detached HEAD (the second command prints nothing) or a merge, rebase,
or cherry-pick in progress counts too, unless this session caused it. Then use the local
variant below instead of steps 1 and 4.

1. `.gitignore`: when `git -C <root> check-ignore -q docs/session-learnings/AGENTS.md`
   fails, append the line `docs/session-learnings/` to the root `.gitignore` (create it
   when missing). When the folder is already tracked, do not ignore it: write the notes
   and report that they are tracked.
2. `docs/session-learnings/CLAUDE.md`: exactly one line, `@AGENTS.md`. Claude Code resolves
   an import relative to the file that holds it, so this loads the notes beside it, not
   the root `AGENTS.md`. In a fresh clone the folder is absent, and the root import of a
   missing file is skipped without an error.
3. `docs/session-learnings/AGENTS.md`: start it with this header, in the language of the
   root instruction file; the notes below it use the same language:

   ```markdown
   # Session learnings

   Notes recorded by session-learnings, not yet moved to their targets. They apply as
   written until a triage moves, rewrites, or drops them. Gitignored: local to this
   checkout.
   ```

4. Root pointer:
   - When the root `CLAUDE.md` holds only `@AGENTS.md`, leave it untouched and add the
     bullet below to the root `AGENTS.md`, whatever the host. Claude Code imports the notes
     through that chain, and Codex reads the bullet as a pointer.
   - Otherwise, by the host the session runs on: Claude Code adds the line
     `@docs/session-learnings/CLAUDE.md` at the end of the root `CLAUDE.md`; Codex or
     Antigravity adds the bullet below at the end of the root `AGENTS.md`.

   The bullet, in the language of the root `AGENTS.md`:

   ```markdown
   - Unsorted learnings from earlier sessions, read them before starting work: @docs/session-learnings/AGENTS.md
   ```

   Keep the path bare and last on its line: Claude Code skips an import inside a code span
   or followed by punctuation (a trailing `;` breaks it). Search for the path first, in
   the file this branch edits: a pointer already there, in any wording, is enough. A
   pointer in the other root file does not count.

### Local variant: a checkout that holds someone else's work

No tracked file changes, so nothing lands in the other session's commit. When
`docs/session-learnings/` is already tracked there, write no notes: put them in the
report in full, say they were not written and why, and end with `Learnings: 0 -> none`.

1. Ignore: when `git -C <root> check-ignore -q docs/session-learnings/AGENTS.md` fails,
   append the line `docs/session-learnings/` to the local exclude file, the path that
   `git -C <root> rev-parse --path-format=absolute --git-path info/exclude` prints
   (create it when missing). Do this before creating the folder, so it never shows as
   untracked.
2. Steps 2 and 3 as above.
3. No root pointer and no new root file. When no pointer is there yet, the report says
   the notes are not wired: the next session will not load them until a triage or the
   owner of the branch adds the pointer.

Check: `git -C <root> status --porcelain --untracked-files=no` prints the same before and
after, and `git -C <root> status --porcelain -- docs/session-learnings` prints nothing.

## Note shape

One section per run, appended at the end:

```markdown
## <YYYY-MM-DD HH:MM> - <host>

- <rule the next agent should follow>
  - Target: <file and section, global file, other repository path, or check/hook/test>
  - Rung: <structure | type | check | test | prose> - <why not higher>
  - Confidence: <high | medium> - <what it rests on>
  - Quote: "<verbatim excerpt>" - <user | command | tool | agent>
  - Check: <environment check and result, or not checkable - why>
```

Optional lines: `Conflict: <file and rule>` when it contradicts an existing rule,
and `Supersedes: <heading and rule of the earlier note>` when it corrects or sharpens
one. Earlier sections are never edited: a corrected note is appended as a new one, and
triage removes the note it supersedes. The date belongs in the heading only; the rule
line stays free of dates and branch names.

## Declined notes

Triage moves each declined note, whole, into `docs/session-learnings/declined.md` with a
`Declined: <date>` line added, under the heading of the section it came from. Nothing
imports this file, so it does not count toward the chain size and is never read as a
rule; recording and triage search it only to avoid proposing the same note again. New
evidence makes a new note in `AGENTS.md` that names the declined one.

## Chain size

With Claude Code the notes load in every session through the import, so they count
toward its instruction size; with Codex the agent reads them on demand. When the project
limits instruction size (a check script or a documented limit), run its check after
appending and report the number; over the limit, recommend a triage instead of trimming
the notes yourself.

In triage, an edit to a file changes every chain that passes through it: the file plus
each nested instruction file below it. Measure the heaviest of those chains before and
after the edit. Prefer the project's own check script; otherwise, for `AGENTS.md` chains,
run this from the repository root with `bash` (zsh does not split an unquoted file list,
and `cat $files | wc -c` then prints 0). It lists tracked, untracked, and gitignored
files on purpose, so the ignored notes count; a nested repository shows as one directory
entry and is not entered. When the root `CLAUDE.md` or `AGENTS.md` links the notes, it
adds them to every chain, since Claude Code imports them through the root:

```bash
bash -s -- <target> <<'EOF'
target=$1
dir=$(dirname "$target")
max=0
heaviest=
for leaf in $( { echo "$target"; git ls-files -c -o -- "$dir" | grep -E '(^|/)AGENTS\.md$'; } | sort -u); do
  files=AGENTS.md
  path=
  for part in $(dirname "$leaf" | tr / ' '); do
    [ "$part" = . ] && continue
    path=${path:+$path/}$part
    [ -f "$path/AGENTS.md" ] && files="$files $path/AGENTS.md"
  done
  notes=docs/session-learnings/AGENTS.md
  case " $files " in
    *" $notes "*) ;;
    *) [ -f "$notes" ] && grep -qs '@docs/session-learnings/' AGENTS.md CLAUDE.md &&
         files="$files $notes" ;;
  esac
  size=$(( $(cat $files | wc -c) ))
  [ "$size" -gt "$max" ] && max=$size heaviest=$leaf
done
echo "$max $heaviest"
EOF
```

It prints the size in bytes and the deepest file of the heaviest chain. Show both the
before and after numbers in the approval item.
