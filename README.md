# Agentflow

[![Auto Reviewer](https://github.com/sentimony/agentic-workflow/actions/workflows/auto-reviewer.yaml/badge.svg)](https://github.com/sentimony/agentic-workflow/actions/workflows/auto-reviewer.yaml)

Agent skills for Claude Code, Codex, and other AI coding agents, packaged as the
`agentflow` plugin.

Version: `v0.0.28`

## Plugins

| Plugin | Version | Skills |
| --- | --- | --- |
| [agentflow](.) | 0.0.28 | resolve-issue, resolve-pr, resolve-ci, resume-task, specify, plan-craft, implement, verify, cr-request, cr-received, finalize, session-learnings |

## Skills

| Skill | Version | Command | Description |
| --- | --- | --- | --- |
| [specify](skills/specify/SKILL.md) | 0.0.14 | `/specify` | Triage a request into a direct change, a short note, or a full design, and write an approved spec with checkable acceptance criteria. |
| [plan-craft](skills/plan-craft/SKILL.md) | 0.0.15 | `/plan-craft` | Turn an approved spec into a task plan with exact files, checks, and commits, ending in an execution record the chain fills in. |
| [implement](skills/implement/SKILL.md) | 0.0.14 | `/implement` | Execute a plan with resumable task evidence; after merge, publish authorized completion evidence with readback or retain an explicit local pending record. |
| [verify](skills/verify/SKILL.md) | 0.0.14 | `/verify` | Check completion claims on the pinned tree with isolated mutable dependencies and fresh target evidence; return PASS, FAIL, INCOMPLETE, or BLOCKED. |
| [cr-request](skills/cr-request/SKILL.md) | 0.0.20 | `/cr-request` | Pin the exact change, state its intent, and dispatch a read-only reviewer; preserve the full report, evidence, and reviewer provenance. |
| [cr-received](skills/cr-received/SKILL.md) | 0.0.16 | `/cr-received` | Verify each review finding against the current code, decide with evidence, fix only what holds up, and report per finding. |
| [finalize](skills/finalize/SKILL.md) | 0.0.13 | `/finalize` | Guard local readiness and strict merge eligibility; preserve post-merge evidence, remove proven transferred duplicates, and separately guard branch/workspace disposal. |
| [resolve-issue](skills/resolve-issue/SKILL.md) | 0.0.4 | `/resolve-issue` | Run issue intake through configured delivery with durable recovery and fresh host authority. |
| [resolve-pr](skills/resolve-pr/SKILL.md) | 0.0.1 | `/resolve-pr` | Take over an existing PR and route its review findings, failing checks and verification toward merge readiness. |
| [resolve-ci](skills/resolve-ci/SKILL.md) | 0.0.1 | `/resolve-ci` | Reproduce one CI failure locally, find its cause and verify the fix. |
| [resume-task](skills/resume-task/SKILL.md) | 0.0.1 | `/resume-task` | Restore an interrupted task from its journal and the current tree, then name the stage to continue. |
| [session-learnings](skills/session-learnings/SKILL.md) | 0.0.14 | `/session-learnings` | Record reusable learnings from the current session without asking in gitignored project notes, then triage them into the right instruction file after approval. |

`specify` and `plan-craft` use the separately installed
[`doc-preview`](https://github.com/sentimony/skills/tree/main/skills/doc-preview) skill
for document previews. If it is unavailable, they report that and continue.

## Workflow

`resolve-issue <issue-url|#number> [--auto]` owns issue orchestration. Without auto,
finish a meaningful stage and request its next transition. With auto, pass the flag
to every stage and continue only within current verified project/invocation authority.
Orchestrated stages return evidence to their owner; historical mode grants no later
permission. Critical product decisions and explicit project/session prohibitions remain.

```text
resolve-issue -> intake -> [specify] -> plan-craft -> plan review -> implement
             -> verify -> code review -> cr-received -> verify -> PR/ready/wait/merge
             -> deploy/health or verified nonproduction -> evidence -> cleanup -> learnings
```

Configured resolve-issue runs can complete delivery through the installed G3 host
bridge with current project authority, bound receipts and independent readback. Unknown
project contracts block their actions. Native host and full production acceptance remain
unverified; track the limits in [issue 29](https://github.com/sentimony/agentic-workflow/issues/29),
[issue 30](https://github.com/sentimony/agentic-workflow/issues/30) and
[issue 31](https://github.com/sentimony/agentic-workflow/issues/31). See the
[run contract](skills/resolve-issue/references/run-contract.md). Each stage keeps its
local checkpoint boundary; saved state grants no new permission.

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
   Publication failure remains evidence-pending in a private store under `~/.sentimony`, separate
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

Since `v0.0.24` the three manifests (`.claude-plugin`, `.codex-plugin`, `.antigravity-plugin`)
are back (standard layout). A `git-subdir` marketplace source with `path: "."` installs only
the top-level files in Claude Code 2.1.322, so the marketplace pins the plugin with a `url`
source. On 2026-11-10 this branch installed through a `url` source in temporary configs of
Claude Code 2.1.322 (`claude plugin details` lists 9 skills) and Codex 0.167.0 (9 SKILL.md
files in the installed root). The 2026-11-07 checks (Claude Code 2.1.319, Codex 0.166.0,
Antigravity 1.5.2) cover the previous root-manifest layout.

Version `0.0.15` renames the plugin from `aw` to `agentflow` after the separate
root-layout release. The repository remains `sentimony/agentic-workflow`. Native
installation was checked on 2026-11-07 (see above); upgrade and rollback evidence
remains unverified under the owner-approved release exception:
https://github.com/sentimony/agentic-workflow/issues/29.
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
`plan-crafting`, `plan-execution` (earlier `inline-plan-dev`), `plan-orchestration`
(earlier `subagent-plan-dev`), `verification-gate`, `branch-finish`, `review-request`,
`review-resolution`, and `cross-review`.
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

The caller delegates to
`sentimony/github-workflows/.github/workflows/auto-reviewer-shared.yaml@v0.0.5`
using the `validate` CI job adapter. Publish that tag before merging this consumer.
Later upgrades update the caller and its contract test together; published tags never
move. The preceding review phase reached Ready through `auto-reviewer.yaml@v0.0.3`;
that review checked the proposed diff and does not prove the new engine's runtime.
The shared workflow owns the engine and its tests; local `scripts/test_auto_reviewer.py`
checks the caller contract. Run it with
`python3 -m unittest discover -s scripts -p 'test_auto_reviewer.py'`.

Live reviews require repository secrets `AUTO_REVIEWER_YNGWALD` and
`CLAUDE_CODE_OAUTH_TOKEN`, mapped to callee inputs with the same names.
Use separate token values for each repository.

Repository variables configure the review: `CLAUDE_REVIEW_MODEL` defaults to
`claude-sonnet-5-5`, `CLAUDE_REVIEW_EFFORT` to `medium`, and
`CLAUDE_REVIEW_MAX_ROUNDS` to 10 when empty. Invalid values fail before inference.
`REVIEW_SKILLS_REF` can pin a full SHA instead of the latest released `cr-request`.
One `auto-review-rounds-N` label overrides the configured round limit; malformed or
multiple labels fail validation. An explicit yngwald request or dispatch bypasses the
count while retaining the other guards. The count includes manual reviews.

Inspect the review jobs with:

```bash
gh pr checks <number> --repo sentimony/agentic-workflow
```
