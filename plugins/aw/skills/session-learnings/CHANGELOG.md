# Changelog

## [0.0.4] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; the text changes only that name.

## [0.0.3] - 2026-10-27

- Description drops how the notes are linked and what each note carries; the body still
  covers both.
- The notes root is the main checkout of the repository the work happened in (the first
  entry of `git worktree list`, or the clone from the brief), not the working directory of
  the process, so a subagent that worked in a worktree of another repository writes there.
  A note about a further repository goes into its notes when that folder already exists
  and is ignored there.
- In a checkout with someone else's uncommitted changes, on someone else's branch, on a
  detached HEAD, or mid-operation, setup changes no tracked file: the folder is ignored
  through the local exclude file (`--git-path info/exclude`), no pointer is added, and the
  report says the notes are not wired.
- The report names the chosen root, how the folder is ignored, and whether the notes are
  wired, and its last line before `Next step` is `Learnings: <n> -> <file>`.
- Notes and setup lines are written with the file edit or write tool, never a shell
  heredoc or `echo >>`.
- After a context compaction, quotes come from the session transcript (Claude Code JSONL
  or Codex thread), read with a script; the compaction summary is quoted only as a last
  resort, as `agent` with at most `medium` confidence.
- A recipe note is run in the form it is written before it is recorded, and again in
  triage once the user approves it; its flags are copied verbatim.
- Triage moves declined notes into `docs/session-learnings/declined.md`, which nothing
  imports, instead of leaving them in the loaded notes file.

## [0.0.2] - 2026-10-22

- Description opens with "You MUST use this when", names the end of the awf chain as a
  trigger, and separates the skill from `maintaining-agent-context`.
- Recording asks no questions: each learning goes, with its quote and intended target,
  into the gitignored `docs/session-learnings/AGENTS.md` of the session's repository.
  A one-time setup adds the `.gitignore` line, `docs/session-learnings/CLAUDE.md` with
  `@AGENTS.md`, and a link in the root `CLAUDE.md` (Claude Code) or `AGENTS.md` (Codex,
  Antigravity, or any host when the root `CLAUDE.md` only imports `AGENTS.md`).
- New triage mode (`triage` argument or a request to sort the notes): moves each note to
  its target after approval, measures the heaviest instruction chain through the target
  before and after the edit, and prunes applied notes.
- Every candidate carries a verbatim quote from the session and a confidence level;
  only text a person typed counts as a user correction, never hook output, system
  reminders, tool results, or a parent agent's prompt to a subagent.
- New step: each candidate is checked against the environment (remote, path, script,
  flag) with read-only means before it is drafted.
- New enforcement ladder: structure, type, check or lint, test, prose; mechanical rules
  are proposed as a check or a hook, and a learning that recurs moves up a rung.
- The target file is re-read right before each edit, and edits land on top of others'
  changes.
- Earlier notes are never rewritten: a corrected note is appended with `Supersedes:`, and
  triage removes the note it replaces.
- A repeat run in the same session collects only events after the previous report;
  deduplication also covers skill improvement requests the session already wrote.
- Rule form follows the failure: prohibition, recipe, template slot, or condition; rules,
  not stories of the session.
- More placement surfaces: files read during review, a glossary, a decision record for
  hard-to-reverse trade-offs, and a "why" comment beside the code.
- The result ends with `Next step: none - chain complete`.
- New `references/` (candidate records, ladder and placement, notes folder and chain
  size) and a `## References` section.

## [0.0.1] - 2026-10-18

- Initial release: candidates from actual session events, a four-part filter, placement
  by the narrowest scope including the user's global files and other repositories,
  deduplication against instructions, code, and configuration, drafts matched to the
  target file and its size limit, approval before any edit, and commits only on request.
