# Review Identity and Archive

## Host-owned local archive

The shared resolver accepts `session_root` captured by the trusted host from its
session repository before switching to any target directory. Resolve it to that
repository's absolute top level once and pass it explicitly to local `cr-request`.
Never infer it from the reviewed target or accept a replacement from reviewer output.
The target may be a different repository. A caller specifying another archive owns its
destination and setup; preserve the complete report and target identity there.

1. Local `cr-request`: `~/.sentimony/agentflow/cr-request/<project>/<run-id>/review.md` and
  `identity.json`; `<project>` is the slug of the main checkout of `<session_root>`
  (`python3 <skill-dir>/scripts/project_slug.py --cwd <session_root>` prints the root; `<skill-dir>` is the
  installed skill directory; the script refuses a HOME inside the project). Archives that
  older versions wrote to `.cross-review/local/<run-id>/` stay as they are, and references
  to them in earlier journals remain valid.
2. The host chooses a unique run ID with only ASCII letters, digits, `.`, `_`, or `-`,
  beginning with a letter or digit; reject `.`/`..`, path separators, and collisions.
  Keep every directory from `~/.sentimony` down to the run directory private (`0700`),
  and archived files `0600`. Reject symlink components, symlink destinations, paths
  escaping the resolved HOME (resolve HOME first, then open every component with `O_NOFOLLOW` through
  directory descriptors so a swap after the check cannot redirect the write), and incompatible ownership; never follow or
  overwrite them. A missing or unusable HOME fails the archive; no fallback path is used.
3. The local archive lives outside every repository: do not edit `info/exclude` or the
  tracked `.gitignore` for it, and do not stage archive files.
4. After the reviewer has fully finished, the trusted host validates the output and
  writes the archive, using private temporary files and atomic replacement within a
  newly created run directory. Reviewers never receive permission to write the archive.
  Working files live outside the target repository until the host archives them.
5. Persist the entire report and identity before compact handoff. On any permission,
  exclusion, validation, or write failure, report `INCOMPLETE` with the failed path and
  operation, retain available temporary output for recovery, and stop automatic
  handoff. A link into OS temporary storage alone is incomplete.

`identity.json` has `schema_version=1`, `run_id` (the local string ID), `session_root`,
`target_root` (absolute), `target_identity` (the complete pinning record, including
`Tree` or document `sha256`), `reviewer_model`, `reviewer_effort` (string or `null`),
`cost_usd` (non-negative number or `null`), and `review_file` (`review.md` for local
`cr-request`). Unknown effort/cost is displayed as `unknown`; no guessed value or
GitHub source ID is created for a local review. Keep multiple reviewers' identities
and findings separate. The host's identity and permissions checks precede every write.

Exclude the entire `.cross-review/` archive, including any legacy `local/` folder, from target snapshots, briefs, and attachments. The local archive now lies
outside the repository, so a read-only reviewer inside the target cannot discover it by
walking the tree. This does not promise deny-read isolation: a same-host
reviewer can still read
repository-local archives. The owner accepts that read risk; mandatory deny-read and
an unavailable-reviewer gate are outside this contract. Preserve the existing project
trust and read-only boundaries. Focused-test write isolation is a separate rule in
[brief.md](brief.md), with an original-status/hash comparison rather than a read
isolation claim.
