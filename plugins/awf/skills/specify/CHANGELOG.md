# Changelog

## [0.0.1] - 2026-10-22

- First release: route triage (`direct`, `note`, `design`), evidence register,
  questions with a recommended answer, two approaches, a fresh-reader check, a spec
  with `AC<n>` criteria, and an explicit approval barrier.
- The `direct` route hands `implement` one sentence with the request's domain values;
  secrets appear only as placeholder names.
- Calls `scope-check` after each save when it is installed.
- Ends every result with a `Next step` line.
