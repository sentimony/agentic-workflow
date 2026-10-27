# Changelog

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
