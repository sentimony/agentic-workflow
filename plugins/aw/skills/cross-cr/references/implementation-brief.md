# Implementation Review Brief

Use this template for `implementation` mode. Replace every placeholder, omit empty
sections, and keep the brief self-contained: the reviewer has no skills and no
conversation history. `cr-request` stays the source of the review methodology and the
finding contract; this template only fixes the shape of the brief.

## Requirement sources

The spec defines required behavior, and the plan defines the agreed tasks and constraints.
Pass both paths to the runner as `--spec` and `--plan`, which appends their content hashes,
and tell the reviewer to read them before any code. For a change made from conversation
requests with no spec or plan, set both to `none` and fill `Requirement sources
(conversation)` with the user's requests and decisions, verbatim or closely; the
fingerprint then needs no document hashes. A
Claude or Antigravity reviewer cannot read files outside the repository root; the runner
embeds the full content of a `--spec` or `--plan` stored there, so embed by hand only other
sources outside the repository. Copy into the brief the repository rules from `AGENTS.md`
that bear on the review.

## Boundary

Pass `--target` to the runner: `working-tree BASE` for `git diff BASE` with untracked
files, `range BASE..HEAD` for committed changes, `working-tree` for changes against `HEAD`,
or `tree HEAD`, and `--exclude <path>` for each untracked file or directory that is not
part of the change. The runner then appends the file list, the fingerprint, and the
exclusions to the brief, so do not repeat them. Fill the boundary fields by hand from
cr-request's `target.md` only for a boundary none of these express.

List hunks inside the boundary that this session did not make (the user's or another
session's uncommitted edits) under `Foreign changes in scope`, by file and line.

For a Claude or Antigravity reviewer, the runner embeds the diff and the content of each
untracked file in scope, because neither may run Git, and with `--mode` adds the line
that limits Antigravity to its file read and search tools. A Codex reviewer runs Git
itself. One brief serves every reviewer of the round.

## Template

    You are an independent reviewer called by another agent. Inspect and report only.
    Do not modify files, create fixes, commit, start other agents or CLIs, or use reviewer
    skills such as cross-cr or cr-request.

    Review mode: implementation
    Respond in the language of the user's conversation: <language>.

    Target identity:
    - Repository root: <path>
    - Branch or worktree: <name>
    - Base: <sha and how it was chosen> | runner-computed (--target)
    - HEAD: <sha> | runner-computed (--target)
    - Tree: <fingerprint from cr-request tree-fingerprint.md>
    - Spec: <path> | runner-computed (--spec) | none
    - Plan: <path> | runner-computed (--plan) | none

    Read the requirement sources first, in this order: <spec>, <plan>. Only then inspect
    the diff and the code it touches.

    Requirement sources (conversation): <the user's requests and decisions, numbered> | none

    Foreign changes in scope (not under review): <file:line - the user's or another
    session's edit> | none
    Do not judge these hunks against the requirements or the boundary; report one only
    when it breaks the reviewed changes.

    Repository rules:
    <rules copied from AGENTS.md>

    Excluded paths (do not read them): <paths and reason> | none

    Host evidence (output the host already produced; do not rerun it to confirm):
    <test, lint, or build output with the command that produced it> | none

    Sandbox note: a read-only Codex sandbox can block mktemp, writes to a temp
    directory, and stdin for diff. When you cannot reproduce a finding by running it,
    mark the finding "not verified by running" and give the reasoning instead.

    Objective: <what the implementation must achieve>
    Known review gaps: <gaps> | none

## Verdicts and result format

`--mode implementation` makes the runner append the `Reviewer instructions`, `Result
contract`, and `Severity` sections of the installed `cr-request/references/brief.md` and
the `Intent`, `System`, and `Craft` sections of its `references/lenses.md`; do not copy
them. Its three axis verdicts apply as written. For a Claude or Antigravity reviewer, its
lines about running Git and tests yield to the embedded material and the sandbox note.

## Follow-up rounds

A later round of the same target runs with `--followup <previous-run-dir>
--dispositions <file>` and no `--brief`: the runner reuses the host part of the previous
brief, its target, mode, and exclusions, and rebuilds the diff, the untracked files, the
fingerprint, and the `--spec` and `--plan` hashes and statuses from the current files.
Pass a new `--brief` only when a fact the host wrote has changed, such as the host
evidence after a fix; write it from the current files, never from the previous
`brief.md`. The
dispositions file lists every finding of the previous round with its ID and the host's
disposition from `cr-received` (accepted and fixed, rejected with reason, deferred, or
escalated, open).
The runner appends the previous `review.md` and that file to the brief and asks the
reviewer for a status of each previous finding: `ADDRESSED` or `NOT ADDRESSED`, a
partial fix being `NOT ADDRESSED`.
