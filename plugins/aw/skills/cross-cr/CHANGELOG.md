# Changelog

## [0.0.2] - 2026-10-29

- Before round 1 the skill commits this session's own uncommitted spec, plan, or code
  locally as `Checkpoint before cross-cr R1: <topic>`, through a temporary index when the
  real one holds foreign content, under the user's and project's commit policy; other
  uncommitted paths are listed and left alone. The old ban on any commit made only to fit
  the boundary is gone; foreign changes are still never committed to fit it.
- Only automatic rounds count against the limit (three, or the named rounds); a round
  the user starts past the limit runs once and is recorded as a `Ruling` line, and the
  same cause twice escalates also in user-started rounds. Dispositions can be
  "escalated, open".
- `--auto`: the skill takes it out of the arguments before the runner's `resolve` and
  runs review, `cr-received`, `verify`, and the next round without pauses, stopping on
  user decisions, the Round rule, and before the `finalize` choice.
- The runner reads `~/.gemini/antigravity-cli/settings.json` (through `HOME`) before every
  Antigravity `run` and `resume`: a non-empty `permissions.allow`, or a file it cannot read
  or parse, is exit 2 before any brief is sent, with a message that names the file but not
  its content; a missing file lets the run proceed.
- `Review`, `Finding`, and `Round review <n>` lines go to the record host, the plan or else
  the spec's `## Verification record`, as in `cr-request`, and the round counter is read
  from them. Under `--auto` a re-review comes back to `cross-cr` as its next round, never
  as a same-host `cr-request`.
- A runner test checks that `standard_sections()` leaves out the host-only text of
  cr-request `brief.md` (`Reviewed with`, `CI footer grammar`, `conversation comment`).

## [0.0.1] - 2026-10-27

- New skill, forked from sentimony/skills devflow `cross-review` 1.4.2, which it
  replaces in a workspace that installs aw.
- Reads the reviewer brief, result contract, severity scale, target pinning, and tree
  fingerprint of the installed `cr-request` instead of devflow `review-request`, and
  hands findings to `cr-received` instead of `review-resolution`.
- Verdicts are the three `cr-request` axes, Intent, System, and Craft, in both modes;
  `plan` mode is the `cr-request` document kind.
- Finding IDs are `R<n>-<reviewer>-F<k>`; the target identity carries `Tree`; a
  follow-up round marks each previous finding `ADDRESSED` or `NOT ADDRESSED`.
- Arguments are zero or more groups `<family> [model] [effort]` with `family` one of
  `claude`, `codex`, `gemini` (`claude opus low`, `codex sol low`, `gemini argon low`).
  With no group one reviewer runs, the CLI opposite to the host; each group adds one.
  The runner's `resolve` command parses the groups and expands model shorthands.
- The runner builds the standard part of the brief: with `--mode` the cr-request
  reviewer instructions, result contract, severity, and lenses, plus the Antigravity
  tools line; for a Claude or Antigravity reviewer the diff, the untracked files, and
  requirement documents outside the repository, never env, key, or credential files
  or untracked symlinks, with `--exclude` for unrelated paths and an error instead of
  truncation over 4 MiB; the current `Status:` line of the spec
  and plan.
- A `--followup` round without `--brief` reuses the host part of the previous brief and
  its target, and rebuilds the diff, the untracked files, hashes, and statuses from the
  current files.
- Rounds the user names are authorized: they run without asking, also on an unchanged
  target or past round 3; the next round after them asks.
- An `agy` reviewer that wrote a complete answer and then hangs is stopped after 60
  seconds idle; the runner exits 25 with `review.md` written.
- The run report writes sums as `~$`, as the runner does.
- Appends `Review` and `Finding` lines to the plan's execution record when the plan is
  known, and ends with a `Next step` line.
- Runs only on the user's request: no aw skill calls it automatically.
