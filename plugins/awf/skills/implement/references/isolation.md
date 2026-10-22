# Isolation

Isolation keeps task work apart from changes that are not part of the plan. Pick the
lightest option that gives that separation.

## Detect what already exists

Before creating anything, check where the session already is:

- `git rev-parse --show-toplevel` - the root of the current working tree;
- `git rev-parse --git-dir` and `git rev-parse --git-common-dir` - when they differ, the
  session already runs inside a linked worktree;
- `git worktree list` - worktrees that already exist for this repository, including one
  for this branch;
- the harness - a sandbox or an isolated workspace the agent runtime already provides.

Existing isolation is used as it is. Do not stack a new worktree on top of one.

## Order of preference

1. **Work in place.** A full option, chosen whenever the branch is right and the
   uncommitted changes (if any) are unrelated and can be kept out of task commits by
   committing with explicit paths.
2. **The harness mechanism.** When the runtime offers its own isolated workspace, use it
   instead of managing worktrees by hand.
3. **A Git worktree.** When the work must not share a working tree with other changes or
   other sessions: `git worktree add -b <branch> <path> <base>`, placed where the
   project's instructions say. Record its path as `Root` in the journal.

Parallel subagents each need a separate workspace; two writers in one working tree is
never an option.

## Limits

A worktree separates files only. Ports, databases, caches outside the tree, and external
services are still shared; tasks that touch them are not independent just because they run
in different worktrees.

## Never

Never reset, stash, clean, or check out over changes that someone else left in the tree.
Name them in `Initial dirty state` and work around them. Removing a worktree after the
change is integrated belongs to `finalize`, not to this skill.
