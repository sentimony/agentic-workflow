# Changelog

## [0.0.3] - 2026-10-27

- The time in the `Verify` line comes from `date '+%Y-%m-%d %H:%M'` right after the
  re-pin, never from memory (request 20261026-1911).
- The `Next step` table counts only `Review` lines in `code` mode, or `re-review` after a
  code review, as a review of the implementation: a journal with only spec or plan
  reviews leads to `cr-request`, not `finalize`; open blockers still come from every
  round (request 20261025-1712, verify).
- New `references/clean-clone.md`: rebuild an uncommitted tree in a fresh clone (`git
  clone`, `git diff --binary HEAD | git apply`, the untracked files the fingerprint
  covers) and compare fingerprints before trusting it; a copy without `.git` is not a
  clean checkout (request 20261025-2044, verify).
- Journal lines go inside the record's `text` block, before its closing fence, never
  after it (request 20261025-1800).

## [0.0.2] - 2026-10-27

- Rename only: the plugin `awf` is now `aw`; version bump only, the text is unchanged.

## [0.0.1] - 2026-10-22

- Initial release, replacing devflow verification-gate in the awf chain: claims numbered
  before checks from the spec criteria, plan tasks, journal, and the caller's words; a
  tree fingerprint pinned before and after checking; fresh evidence only; check
  equivalence; a bar check for weakened tests, suppressions, and lowered thresholds;
  suspiciously easy success; four verdicts with review blockers read from the journal;
  full and compact reports; the `Verify` journal line; the shared Round rule; a
  standalone mode that creates a plan-journal; and a `Next step` line.
