# Cross CR workflow details

Read each section before its corresponding numbered step in
[SKILL.md](../SKILL.md#workflow). The entrypoint retains routing and the Security Model.
The workflow below preserves the existing contract, including all conditions, exceptions,
commands, exit codes, archive rules, result forms, and follow-up rules.

## Workflow

### 1. Confirm the dependency and the target

Locate the installed `cr-request` skill next to this one (the same skills directory
that contains this `SKILL.md`). Both modes need its `references/brief.md` and
`references/tree-fingerprint.md`; `implementation` also needs `references/target.md` and
`references/lenses.md`. If they are missing, report `dependency unavailable: cr-request`
and stop.

Before round 1, commit this session's own uncommitted spec, plan, or code as
`Checkpoint before cross-cr R1: <topic>`. Own paths are the spec, the plan, and the
paths of the tasks and rounds in its record, the files this session created or changed;
list every other uncommitted path in the report and leave it uncommitted. Without a
commit, the boundary stays on the working tree (step 3). With one, and no explicit or
plan-start base, record `HEAD` from before it and review against that SHA
(`--target working-tree <SHA>`) in this and later rounds, so the committed change stays
in the diff.

Checkpoint commit: commit locally, never push, with only this session's own paths (files it
created or changed for this spec, plan, task, or round). Other uncommitted changes, and
content someone else already staged, stay exactly as they were: commit through a temporary
index when the real index holds foreign content. Before the first commit of a chain, read the
commit policy in the user's and project's instruction files in force; the stricter one wins.
A policy that asks first gets one question for the whole chain (this stops `--auto`); a
policy that forbids commits means no commit, and the report says so.

Capture the target identity: repository root, branch or worktree, `HEAD`, and working-tree
state. For `plan`, name the plan and spec paths; pass them to the runner as `--plan` and
`--spec` and it hashes them. For `implementation`, establish the boundary in step 3.
Before changing to the target directory, capture the session repository's absolute root
as `session_root`. Pass that host-owned value explicitly when archiving; a target in
another repository never changes it. Use the shared resolver and archive contract in
cr-request's `references/review-actions.md`.

Before a round on a target whose previous round passed with no findings, check whether
anything changed since: base, `HEAD`, the working tree, the plan, and the spec. A runner
`--followup` round prints `target and documents unchanged since round N` on stderr when
they match. When nothing changed, do not rerun as is: say so in one line and offer what
can add information (a higher effort or another model, another reviewer group, or a
brief narrowed to a named risk or file). Run only after the user
chooses; a confirmed repeat runs unchanged.

### 2. Select material with secret hygiene

Apply `secret-hygiene` before writing any part of the brief, because the brief and the
reviewer's reads leave this machine for another vendor's API.

1. Name selected and excluded paths; never print file contents or values while selecting.
2. Exclude `.env`, `.env.*`, credential files, private keys, unrelated untracked files,
  and all `.cross-review/` archives, including `local/` and peer reviewer outputs.
  Keep gitignore rules. With `--target working-tree`, the runner takes every untracked file
  that gitignore keeps, except its standard exclusions (env files, local overrides, key
  and credential names such as `*.pem`, `id_rsa*`, `.npmrc`) and untracked symlinks, and
  embeds it for a Claude or Antigravity reviewer: pass `--exclude` for every other
  untracked file that is not part of the change.
3. Do not follow a symlink that resolves outside the repository.
4. Check the selected diff for secret-shaped values by pattern, reporting only path and line.
5. If material that may be sensitive is needed for a verdict, stop and agree the boundary
  with the user. If no acceptable boundary exists, do not send the repository.
6. Separate foreign changes. Compare the boundary's diff with the edits this session made.
  A hunk the session did not make (the user's own edit or another session's) stays valid
  and is not under review: list it by file and line in the brief's `Foreign changes in
  scope` field. A file holding both kinds stays in scope. When the session's edits cannot
  be told apart, name that in `Known review gaps`.

Every exclusion is a coverage gap, and the brief names it. The brief also forbids the
reviewer from reading the excluded paths. The read-only policy prevents edits only: a
Claude or Antigravity reviewer can read any file inside the repository, and a Codex
reviewer can read any file its read-only sandbox allows.

### 3. Fix the implementation boundary

The diff runs from a trusted base to the current working tree:

1. base: an explicit base SHA or the verified plan-start SHA recorded by the orchestrator;
2. a merge base only when the active workflow names the intended target branch and the rule
  for computing it;
3. with no trustworthy base, ask in an interactive session, or return a gap and the caller's
  fallback in an automatic one. Never assume `main`.

The material is `git diff BASE` (committed, staged, and unstaged tracked changes) plus the
complete content of each selected untracked file, with exclusions named. Follow
cr-request's `target.md` for the inspection commands, the secret scan, and stale
detection. Pass the boundary to the runner, which then computes the file list, the
standard exclusions, and the fingerprint and appends them to the brief:

1. `--target working-tree BASE` - `git diff BASE` with selected untracked files; the
  default for the final review, including when the commit policy left the plan, spec, or
  fixes uncommitted, and for a later round with uncommitted fixes;
2. `--target range BASE..HEAD` - committed changes only;
3. `--target working-tree` - uncommitted changes against `HEAD`, the usual boundary of a
  change made from conversation requests while nothing of it is committed (after the
  checkpoint commit of step 1, `--target working-tree <SHA>` with the `HEAD` from before
  it);
4. `--target tree HEAD` - the whole tree.

`--exclude <path>` (repeatable, a file or a directory, relative to the repository root or
absolute inside it) drops a path from the material, for example the user's untracked file
that is not part of the change; the brief lists it as excluded, and one that matches no
path of the target is exit `2`. Only the checkpoint commit of step 1 commits anything:
foreign changes are excluded or listed, never committed to fit a boundary.

### 4. Record the target fingerprint

Record base and head, hashes of the plan and spec, the identity of the selected tracked
diff, and the hash of each selected untracked file (commands in cr-request's `target.md`).
Requirements can change without a commit, so hash the plan and spec files themselves:
`--plan` and `--spec` make the runner do it on every round, and a `--followup` round
rehashes the previous round's paths. Also take the `Tree` fingerprint with cr-request's
`tree-fingerprint.md`: `Committed tree` for a committed range, `Working tree` when the
boundary holds uncommitted changes; both leave the record host out. Write it into the
target identity: `cr-received` binds its decisions to it. The brief carries this
fingerprint. Recheck it before the handoff; a material change makes the result stale.

### 5. Build the brief

The brief is one UTF-8 file and the reviewer needs nothing else. A Claude reviewer runs in
safe mode without skills or project customizations, and a Codex reviewer gets no skill
instructions from this host. The host writes only the task-specific part, one brief for
every reviewer of the round:

1. role: independent reviewer called by another agent; inspect and report only; do not edit
  files, commit, start other agents or CLIs, or use reviewer skills such as `cross-cr`
  and `cr-request`;
2. `Review mode: plan` or `Review mode: implementation`;
3. target identity and the `Tree` fingerprint from step 4;
4. requirement sources with paths and an instruction to read them first. Without a spec
  and plan, the sources are the user's requests and decisions from the conversation,
  copied verbatim or closely, with `Spec` and `Plan` set to `none`;
5. foreign changes in scope from step 2, which the reviewer does not judge against the
  requirements;
6. repository rules from `AGENTS.md` that bear on the review;
7. the excluded paths and the instruction not to read them;
8. `Respond in the language of the user's conversation: <language>.`;
9. finding IDs `R<n>-<reviewer>-F<k>` (`<reviewer>` is `codex`, `claude-code`, or
  `antigravity`); take the round `n` from the record host's record as `cr-request`
  does.

The runner appends the rest, so never copy or embed it by hand:

1. `--mode plan|implementation`: the `Reviewer instructions`, `Result contract`, and
  `Severity` sections of the installed cr-request `brief.md`, the `Intent`, `System`, and
  `Craft` lenses of its `lenses.md` in `implementation` mode, and for Antigravity the line
  that limits it to file read and search tools (a denied call ends the turn with no
  answer, exit `23`). Always pass `--mode`; the `run.log` header records it.
2. `--target range|working-tree` for a Claude or Antigravity reviewer, which may not run
  Git: the diff of the files in scope and the full content of each untracked file in
  scope, standard exclusions and `--exclude` paths left out. This diff and these files
  over 4 MiB fail with exit `2` instead of being truncated: narrow the agreed boundary or
  report failure.
3. `--plan` and `--spec`: their paths, hashes, and current `Status:` lines, and for a
  Claude or Antigravity reviewer the full content of each one stored outside the
  repository root, because its file reads cannot leave the repository.

Mode-specific parts:

1. `plan`: follow [plan-brief.md](plan-brief.md).
2. `implementation`: follow [implementation-brief.md](implementation-brief.md),
  including the host's own test output and the sandbox note.

### 6. Run the reviewer

Write the brief to a private temporary file, then call the runner by the absolute path of
`scripts/cross_review.py` inside this installed skill directory, once per reviewer that
`resolve` printed. With several reviewers, start all runners at the same time, each in the
background with the same brief file, and wait for every exit before step 7.

```text
python3 <skill-dir>/scripts/cross_review.py run --agent claude|codex|gemini \
  --repo <repo-root> --brief <brief-file> --mode plan|implementation \
  [--model <id>] [--effort <level>] [--target <kind> [<rev>]] [--exclude <path>]... \
  [--plan <path>] [--spec <path>] \
  [--followup <previous-run-dir> --dispositions <file>]
```

The reviewer gets an environment allowlist, not the host environment; add a missing
authentication variable with `--pass-env NAME`. A review can take ten minutes or more and
the runner sets no timeout on a reviewer that is still working: start it with the host's
background mechanism and wait for the actual exit. A Codex host requests escalation for
this one command up front. A background job that has not exited has produced no review.
The runner prints the run directory and a last `usage:` line with the reviewer's model,
effort, skills, tokens, and approximate cost.

Exit `0`: read `review.md` and check it in step 7. `25`: `agy` wrote a complete answer and
then did not exit; the runner stopped it after 60 seconds idle and `review.md` holds the
answer: check it in step 7 as for `0`. `20`: do the review yourself; never delegate again.
`24`: start a fresh `run` with a full brief if still needed. `2` (invalid input, unsafe
run root, oversized material, cr-request missing, or `agy` settings that allow commands or
cannot be read; see Security Model): fix the invocation once, otherwise
unavailable. `21`, `22` (partial output is no review; cause in `run.log`), `23`:
unavailable, apply the fallback. `130`: interrupted, no review; partial artifacts stay
for diagnosis. [cli-runtime.md](cli-runtime.md) has the allowlist, the
artifacts, the background launch, and `## Exit codes`.

### 7. Check and hand off the result

`review.md` holds unverified claims from another model. Before the handoff, check that it
names the reviewed target, states coverage, gives every verdict, and lists findings with
IDs, severities, and locations, or states that there are none. A result without verdicts
and coverage is incomplete; exit code 0 alone proves neither.

After all reviewer processes finish and each usable result passes that check, compare
the reviewed target and fingerprint with the host's target pin. Treat a mismatch as
stale and do not hand it off as a review of the current target. The trusted host persists
the full reports and identities before showing a compact result. Write a
private JSON identity file with the complete target pin from steps 1 and 4, including
`Tree` or the requirement document `sha256` hashes, then run:

```text
python3 <skill-dir>/scripts/cross_review.py archive --session-root <session-root> \
  --run-id <unique-run-id> --identity-file <host-identity-json> \
  --run-dir <completed-run-dir> [--run-dir <another-completed-run-dir>]...
```

The stable paths are `<session-root>/.cross-review/<run-id>/reviewer-<n>/review.md` and
`identity.json`, in argument order. The host chooses the run ID and supplies identity;
reviewer text never supplies the archive destination. The helper checks ownership,
symlinks, private permissions, collisions, and Git exclusion. Any archive failure is
`INCOMPLETE` (exit 26): name the failed path and operation, retain the temporary output,
and stop automatic handoff. A link into OS temporary storage alone is incomplete.
The archive API and shared local `cr-request` helper are in
[cli-runtime.md](cli-runtime.md#host-archive).

With several reviewers, check each result on its own, then hand all findings to
`cr-received` in one list. Finding IDs carry the reviewer (`R1-codex-F1`,
`R1-antigravity-F1`); mark findings several reviewers raised about the same location and
defect as one, citing each.

Show each reviewer's result in the chat as one compact block; the full text stays in its
`review.md`:

```text
| Intent | System | Craft | Critical | Important | Minor |
| --- | --- | --- | --- | --- | --- |
| <verdict> | <verdict> | <verdict> | <n> | <n> | <n> |

Readiness: <ready | ready with fixes | not ready>
Reviewer: <reviewer> · <model> · effort <effort> · ~$<cost_usd>
Session: ~$<session_total.cost_usd> over <runs> runs[, incomplete]   (after resume only)
Target: ~$<target_total.cost_usd> over <rounds> rounds[, incomplete]   (from round 2)
Warning: same CLI as the host, not a cross-vendor review   (same_cli group only)
Stopped: agy answered and did not exit   (exit 25 only)
Details: <session-root>/.cross-review/<run-id>/reviewer-<n>/review.md
```

The table and `Readiness` come from the checked `review.md` (its axis verdicts, `Summary`,
and `Merge readiness`), as in the installed cr-request `references/compact.md` without its
`<details>` block. The `Reviewer` line and the conditional lines after it are the run
report, built from `usage.json` (or the `usage:` line); show a conditional line only where
its note applies. Numbers carry thousands separators (`1,204`). Add "incomplete" when the
total's `complete` is false. Write `unknown` for any field without data, and `cost unknown`
in place of `~$<cost_usd>` when the model has no price; `agy` reports no cost, so an
Antigravity run always shows `cost unknown`. The cost is a list-price equivalent, not a
bill. A missing `usage.json` does not make the review incomplete. Write sums as `~$`, as the
runner's `usage:` line does.

Findings are not listed in the chat: `cr-received` reads them from the `Details` path,
validates each, and chooses its disposition. With several reviewers, show one block per
reviewer, each with its own `Details`, and one shared `Next step` line after the last.
Keep their verdicts, counts, readiness, model, effort, and cost separate; do not turn
several results into an unchecked aggregate PASS.
Keep the run directory, the target fingerprint, and the reviewer session with the review
record.

With a record host, found as `cr-request` step 7 finds it (the plan, else the spec), append
to its record (the plan's `## Execution record` or the spec's `## Verification record`) the
lines `cr-request` step 7 writes, one `Review` line per reviewer, one `Finding` line per
finding, and the `Round review <n>` line of the round, with `reviewer <agent> <model>` and
mode `document` for `plan`, `code` for `implementation`, and `re-review` for a follow-up
round. Append the `Ruling: review R<n> origin <automatic|user-started|external> -
<source and authorization>` from `cr-request` once per review. Never rewrite existing
lines. Like `cr-request`, this skill never creates a spec's
`## Verification record`: before `implement` or `verify` adds it, the lines stay in the
result.

The last line of the result is the next step:

| Result | Last line |
| --- | --- |
| Findings, or a follow-up leaves a previous finding `NOT ADDRESSED` | `Next step: cr-received - <n> findings to rule on: <archived review.md path>` |
| Clean, and a full `Verify: PASS` exists on this tree | `Next step: finalize - reviewed and verified on this tree` |
| Clean, no full `Verify: PASS` on this tree | `Next step: verify - review is clean, verification missing on this tree` |
| Clean `plan` mode | `Next step: implement - <plan path>` |
| Unavailable | `Next step: none - choose another reviewer or retry` |
| Archive incomplete | `Next step: none - persist the full review and identity before handoff` |

With several reviewers, the findings line lists every `review.md` path, separated by `, `.

Under `--auto`, the host may perform already authorized defer issue and thread reply
actions, and the bounded REJECT reply in `cr-received` `references/return.md`, without
asking again. This grants no reviewer write token or general outward permission; all
other outward actions and merge, release, and publication retain their approval gates.

With `--auto` in the arguments, a `Next step` that names a local skill (`cr-received`,
`verify`, `implement` after a clean `plan` round, the next `cross-cr` round of step 8)
is not handed back: start that skill in the same turn and pass `--auto` on.
The turn still ends on a decision that belongs to the user (spec approval, `NEEDS RULING`,
`ESCALATE`, an open question, the commit-policy question, a choice that changes the spec or
a public contract), on the Round rule, before any other `Outward` action, on `INCOMPLETE` or
`BLOCKED`, and before the `finalize` option choice, which is the one final confirmation:
nothing is pushed, opened as a PR, merged, tagged, or published under `--auto` without it.
`--auto` is never written into a plan, spec, or record, and a `Next step` line never
carries it; a new session or a manual call runs without it.

### 8. Repeat rounds

Automatic rounds:

1. **Start.** After `cr-received` decides that another round is needed (an accepted material
  change, security, data loss, public contract, or several interacting fixes), start the
  next `cross-cr` round of the same mode yourself, without asking, up to the round limit of
  Count. Under `--auto` the loop runs without pauses: the review, `cr-received --auto`,
  `verify --auto`, then the next round: a re-review that `cr-received` or `verify` names
  comes back here as that round, never as a same-host `cr-request`. Each round is a fresh
  `run --followup <previous-run-dir> --dispositions <file>` without `--brief`: the runner
  reuses the host part of the previous brief, its target, mode, and exclusions (a new
  `--exclude` adds to them), rebuilds the diff, untracked files, hashes, and `Status:` lines
  from the current files, and states the new round's finding IDs. A previous target pinned
  to a commit id (`range BASE..<sha>`, `tree <sha>`) is exit `2`: pass `--target` with the
  head that holds the fixes.
  Pass a new `--brief` only when a fact the host wrote has changed (a requirement, the
  host evidence), written from the current files; never feed the previous round's
  `brief.md` back in. With several reviewers, each follows up on its own previous run,
  and its dispositions file lists its own findings.
2. **Named rounds.** A number of rounds or a sequence of reviewers the user names
  explicitly authorizes exactly those rounds: they run one after another without asking,
  even on an unchanged target or past the limit, and Skip and the unchanged-target rule of
  step 1 do not apply to them. After them the usual rules hold. When the user named 2
  rounds, round 2 starts without asking and round 3 only after asking.
3. **Count.** Only automatic rounds count: at most three, or the number of named rounds.
  A round the user starts by an explicit call after the limit runs once past it and is
  recorded as
  `Ruling: round R<n> started by the user past the limit - <user's words> - <cost if wrong>`.
  The same cause twice escalates to the user, in user-started rounds too. Round numbers
  `R<n>` run over every round of the target, whichever reviewer ran it. The target is the
  plan and spec paths in `plan` mode, and the base and branch in `implementation` mode.
  The runner's `Target:` total covers one reviewer's follow-up chain; for a sequence of
  reviewers on one target, the report adds the chains up.
4. **Skip.** Do not start a round automatically when the last round had no accepted
  Critical or Important finding, when the round was `unavailable`, or when the user said
  not to repeat the review for this target. An explicit request on an unchanged target
  after a clean round follows step 1.
5. **After the limit.** Ask before every further round and give a recommendation with its
  reason: worth it when the last round found an accepted Critical or Important finding
  whose fix changed a contract; can stop when only Minor, rejected, or deferred findings
  remain or when running tests catches the remaining risk better. Without a user channel,
  stop at the limit and put the recommendation in the report.

Each round report shows the round cost and the cumulative cost of the target.

Local `Round review <n>` lines order reviews; count distinct automatic origin Rulings
against the budget, separately from local IDs, external review counts, and fix attempts.
Reconstruct unknown old provenance from evidence or escalate instead of guessing. With
no host keep these details in the conversation. The last allowed automatic round is
decision-only: escalate Critical or unsafe findings; fixes require explicit permission,
stale verification, and still require re-review even after the budget is exhausted. Write the dispositions file from the `cr-received`
record: every previous finding ID with accepted and fixed, rejected with reason, deferred,
or escalated, open.

### 9. Follow up in the same session

To ask the reviewer a clarifying question about the same target:

```text
python3 <skill-dir>/scripts/cross_review.py resume --run-dir <previous-run-dir> \
  --prompt "<follow-up>"
```

The runner reuses the reviewer, repository, model, effort, and session of the previous run,
keeps the same read-only policy, wraps the prompt with a read-only and no-delegation
reminder, and writes a new run directory. Changed requirements, base, or file set need a
fresh `run`; an earlier PASS never covers a new target.

## Anti-patterns

1. choosing the reviewer from environment variables, or picking the same CLI as the host
  without the user's explicit group;
2. running several reviewers one after the other, or reporting the review as complete when
  one reviewer failed without naming the gap;
3. passing an effort outside `low|medium|high|xhigh|max`, or reusing the first round's
  model when the user gave a new one;
4. sending a brief that relies on skills, conversation history, or files the reviewer is not
  told to read;
5. guessing `main` as the base, or omitting staged, unstaged, or selected untracked changes;
6. sending `.env` files, credentials, private keys, or files behind external symlinks;
7. truncating a large diff silently, or embedding the diff, untracked files, or the
  cr-request sections by hand instead of letting the runner add them;
8. copying the previous round's `brief.md` into a follow-up round;
9. building CLI arguments by hand instead of calling the runner;
10. treating a running background job, a partial `review.md`, or exit code 0 alone as a
  complete review;
11. fixing code or accepting findings inside this skill;
12. reusing a review after the plan, spec, or diff changed;
13. repeating a round on an unchanged target after a clean result without offering a
  different reviewer, model, effort, or focus;
14. committing foreign changes to make a boundary fit `--target`, or judging the user's own
  uncommitted edits as findings;
15. passing `--auto` to the runner.

## Preservation map

This map covers every original body block from cross-cr 0.0.3 at commit
`7a96dfc1ffa83a604594e3b3e441b60d31df222c`. Original line ranges identify
paragraphs, headings, list groups, tables, and code blocks. Each digest is the first
16 hexadecimal characters of SHA-256 over its original text after removing outer
whitespace and top-level list markers and normalizing relative `references/` links.
The destination contains the same normalized block. New entrypoint step links require
reading each moved section before its step; Anti-patterns apply before acting.

| Original lines | Destination | Normalized SHA-256 prefix |
| --- | --- | --- |
| 11-11 | `SKILL.md` | `b93ba3da471bd6fe` |
| 13-16 | `SKILL.md` | `7bd24496c62a8102` |
| 18-18 | `SKILL.md` | `e0c51137a655e9a1` |
| 20-20 | `SKILL.md` | `bb663236a370e886` |
| 22-31 | `SKILL.md` | `a6d7485b7d913497` |
| 33-34 | `SKILL.md` | `8c2a4043f15fafc9` |
| 36-39 | `SKILL.md` | `85ef1dc2e9450765` |
| 41-42 | `SKILL.md` | `6182474738f40a5c` |
| 44-44 | `SKILL.md` | `5802df105916ad8e` |
| 46-51 | `SKILL.md` | `99ea8e596e78a61a` |
| 53-55 | `SKILL.md` | `e2c95ac62b272239` |
| 57-57 | `SKILL.md` | `6d75aebc18a89816` |
| 59-61 | `SKILL.md` | `fac7e427e65e94c6` |
| 63-70 | `SKILL.md` | `806744dd9287c0cb` |
| 72-75 | `SKILL.md` | `66db644302fed10b` |
| 77-79 | `SKILL.md` | `6bb3dd9ddf3ef065` |
| 81-85 | `SKILL.md` | `74d6c926a416bf85` |
| 87-89 | `SKILL.md` | `3a2cefececec8bf1` |
| 91-94 | `SKILL.md` | `fe430ee08e1dc33f` |
| 96-101 | `SKILL.md` | `06a17bf718384781` |
| 103-103 | `references/workflow-details.md` | `7136000e494604c0` |
| 105-105 | `references/workflow-details.md` | `7f81727f6a0f0760` |
| 107-111 | `references/workflow-details.md` | `8226eec689cbaf8d` |
| 113-120 | `references/workflow-details.md` | `6f5a9e005fabf9b8` |
| 122-128 | `references/workflow-details.md` | `9d02671bd3bc0b64` |
| 130-136 | `references/workflow-details.md` | `5d9592c68542e293` |
| 138-144 | `references/workflow-details.md` | `f9783623646f5316` |
| 146-146 | `references/workflow-details.md` | `8badedd979d14dda` |
| 148-149 | `references/workflow-details.md` | `a5cbcda579931e9e` |
| 151-167 | `references/workflow-details.md` | `2f98163931bea0be` |
| 169-172 | `references/workflow-details.md` | `43310d7f99bde86c` |
| 174-174 | `references/workflow-details.md` | `68b2a48881ff98e8` |
| 176-176 | `references/workflow-details.md` | `bfa9e55b479ba8d1` |
| 178-182 | `references/workflow-details.md` | `3e07930726be3c39` |
| 184-188 | `references/workflow-details.md` | `6489cebab0f1ccea` |
| 190-198 | `references/workflow-details.md` | `7d77da3d08ac4c6f` |
| 200-204 | `references/workflow-details.md` | `3210822d0e98d2c1` |
| 206-206 | `references/workflow-details.md` | `2fffed0fabf02b53` |
| 208-216 | `references/workflow-details.md` | `87c26bfadfd2b9a6` |
| 218-218 | `references/workflow-details.md` | `3c80456b6d0edd94` |
| 220-223 | `references/workflow-details.md` | `143960aa61b96d26` |
| 225-240 | `references/workflow-details.md` | `0768ebd86594207b` |
| 242-242 | `references/workflow-details.md` | `1c568b25931ed424` |
| 244-256 | `references/workflow-details.md` | `3072c507c3c82de5` |
| 258-258 | `references/workflow-details.md` | `48b853cbe35a65d8` |
| 260-262 | `references/workflow-details.md` | `aea3b2c73ab7f591` |
| 264-264 | `references/workflow-details.md` | `0a2dd9439d7671f2` |
| 266-269 | `references/workflow-details.md` | `e07427390bc1b5e8` |
| 271-277 | `references/workflow-details.md` | `3c952decac4e4121` |
| 279-285 | `references/workflow-details.md` | `c224d54b6036e5d0` |
| 287-296 | `references/workflow-details.md` | `d594dcd1b2cbf896` |
| 298-298 | `references/workflow-details.md` | `b2e6f9fdb4a04fb4` |
| 300-303 | `references/workflow-details.md` | `366a569fb992a68c` |
| 305-310 | `references/workflow-details.md` | `b128bcc10e370c28` |
| 312-316 | `references/workflow-details.md` | `08ee3233ddb4f65b` |
| 318-325 | `references/workflow-details.md` | `df8055dcb05eee80` |
| 327-330 | `references/workflow-details.md` | `e6c825d22d4b9d73` |
| 332-333 | `references/workflow-details.md` | `e5cf65ba72106a56` |
| 335-338 | `references/workflow-details.md` | `57d1a8c263cc9c05` |
| 340-347 | `references/workflow-details.md` | `66897f71e890ae0f` |
| 349-358 | `references/workflow-details.md` | `b8c4908141c0f7e5` |
| 360-366 | `references/workflow-details.md` | `7d373c2b244524ef` |
| 368-377 | `references/workflow-details.md` | `d477c86cdf19ee2d` |
| 379-379 | `references/workflow-details.md` | `416eddcdad724b3a` |
| 381-388 | `references/workflow-details.md` | `8609eef9ca55fe96` |
| 390-390 | `references/workflow-details.md` | `791ff1d90e333d5b` |
| 392-395 | `references/workflow-details.md` | `c66d0565406066da` |
| 397-406 | `references/workflow-details.md` | `2ba2200f8208c78a` |
| 408-408 | `references/workflow-details.md` | `9ed1d1ff7287a56e` |
| 410-410 | `references/workflow-details.md` | `843f0752d040ac95` |
| 412-450 | `references/workflow-details.md` | `5e7cd3194a3cfb3a` |
| 452-452 | `references/workflow-details.md` | `36eaf0d64317e7e0` |
| 454-461 | `references/workflow-details.md` | `c6c5114fe0f65dea` |
| 463-463 | `references/workflow-details.md` | `a70b7d8e77d75fde` |
| 465-465 | `references/workflow-details.md` | `f06d22712518133c` |
| 467-470 | `references/workflow-details.md` | `ef26823573fa5d9f` |
| 472-475 | `references/workflow-details.md` | `ea5f92006d86bae4` |
| 477-477 | `SKILL.md` | `b90066692c83c88a` |
| 479-481 | `SKILL.md` | `785bdc2929667c5f` |
| 483-485 | `SKILL.md` | `7be8e278689c2969` |
| 487-509 | `SKILL.md` | `094ddcaab780e569` |
| 511-514 | `SKILL.md` | `2ca9d2f1f5e917eb` |
| 516-516 | `SKILL.md` | `418777475000b018` |
| 518-549 | `SKILL.md` | `47692f903a7740f3` |
| 551-551 | `SKILL.md` | `f7deca2f6819859a` |
| 553-560 | `SKILL.md` | `0cf0fb621ae9e6a6` |
| 562-562 | `references/workflow-details.md` | `2d7b716cde65fe0b` |
| 564-586 | `references/workflow-details.md` | `1054d8cfd2c96e92` |
| 588-588 | `SKILL.md` | `65b72d86eeeb214a` |
| 590-593 | `SKILL.md` | `c9c216f0a5df4218` |

The runner still reads the sibling `cr-request` references by their existing paths.
Its `Reviewer instructions`, `Result contract`, and `Severity` brief headings and
`Intent`, `System`, and `Craft` lens headings are unchanged. The host-only boundary
starting with `` `Not checkable `` stays in that dependency. This refactor changes
no runner, authentication, model, extraction rule, or result contract.
