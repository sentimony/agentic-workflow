# AGENTS.md

- Layout: `plugins/awf/skills/<skill>/` with `SKILL.md`, `LICENSE`, `CHANGELOG.md`, and
  optional `references/`. A new skill goes into the `skills` list of
  `plugins/awf/.claude-plugin/plugin.json`; the Codex manifest reads `./skills/`.
  Marketplaces: `.claude-plugin/marketplace.json` (Claude Code) and
  `.agents/plugins/marketplace.json` (Codex) list the same plugins.
- Frontmatter: `name` equals the directory, plus `description`, `metadata.version`
  (semver), and `license: MIT`. The top `CHANGELOG.md` entry matches the version.
- Versions bump by patch. Plugin `version` in both manifests equals the release tag
  without `v`.
- License is MIT, Ihor Orlovskyi only. Skills are original work.
- Everything in this repository is English. Use the plain hyphen, never typographic
  dashes.
- Work happens on a branch named `YYMMDD-dev-session` after the session date (for
  example `261018-dev-session`), merged into `main` through a squash-merged PR. Do not
  commit to `main` directly.
