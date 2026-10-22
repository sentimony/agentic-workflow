# Changelog

## [0.0.2] - 2026-10-22

- Description opens with "You MUST use this when", names the end of the awf chain as a
  trigger, and separates the skill from `maintaining-agent-context`.
- Every candidate carries a verbatim quote from the session and a confidence level;
  only text a person typed counts as a user correction, never hook output, system
  reminders, tool results, or a parent agent's prompt to a subagent.
- New step: each candidate is checked against the environment (remote, path, script,
  flag) with read-only means before it is drafted.
- New enforcement ladder: structure, type, check or lint, test, prose; mechanical rules
  are proposed as a check or a hook, and a learning that recurs moves up a rung.
- The target file is re-read right before each edit, and edits land on top of others'
  changes.
- A repeat run in the same session collects only events after the previous report;
  deduplication also covers skill improvement requests the session already wrote.
- Rule form follows the failure: prohibition, recipe, template slot, or condition; rules,
  not stories of the session.
- More placement surfaces: files read during review, a glossary, a decision record for
  hard-to-reverse trade-offs, and a "why" comment beside the code.
- The result ends with `Next step: none - chain complete`.
- New `references/` (candidate records, ladder and placement) and a `## References`
  section.

## [0.0.1] - 2026-10-18

- Initial release: candidates from actual session events, a four-part filter, placement
  by the narrowest scope including the user's global files and other repositories,
  deduplication against instructions, code, and configuration, drafts matched to the
  target file and its size limit, approval before any edit, and commits only on request.
