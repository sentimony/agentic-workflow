# AGENTS.md

## Layout

- `.claude-plugin/marketplace.json` - Claude Code marketplace.
- `.agents/plugins/marketplace.json` - Codex marketplace.
- `plugins/awf/.claude-plugin/plugin.json` - Claude Code manifest; lists skills.
- `plugins/awf/.codex-plugin/plugin.json` - Codex manifest; reads `./skills/`.
- `plugins/awf/skills/<skill>/` - `SKILL.md`, `CHANGELOG.md`, `LICENSE`, `references/`.
- `.github/workflows/ci.yml` - validation; `claude-review.yml` - auto review as yngwald.

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
- `claude-review.yml` changes in a PR run only after merge: `workflow_run` uses the default
  branch copy. `.auto-review/` is reserved for the review job and must not be tracked.
- Renaming a released skill: the new name starts at `0.0.1`, its CHANGELOG names the old one,
  and README Install says to remove the old skill or reinstall.
- License: MIT, Ihor Orlovskyi.
- Branches: `YYMMDD-dev-session`, squash-merged into `main` via PR.
- English only, plain hyphen.
