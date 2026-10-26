# AGENTS.md

## Layout

- `.claude-plugin/marketplace.json` - Claude Code marketplace.
- `.agents/plugins/marketplace.json` - Codex marketplace.
- `plugins/awf/.claude-plugin/plugin.json` - Claude Code manifest; lists skills.
- `plugins/awf/.codex-plugin/plugin.json` - Codex manifest; reads `./skills/`.
- `plugins/awf/skills/<skill>/` - `SKILL.md`, `CHANGELOG.md`, `LICENSE`, `references/`.
- `.github/workflows/ci.yml` - validation; `claude-review.yml` - auto review: gate, review
  (read-only agent writes the body), publish (validates it, posts a PR review as yngwald, sets
  the `Claude review` status). An automatic trigger (green CI, opened, reopened, ready) reviews a
  head when the PR has no yngwald review yet, or when the latest one has Critical or Important
  findings, reviewed another head, and is one of fewer than 3; a request for yngwald or a
  dispatch always reviews.

## Rules

- New skill: add it to `skills` in the Claude Code manifest; frontmatter `name` equals
  the directory.
- Versions: patch bumps; manifest `version` equals the release tag without `v`; the top
  `CHANGELOG.md` entry matches `metadata.version`. README shows the repository
  version, each plugin version, and each skill version.
- After a release tag, bump the `awf` entry `ref` in sentimony/skills
  `.claude-plugin/marketplace.json` with a skills patch release.
- Releases go through the `rc-verifier` and `releaser` roles (contracts and the release
  checklist in the `skills-aiassist` workbench): `rc-verifier` approves the tree, then
  `releaser` commits, squash-merges the PR, and pushes the annotated tag.
- `claude-review.yml` changes in a PR reach `workflow_run` only after merge (it uses the default
  branch copy); `pull_request` runs use the PR branch copy. `.auto-review/` is reserved for the
  review job and must not be tracked.
- `claude-review.yml` keeps one run per head SHA (workflow-level concurrency), so automatic
  runs for one head no longer race, and a late CI run for an older head cannot cancel the review
  of a newer one; the review job's per-PR group lets a newer head's review cancel an older one,
  which publish reports as superseded. A `workflow_dispatch` run and an event-driven run for the
  same head meet only in that job group, so one review cancels the other and the head can end
  with an `error` status and no review: an accepted trade-off, not a defect for review;
  re-requesting yngwald recovers, and the status is advisory.
- The `publish` footer check accepts the signature with the measured duration followed by a
  `Next step` line in its full format, and the pre-0.0.6 order with the signature last. Its
  regexes have no CI test, because the workflow is self-contained; an edit to them is checked
  by hand on sample bodies. This is an accepted trade-off, not a defect for review.
- Renaming a released skill: the new name starts at `0.0.1`, its CHANGELOG names the old one,
  and README Install says to remove the old skill or reinstall.
- Skills form one chain: specify -> plan-craft -> implement -> verify -> cr-request ->
  cr-received -> verify -> finalize -> session-learnings. Each runs standalone: it takes the
  previous skill's file artifact or builds a minimal one, and ends with a `Next step` line;
  no orchestrator skill.
- awf skills replace their sentimony/skills devflow counterparts (scope-triage,
  plan-crafting, inline-plan-dev, subagent-plan-dev, verification-gate, branch-finish,
  review-request, review-resolution): a description opens with `You MUST use this when`,
  as devflow's do, and names the skill it replaces. README Install keeps review-request and
  review-resolution installed while devflow `cross-review` depends on them.
- License: MIT, Ihor Orlovskyi.
- Branches: `YYMMDD-dev-session`, squash-merged into `main` via PR.
- English only, plain hyphen.
