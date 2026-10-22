# Agentic Workflow

Agent skills for Claude Code, Codex, and other AI coding agents, packaged as the `awf`
plugin.

Version: `v0.0.4`

## Plugins

| Plugin | Version | Skills |
| --- | --- | --- |
| [awf](plugins/awf) | 0.0.4 | specify, plan-craft, implement, verify, cr-request, cr-received, finalize, session-learnings |

## Skills

| Skill | Version | Command | Description |
| --- | --- | --- | --- |
| [specify](plugins/awf/skills/specify/SKILL.md) | 0.0.1 | `/awf:specify` | Triage a request into a direct change, a short note, or a full design, and write an approved spec with checkable acceptance criteria. |
| [plan-craft](plugins/awf/skills/plan-craft/SKILL.md) | 0.0.1 | `/awf:plan-craft` | Turn an approved spec into a task plan with exact files, checks, and commits, ending in an execution record the chain fills in. |
| [implement](plugins/awf/skills/implement/SKILL.md) | 0.0.1 | `/awf:implement` | Execute a plan inline or through subagents, task by task, test first, recording base, task state, and rulings in the execution record. |
| [verify](plugins/awf/skills/verify/SKILL.md) | 0.0.1 | `/awf:verify` | Check every completion claim with fresh evidence bound to the exact tree fingerprint and return PASS, FAIL, INCOMPLETE, or BLOCKED. |
| [cr-request](plugins/awf/skills/cr-request/SKILL.md) | 0.0.4 | `/awf:cr-request` | Pin the exact change, state its intent, and dispatch a read-only reviewer that returns Intent, System, and Craft verdicts with evidence-backed findings. |
| [cr-received](plugins/awf/skills/cr-received/SKILL.md) | 0.0.2 | `/awf:cr-received` | Verify each review finding against the current code, decide with evidence, fix only what holds up, and report per finding. |
| [finalize](plugins/awf/skills/finalize/SKILL.md) | 0.0.1 | `/awf:finalize` | Integrate verified work safely: merge, pull request, squash, keep, discard, or pause, with cleanup behind explicit confirmation. |
| [session-learnings](plugins/awf/skills/session-learnings/SKILL.md) | 0.0.2 | `/awf:session-learnings` | Record reusable learnings from the current session in the right agent instruction file, deduplicated and applied only after approval. |

## Workflow

The skills form one chain. Each hands the next a file (spec, plan with its execution
record), runs standalone as well, and ends with a `Next step` line; there is no
orchestrator skill.

```text
specify -> plan-craft -> implement -> verify -> cr-request -> cr-received -> verify -> finalize -> session-learnings
```

## Install

0.0.3 renames `cr-receive` to `cr-received`: remove the old skill or reinstall.

awf replaces these sentimony/skills devflow skills; remove them from a workspace that
installs awf, or they intercept the same requests: `scope-triage`, `plan-crafting`,
`inline-plan-dev`, `subagent-plan-dev`, `verification-gate`, `branch-finish`. Keep
`review-request` and `review-resolution` for now: devflow `cross-review` reads its brief
from the first and hands findings to the second.

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
npx skills add sentimony/agentic-workflow -s specify plan-craft implement verify cr-request cr-received finalize session-learnings -a codex claude-code -y
```
