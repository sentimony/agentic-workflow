# Agentic Workflow

Agent skills for Claude Code, Codex, and other AI coding agents, packaged as the `awf`
plugin.

Version: `v0.0.3`

## Plugins

| Plugin | Version | Skills |
| --- | --- | --- |
| [awf](plugins/awf) | 0.0.3 | cr-request, cr-received, session-learnings |

## Skills

| Skill | Version | Command | Description |
| --- | --- | --- | --- |
| [cr-request](plugins/awf/skills/cr-request/SKILL.md) | 0.0.3 | `/awf:cr-request` | Pin the exact change, state its intent, and dispatch a read-only reviewer that returns Intent, System, and Craft verdicts with evidence-backed findings. |
| [cr-received](plugins/awf/skills/cr-received/SKILL.md) | 0.0.1 | `/awf:cr-received` | Verify each review finding against the current code, decide with evidence, fix only what holds up, and report per finding. |
| [session-learnings](plugins/awf/skills/session-learnings/SKILL.md) | 0.0.1 | `/awf:session-learnings` | Record reusable learnings from the current session in the right agent instruction file, deduplicated and applied only after approval. |

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
npx skills add sentimony/agentic-workflow -s cr-request cr-received session-learnings -a codex claude-code -y
```
