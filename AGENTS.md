# AGENTS.md

## Layout

- `.claude-plugin/marketplace.json` - Claude Code marketplace.
- `.agents/plugins/marketplace.json` - Codex marketplace.
- `plugins/awf/.claude-plugin/plugin.json` - Claude Code manifest; lists skills.
- `plugins/awf/.codex-plugin/plugin.json` - Codex manifest; reads `./skills/`.
- `plugins/awf/skills/<skill>/` - `SKILL.md`, `CHANGELOG.md`, `LICENSE`, `references/`.

## Rules

- New skill: add it to `skills` in the Claude Code manifest; frontmatter `name` equals
  the directory.
- Versions: patch bumps; manifest `version` equals the release tag without `v`; the top
  `CHANGELOG.md` entry matches `metadata.version`. README shows the release tag
  and each skill version.
- License: MIT, Ihor Orlovskyi.
- Branches: `YYMMDD-dev-session`, squash-merged into `main` via PR.
- English only, plain hyphen.
