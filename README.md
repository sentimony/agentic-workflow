# Agentic Workflow

Agent skills for Claude Code, Codex, and other AI coding agents, packaged as the `aw`
plugin.

Version: `v0.0.11`

## Plugins

| Plugin | Version | Skills |
| --- | --- | --- |
| [aw](plugins/aw) | 0.0.11 | specify, plan-craft, implement, verify, cr-request, cr-received, cross-cr, finalize, session-learnings |

## Skills

| Skill | Version | Command | Description |
| --- | --- | --- | --- |
| [specify](plugins/aw/skills/specify/SKILL.md) | 0.0.5 | `/specify` | Triage a request into a direct change, a short note, or a full design, and write an approved spec with checkable acceptance criteria. |
| [plan-craft](plugins/aw/skills/plan-craft/SKILL.md) | 0.0.5 | `/plan-craft` | Turn an approved spec into a task plan with exact files, checks, and commits, ending in an execution record the chain fills in. |
| [implement](plugins/aw/skills/implement/SKILL.md) | 0.0.5 | `/implement` | Execute a plan inline or through subagents, task by task, test first, recording base, task state, and rulings in the execution record. |
| [verify](plugins/aw/skills/verify/SKILL.md) | 0.0.5 | `/verify` | Check every completion claim with fresh evidence bound to the exact tree fingerprint and return PASS, FAIL, INCOMPLETE, or BLOCKED. |
| [cr-request](plugins/aw/skills/cr-request/SKILL.md) | 0.0.10 | `/cr-request` | Pin the exact change, state its intent, and dispatch a read-only reviewer that returns Intent, System, and Craft verdicts with evidence-backed findings. |
| [cr-received](plugins/aw/skills/cr-received/SKILL.md) | 0.0.6 | `/cr-received` | Verify each review finding against the current code, decide with evidence, fix only what holds up, and report per finding. |
| [cross-cr](plugins/aw/skills/cross-cr/SKILL.md) | 0.0.2 | `/cross-cr` | Hand a plan or a finished change to other agent CLIs (by default the opposite CLI, more by name) for a read-only review in the cr-request contract, then pass the findings to cr-received. |
| [finalize](plugins/aw/skills/finalize/SKILL.md) | 0.0.5 | `/finalize` | Integrate verified work safely: merge, pull request, squash, keep, discard, or pause, with cleanup behind explicit confirmation. |
| [session-learnings](plugins/aw/skills/session-learnings/SKILL.md) | 0.0.5 | `/session-learnings` | Record reusable learnings from the current session without asking in gitignored project notes, then triage them into the right instruction file after approval. |

## Workflow

The skills form one chain. Each hands the next a file (spec, plan with its execution
record), runs standalone as well, and ends with a `Next step` line; there is no
orchestrator skill.

```text
specify -> plan-craft -> implement -> verify -> cr-request -> cr-received -> verify -> finalize -> session-learnings
```

With `--auto` in the arguments, a skill starts its local next step in the same turn and
passes the flag on. It still stops on decisions that belong to the user (spec approval, an
escalation, the round limit, an outward action) and before the `finalize` choice, so nothing
is pushed, merged, or published without it. Each skill commits its own paths locally at its
checkpoint and never pushes.

`cross-cr` is outside the chain: it runs only on request, next to or in place of the
`cr-request` step, and hands its findings to `cr-received`.

## Install

Since 0.0.9 the plugin installs from [sentimony/marketplace](https://github.com/sentimony/marketplace),
and this repository has no marketplace of its own: uninstall `aw@agentic-workflow`, remove the
`agentic-workflow` marketplace, then add `sentimony/marketplace` and install `aw@sentimony`.

0.0.8 renames the plugin to `aw`: uninstall the old plugin, then install `aw`.

0.0.3 renames `cr-receive` to `cr-received`: remove the old skill or reinstall.

aw replaces these sentimony/skills devflow skills; remove them from a workspace that
installs aw, or they intercept the same requests: `scope-triage`, `plan-crafting`,
`inline-plan-dev`, `subagent-plan-dev`, `verification-gate`, `branch-finish`,
`review-request`, `review-resolution`, and `cross-review`, which `cross-cr` replaces.

Claude Code:

```bash
claude plugin marketplace add sentimony/marketplace
claude plugin install aw@sentimony
```

Codex:

```bash
codex plugin marketplace add sentimony/marketplace
codex plugin add aw@sentimony
```

Any agent through [skills](https://github.com/vercel-labs/skills):

```bash
npx skills add sentimony/agentic-workflow -s specify plan-craft implement verify cr-request cr-received cross-cr finalize session-learnings -a codex claude-code -y
```
