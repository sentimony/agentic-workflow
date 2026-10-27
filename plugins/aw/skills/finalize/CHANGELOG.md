# Changelog

## [0.0.3] - 2026-10-27

- After a squash the worktree always ends on the fresh base, with or without branch
  deletion, or detached on `origin/<base>` when another worktree holds the base; the
  report gives the branch, `HEAD`, and whether it equals `origin/<base>`
  (request 20261024-2226).
- Before the merge, a PR that changes `.github/workflows/` needs the `workflow` scope on
  the CLI token; a merge refused with a generic text gets its reason from the same merge
  through the REST API, pinned to the same head (request 20261026-1946).
- A repository without required checks waits for all PR checks, and a `mergeStateStatus`
  other than `CLEAN` stops the merge; the report says which checks were read
  (request 20261026-2331, no required checks).
- The uncommitted journal is saved and restored to `HEAD` before switching to the base,
  then written back; the diff must show only added record lines, and the report names
  the journal's fate (request 20261026-2331, uncommitted journal after squash).

## [0.0.2] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; the text changes only that name.

## [0.0.1] - 2026-10-22

- Initial release: replaces devflow `branch-finish`. Reads the Git state before every
  action, takes the base branch from the strongest source, and integrates only with a
  full `Verify: PASS` on the current tree fingerprint and nothing but the plan left
  uncommitted, otherwise hands back to `verify`.
- Six options: `merge`, `pr`, `squash`, `keep`, `discard` (explicit request only, with
  the commits that will be lost), and `pause` (wip commit with a continuation note).
- Squash merge recipe pinned to the verified head, PR title and body template with
  rulings and deferred items from the execution record, and cleanup behind a workspace
  barrier and a branch barrier.
