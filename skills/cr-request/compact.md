# Compact Result

Show verdicts, severity counts, readiness, and the next step; keep the complete
evidence available on demand. Follow caller-specified output requirements while
preserving the full result.

## Default presentation

After the trusted host archives the completed review using
[review-actions.md](review-actions.md), or the caller's specified persistence destination,
show the verdicts and severity counts in a one-row table and a `Readiness` line, then
identify the full review destination and show the local next step. Link the saved review
when the destination supports a link; otherwise identify the caller-provided destination
without inventing one. Keep full findings, target identity, evidence, set-aside items,
and gaps in the archived report. A missing or failed archive makes
the handoff `INCOMPLETE`, with the failed operation and recovery path visible.

For multiple reviewers, show one row per reviewer, with reviewer/model, effort, cost or
`unknown`, its own Intent/System/Craft verdicts and Critical/Important/Minor counts,
and a link to its full result. Preserve original IDs and provenance; differing verdicts
never collapse to an unconditional PASS. Follow those rows with readiness and the
local next step. Each reviewer retains its complete report and identity in the stable
archive; a temporary runner path alone is incomplete.
