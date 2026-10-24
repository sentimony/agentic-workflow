# Notes folder, setup, note shape, and chain size

Contents: where the notes live, the one-time setup, the note shape, and how to measure
the instruction chain they join.

The skill usually runs after the work is already squashed into the base branch, so a
tracked edit would need a branch and a pull request of its own. Recording therefore
writes into a gitignored folder that the next session still loads, and a later triage
moves each note to its real place.

## Where

The root is the top of the repository the session ran in (`git rev-parse --show-toplevel`
from the session's working directory). Outside a Git repository, use the working
directory and skip the `.gitignore` step, saying so in the report.

```text
<root>/.gitignore                         docs/session-learnings/
<root>/docs/session-learnings/CLAUDE.md   @AGENTS.md
<root>/docs/session-learnings/AGENTS.md   the notes
<root>/CLAUDE.md                          @docs/session-learnings/CLAUDE.md   (Claude Code)
<root>/AGENTS.md                          pointer line   (Codex, Antigravity, or any host
                                                         when CLAUDE.md is only @AGENTS.md)
```

## Setup, each step only when missing

1. `.gitignore`: when `git check-ignore -q docs/session-learnings/AGENTS.md` fails, append
   the line `docs/session-learnings/` to the root `.gitignore` (create it when missing).
   When the folder is already tracked, do not ignore it: write the notes and report that
   they are tracked.
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
`Supersedes: <heading and rule of the earlier note>` when it corrects or sharpens one,
and `Declined: <date>` added by triage. Earlier sections are never edited: a corrected
note is appended as a new one, and triage removes the note it supersedes. The date
belongs in the heading only; the rule line stays free of dates and branch names.

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
