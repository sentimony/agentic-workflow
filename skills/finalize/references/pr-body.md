# PR title and body

Used by the `pr` option and by [After every push](#after-every-push).

## Title

- At most 72 characters.
- Describes the whole branch, not the first or the last commit. Read every commit
  before writing it:

  ```sh
  git log --oneline origin/<base>..HEAD
  ```

  The range is the PR's own, against the remote base: the local base may be ahead of it,
  as on the work-on-base path, where `<base>..HEAD` misses the work.

- On a squash merge the title becomes the commit subject on the base, so write it as
  that subject.

## Body

Sections in this order. Leave a section in place with `none` rather than dropping it.
A PR whose base is the branch of another open PR starts with the line `Stacked on #<n>`,
naming that PR, before `## Why`.

```markdown
Stacked on #<n>

## Why

<the problem or the goal, in one or two sentences; link the spec or issue>

## What changed

- <one line per behavior or file group, covering every commit in origin/<base>..HEAD>

## Scope and trade-offs

<what the change deliberately does not do, and the alternative that was not taken>

## Blast radius and reversibility

<who and what is affected if this is wrong; whether a revert of the squash commit
undoes it fully, or what does not come back (data migrations, published artifacts)>

## Verification

- `<command actually run>` -> <result>
- Verify: PASS full tree <tree SHA> <YYYY-MM-DD HH:MM> | not verified on this tree

## Rulings

- <each current reviewer-relevant decision, its reason, and a finding ID or document section when useful>
- <link to the complete record>

## Deferred

- <each Deferred line from the record, with its owner or place>
- <each unfinished task with an Outward field: Task <n> (outward): <what and where>>
```

Filling rules:

- **Verification** lists commands that were run on this tree, with their real result,
  and quotes the `Verify` line the gate accepted with its full fingerprint. A command
  that was not run does not appear. A draft (`pr --draft`) writes
  `not verified on this tree` instead. With no record host, quote the `Verify` line
  printed in this session's report, or write `not verified on this tree` when there is
  none; that alternative is permitted for a draft only. A hostless ready PR needs
  freshly executed project checks on the current full committed head and fingerprint,
  with the exact commands, results, and target in both this body and the handoff.
  Undefined or unavailable project checks require a draft or clarification.
- **Rulings** summarizes current decisions relevant to behavior, contract, security,
  or accepted trade-offs. Give each decision and its reason briefly, with a finding ID
  or document section when useful, and link to the complete record: the plan's
  `## Execution record` or the spec's `## Verification record`. Include relevant
  decisions written by `cr-received`. Leave session history, permissions, local
  environment problems, and resolved waiting states in the record. Do not invent
  rejected alternatives; write `none` when no decisions apply. Rebuild this section
  after each push from the final state, excluding superseded decisions.
- **Deferred** retains current deferred items with their owner or place, accepted risks,
  open blockers, and outstanding checks. List every unfinished plan task with an
  `Outward` field; `finalize` does not run them. Write `none` when nothing applies.
  Without a record host, write `none` for record-based items; still report any known
  current risks, blockers, outstanding checks, and unfinished `Outward` tasks. These
  summaries do not replace verification or review gates.
- The line `Stacked on #<n>` appears only for a stacked PR (SKILL.md "Find the base
  branch"); otherwise drop it.
- Credentials, tokens, and values from env files never go into the title or the body;
  name them by placeholder (`<API_TOKEN>`).

## After every push

When the branch already has an open PR, a push changes what the PR contains. After
each push:

1. Re-read `git log --oneline origin/<base>..HEAD`.
2. Rebuild the title and every section from the current branch and record host.
3. Update both on the forge:

   ```sh
   gh pr edit <pr> --title "<title>" --body-file <file>
   ```

A changed head or base invalidates applicable readiness, verification, and review
evidence, even if the fingerprint happens to match. Reread full head/base and
mergeability before expensive checks, ready, waiting, and merge; changed content needs
a new `Verify` line. The body quotes only evidence valid for that target. Turning a
draft into a ready PR (`gh pr ready <pr>`) requires fresh local project checks on the
committed target, including hostless work. Remote jobs may remain missing/pending and
start after ready; list them as outstanding rather than successful. DRAFT or a
check-related BLOCKED/UNSTABLE state can permit readiness; actual conflicts, stale
identity, red checks and incomplete observations still block. Unknown policy remains
unknown and requires its merge-time resolution. The body replaces `not verified on
this tree` with the local accepted `Verify` line and keeps remote merge-gate status
separate. Ready never claims that outstanding jobs passed.
