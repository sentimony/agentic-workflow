# PR title and body

Used by the `pr` option and by [After every push](#after-every-push).

## Title

- At most 72 characters.
- Describes the whole branch, not the first or the last commit. Read every commit
  before writing it:

  ```sh
  git log --oneline <base>..HEAD
  ```

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

- <one line per behavior or file group, covering every commit in <base>..HEAD>

## Scope and trade-offs

<what the change deliberately does not do, and the alternative that was not taken>

## Blast radius and reversibility

<who and what is affected if this is wrong; whether a revert of the squash commit
undoes it fully, or what does not come back (data migrations, published artifacts)>

## Verification

- `<command actually run>` -> <result>
- Verify: PASS full tree <tree SHA> <YYYY-MM-DD HH:MM> | not verified on this tree

## Rulings

- <each Ruling line from the record>

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
  none.
- **Rulings** and **Deferred** copy the lines from the record host: the plan's
  `## Execution record` or the spec's `## Verification record`, including those written
  by `cr-received`. **Deferred** also lists every unfinished plan task with an
  `Outward` field; `finalize` does not run them. Without a host, write `none`.
- The line `Stacked on #<n>` appears only for a stacked PR (SKILL.md "Find the base
  branch"); otherwise drop it.
- Credentials, tokens, and values from env files never go into the title or the body;
  name them by placeholder (`<API_TOKEN>`).

## After every push

When the branch already has an open PR, a push changes what the PR contains. After
each push:

1. Re-read `git log --oneline <base>..HEAD`.
2. Rebuild the title and every section from the current branch and record host.
3. Update both on the forge:

   ```sh
   gh pr edit <pr> --title "<title>" --body-file <file>
   ```

A pushed tree that differs from the verified one also needs a new `Verify` line before
any merge; the body then quotes the new line. Turning a draft into a ready PR
(`gh pr ready <pr>`) passes the gate of a ready `pr` first, and the body then replaces
`not verified on this tree` with the accepted `Verify` line.
