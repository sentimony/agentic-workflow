# Agentic Workflow

Agent skills for Claude Code, Codex, and other AI coding agents, packaged as the `awf`
plugin.

Release: `v0.0.1` (plugin `awf` 0.0.1)

## Skills

| Skill | Version | Command | Description |
| --- | --- | --- | --- |
| [cr-request](plugins/awf/skills/cr-request/SKILL.md) | 0.0.1 | `/awf:cr-request` | Pin the exact change, state its intent, and dispatch a read-only reviewer that returns Intent, System, and Craft verdicts with evidence-backed findings. |

## Install

Claude Code:

```bash
claude plugin marketplace add sentimony/agentic-workflow
claude plugin install awf@agentic-workflow
```

Codex:

```bash
codex plugin marketplace add sentimony/agentic-workflow
codex plugin add awf@agentic-workflow
```

Any agent through [skills](https://github.com/vercel-labs/skills):

```bash
npx skills add sentimony/agentic-workflow -s cr-request -a codex claude-code -y
```

## License

[MIT](LICENSE) - Ihor Orlovskyi.
