# Plan Review Brief

Use this template for `plan` mode. Replace every placeholder, omit empty sections, and keep
the brief self-contained: the reviewer has no skills and no conversation history.

## Requirement sources

- With a spec: the spec defines required behavior; the plan must implement it.
- Without a spec (explicit request only): the plan's Goal and Global Constraints are the
  requirements, plus any behavioral specs the host names as behavior to preserve.

Pass the plan and spec to the runner as `--plan` and `--spec`: it appends their paths,
content hashes, and current `Status:` lines on every round, so do not compute or copy
them, and never state a document's status from the conversation. Name every file the
reviewer must read first. A Codex reviewer reads the sources itself. A Claude or
Antigravity reviewer cannot read files outside the repository root: the runner embeds a
`--spec` or `--plan` stored there, so embed by hand only a behavioral spec stored there,
under its path. Copy into the brief the repository rules from `AGENTS.md` that bear on the
plan, because a Claude reviewer does not load project instructions. `--mode plan` makes
the runner add the line that limits an Antigravity reviewer to its file read and search
tools.

## Template

    You are an independent reviewer called by another agent. Inspect and report only.
    Do not modify files, create fixes, commit, start other agents or CLIs, or use reviewer
    skills such as cross-cr or cr-request.

    Review mode: plan
    Respond in the language of the user's conversation: <language>.

    Target identity:
    - Repository root: <path>
    - Branch or worktree: <name>
    - HEAD: <sha>
    - Tree: <fingerprint from cr-request tree-fingerprint.md>
    - Working tree: <clean | list of changed paths>
    - Plan: <path> | runner-computed (--plan)
    - Spec: <path> | runner-computed (--spec) | none (requirements: plan Goal and Global Constraints)
    - Behavioral specs to preserve: <paths> | none

    Read the requirement sources first, in this order: <spec>, <behavioral specs>, then
    <plan>. Only then inspect the repository code the plan touches.

    Repository rules:
    <rules copied from AGENTS.md>

    Excluded paths (do not read them): <paths and reason> | none

    Objective: <what the plan must achieve>
    Known review gaps: <gaps> | none

## Verdicts

Plan mode is the `Document kind` of cr-request's `brief.md`: `--mode plan` makes the
runner append its reviewer instructions, `Document kind` included. The three axis verdicts stay, and the brief puts these questions under them:
Intent covers spec and scope compliance, System covers plan soundness, and Craft covers
verification adequacy.

    Intent: PASS | FINDINGS | UNASSESSED
    System: PASS | FINDINGS | UNASSESSED
    Craft:  PASS | FINDINGS | UNASSESSED

- **Spec compliance:** does the plan implement every required behavior and constraint,
  and does any task contradict the spec?
- **Scope compliance:** does the plan stay inside the requested scope, and is every extra
  change justified by a requirement?
- **Plan soundness:** wrong assumptions about the current code, tool versions, or tool
  behavior; missing steps; wrong task order or dependencies; steps that cannot be executed
  as written.
- **Verification adequacy:** does every task have a check that would catch a regression
  of the behavior the spec requires?

## Result format

`--mode plan` makes the runner append the `Result contract` and `Severity` sections of
the installed `cr-request/references/brief.md`; do not copy them. `Location` names a plan or spec section
(`§<heading>`) or a plan task and step, in place of a code line.

Keep its rule that a result with no findings still states target, coverage, and every
verdict.

## Follow-up rounds

A later round of the same plan runs with `--followup <previous-run-dir> --dispositions
<file>` and no `--brief`: the runner reuses the host part of the previous brief and
rehashes the previous round's plan and spec paths, reading their `Status:` lines again,
so the brief needs no edit for new hashes or a changed status. Pass a new `--brief` only
when a fact the host wrote has changed, written from the current files. The dispositions file
lists every previous finding ID with the host's disposition from `cr-received`; the
runner appends it and the previous `review.md` and asks for a status of each previous
finding: `ADDRESSED` or `NOT ADDRESSED`, a partial fix being `NOT ADDRESSED`.
