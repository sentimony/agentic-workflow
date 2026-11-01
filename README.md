# Agentflow

Agent skills for Claude Code, Codex, and other AI coding agents, packaged as the
`agentflow` plugin.

Version: `v0.0.17`

## Plugins

| Plugin | Version | Skills |
| --- | --- | --- |
| [agentflow](.) | 0.0.17 | specify, plan-craft, implement, verify, cr-request, cr-received, finalize, session-learnings |

## Skills

| Skill | Version | Command | Description |
| --- | --- | --- | --- |
| [specify](skills/specify/SKILL.md) | 0.0.6 | `/specify` | Triage a request into a direct change, a short note, or a full design, and write an approved spec with checkable acceptance criteria. |
| [plan-craft](skills/plan-craft/SKILL.md) | 0.0.7 | `/plan-craft` | Turn an approved spec into a task plan with exact files, checks, and commits, ending in an execution record the chain fills in. |
| [implement](skills/implement/SKILL.md) | 0.0.7 | `/implement` | Execute a plan with resumable task evidence; after merge, publish authorized completion evidence with readback or retain an explicit local pending record. |
| [verify](skills/verify/SKILL.md) | 0.0.8 | `/verify` | Check completion claims on the pinned tree with isolated mutable dependencies and fresh target evidence; return PASS, FAIL, INCOMPLETE, or BLOCKED. |
| [cr-request](skills/cr-request/SKILL.md) | 0.0.12 | `/cr-request` | Pin the exact change, state its intent, and dispatch a read-only reviewer; show compact verdicts with a persistent full report and structured action identities. |
| [cr-received](skills/cr-received/SKILL.md) | 0.0.8 | `/cr-received` | Verify each review finding against the current code, decide with evidence, fix only what holds up, and report per finding. |
| [finalize](skills/finalize/SKILL.md) | 0.0.8 | `/finalize` | Guard local readiness and strict merge eligibility; preserve post-merge evidence, remove proven transferred duplicates, and separately guard branch/workspace disposal. |
| [session-learnings](skills/session-learnings/SKILL.md) | 0.0.6 | `/session-learnings` | Record reusable learnings from the current session without asking in gitignored project notes, then triage them into the right instruction file after approval. |

## Workflow

The skills form one chain. Each hands the next a file (spec, plan with its execution
record), runs standalone as well, and ends with a `Next step` line; there is no
orchestrator skill.

```text
specify -> plan-craft -> implement -> [verify -> cr-request -> cr-received]* -> verify -> finalize -> session-learnings
```

The bracketed loop repeats once per review round. `finalize` always follows a fresh `verify`
on the final tree.

With `--auto` in the arguments, a skill starts its local next step in the same turn and
passes the flag on. It still stops on decisions that belong to the user (spec approval, an
escalation, the round limit, an outward action) and before the `finalize` choice, so nothing
is pushed, merged, or published without it; after a successful `merge`, `squash`, `pr`,
`keep`, or `discard`, `finalize` starts `session-learnings`. Each skill commits its own
paths locally at its checkpoint and never pushes.

Already authorized defer issue/reply actions and the bounded REJECT reply in
`cr-received` may proceed under `--auto`; other outward gates remain in force.

Standalone `cross-agent` is a separate experimental plugin, released as `0.0.1`.
The installed [workflow owner adapter](skills/cr-request/references/cross-agent-adapter.md)
binds explicit review/intake delegation; ordinary consultations remain generic.
Native published-pair acceptance remains unverified:
https://github.com/sentimony/agentic-workflow/issues/31.

## Delivery reliability

Version `0.0.16` adds local delivery contracts after the separate root-layout and
agentflow identity releases. Live acceptance remains unverified under the owner-approved
release exception: https://github.com/sentimony/agentic-workflow/issues/30.

1. Verification uses private mutable dependency paths and checks current committed
   targets. Hostless ready PRs require fresh project checks in the handoff and body.
2. Ready requires fresh local verification and current head/base observations; remote
   jobs may start after ready. Merge waits for every applicable check, keeps unknown
   policy unresolved until its gate is satisfied, and receives the verified full SHA.
3. Post-merge completion belongs in an authorized own PR comment with readback.
   Publication failure remains evidence-pending in an ignored local store, separate
   from the result of the external task; tracked plan/spec files stay unchanged.
4. Removing transferred duplicate hunks requires captured ownership and canonical
   evidence. Separate branch/workspace disposal requires current authority, integration
   or retention and data guards, and a trusted post-merge task inventory. Explicitly
   having no tasks makes evidence not applicable for committed-only/local merges;
   no patch, PR or deployment is fabricated. Unknown inventory or actual pending
   evidence blocks disposal. Foreign staging and untracked/ignored data are protected.
5. Whole-clone removal is blocked when common Git storage lies inside the removal
   root. Linked-worktree removal needs proof that the common Git data and retaining
   refs survive outside that root; the helper supplies no external-copy framework.

The Python suites exercise local contracts, real scratch Git operations and injected
forge fixtures. Production adapters, real forge policy/write/readback, deployments,
installation migration and native agent evals remain unverified. Environment isolation
is cooperative; the helpers provide no OS containment. Local fixture results do not
establish live acceptance or authorize outward actions.


## Install

Version `0.0.15` renames the plugin from `aw` to `agentflow` after the separate
root-layout release. The repository remains `sentimony/agentic-workflow`. Native
installation, upgrade and rollback evidence remains unverified under the owner-approved
release exception: https://github.com/sentimony/agentic-workflow/issues/29.
Use the commands below after the matching marketplace update.

### Migrate an existing aw installation

1. Record the existing host version, pinned source tag, plugin name/path and local
   settings before changing the installation. Test the transition in a scratch
   configuration first; keep credentials in their existing approved stores.
2. Use the host's supported uninstall operation to remove `aw`, then install
   `agentflow` from the updated marketplace. Installing both identities together is a
   conflict because they expose the same skill names; no alias plugin is provided.
3. Check the available commands and restore only compatible settings after the new
   installation is verified. Local symlinks require an explicit target/owner check;
   this package does not remove real installations or rewrite user configurations.
4. For rollback, remove `agentflow` with the host's supported operation and restore the
   recorded immutable tag with its matching old `aw` name/path and saved settings.
   Update marketplace metadata through a normal follow-up commit; keep existing tags.

### Fresh installation

Since 0.0.9 the plugin installs from
[sentimony/marketplace](https://github.com/sentimony/marketplace), and this repository
has no marketplace of its own: uninstall `aw@agentic-workflow`, remove the
`agentic-workflow` marketplace, then add `sentimony/marketplace` and install the current
plugin as shown below.

0.0.8 renames the plugin to `aw`: uninstall the old plugin, then install `aw`.

0.0.3 renames `cr-receive` to `cr-received`: remove the old skill or reinstall.

agentflow replaces these sentimony/skills devflow skills; remove them from a workspace
that installs agentflow, or they intercept the same requests: `scope-triage`,
`plan-crafting`, `inline-plan-dev`, `subagent-plan-dev`, `verification-gate`,
`branch-finish`, `review-request`, `review-resolution`, and `cross-review`.
Install standalone `cross-agent` separately for cross-model delegation.

Claude Code:

```bash
claude plugin marketplace add sentimony/marketplace
claude plugin install agentflow@sentimony
```

Codex:

```bash
codex plugin marketplace add sentimony/marketplace
codex plugin add agentflow@sentimony
```

Any agent through [skills](https://github.com/vercel-labs/skills):

```bash
npx skills add sentimony/agentic-workflow -s specify plan-craft implement verify cr-request cr-received finalize session-learnings -a codex claude-code -y
```

## Review operations

Automatic yngwald reviews use Sonnet 5.5 medium and a default limit of five reviews.
One `auto-review-rounds-N` label overrides the limit for that PR. Inspect its review
jobs with:

```bash
gh pr checks <number> --repo sentimony/agentic-workflow
```
