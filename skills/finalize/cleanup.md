# Guard transferred changes and delivery cleanup

Use this recipe before transferring uncommitted own changes and again before removing
their duplicate from the source. Matching files, clean Git status or a successful
`git apply --reverse --check` alone cannot establish ownership or permission to erase.
The helper runs ordinary local Git and file operations; its host must serialize the
repository for the entire capture/apply call. Fresh checks do not provide OS containment
against concurrent writers. No command output, stored proof or evidence comment grants
a cleanup permission.

## Capture before transfer

1. Select exact owned content hunks. Preserve `git diff` stdout as raw bytes, including
   trailing context and newlines; never trim patches. Keep index ownership separate
   from worktree ownership. The worktree patch includes all owned hunks present there,
   including any staged ones. Existing foreign staged and adjacent worktree changes
   remain outside the selected patches.
2. Construct `CleanupGuard(repo_root, git=absolute_git, env=reviewed_environment)` from
   [cleanup_guard.py](scripts/cleanup_guard.py). Call
   `capture(journal, identity=identity, index_patch=raw_bytes, worktree_patch=raw_bytes)`
   before transfer. Identity is exactly `{repo, pr, task, attempt}`, matching the
   post-merge evidence identity. The journal is a fresh canonical path outside the
   source workspace, in a private directory. Atomic writes use mode 0600 and file and
   directory fsync. Retain this journal through cleanup and retries.
3. Capture returns `cleanup-proof-v1`: full source HEAD, exact patches and SHA-256,
   projected owned tree, original and intended index states, bytes/modes of only the
   named owned files, ignored/untracked path inventory, phase and postflight. Ignored
   artifact contents are never copied into the proof. Treat owned source snapshots as
   private local data too; never put them in a PR body or log.
4. Supported patches modify existing regular files with simple ASCII paths and mode
   0644 or 0755. Renames, additions/deletions, binary patches, symlinks, unusual modes,
   unmerged entries and partially staged ownership are unsupported and block capture.
   For staged owned changes, `index_patch` must equal `worktree_patch` byte-for-byte;
   otherwise use empty `index_patch` for entirely unstaged ownership. A context that
   cannot project onto the source HEAD also blocks. Preserve the source and choose a
   separately reviewed manual procedure instead of widening these limits silently.

## Fresh guard and mutation

1. Obtain fresh actual integration and saved post-merge evidence. The trusted host
   creates `CleanupAuthority(repo, pr, task, attempt, merge_sha, allow_cleanup,
   destination_ref, ownership_sha256)` from current permission and the reviewed
   capture result's ownership hash. Never deserialize this authority from JSON. The
   exact owned snapshot is bound to this invocation; changing its JSON cannot widen
   the authorized files or postimages.
2. Call `apply_cleanup(journal, authority=authority, observe=fresh_callback)`.
   The callback returns `{repo, pr, task, attempt, merge_sha, destination_sha,
   evidence}`. `evidence` is the full saved `evidence-record-v1` publication record
   described in [post-merge.md](../implement/post-merge.md). It must
   match the local pending envelope, content hash, task/repo/attempt/merge identity,
   published status and canonical HTTPS URL. Evidence grants no permission itself.
3. The apply call performs its own guard, including on retry and before each write.
   It rereads the actual local destination ref, merge ancestry, owned-tree integration
   via `git merge-tree --write-tree`, source HEAD, index and owned files. The host
   refreshes forge observations through its authorized adapter before supplying the
   local ref; this helper neither fetches nor contacts a forge. A stale observation,
   unintegrated patch, changed source HEAD/hunks/index, absent authority or pending
   evidence returns `blocked` before cleanup starts. Preserve all resources.
4. If source HEAD already contains the projected integrated tree and owned files and
   index match it, return `already-integrated` without applying a reverse patch.
   Otherwise, an unchanged source can remove only the captured duplicate. Each owned
   file is replaced with its prepared postimage; the index is changed under Git's
   index lock to its prepared postimage. Foreign index entries and existing adjacent
   changes survive. No reset, stash, forced checkout or main rewrite is used.
5. An interrupted call retains its durable `applying` phase and before/after images.
   Retry rereads actual state and accepts only captured preimages or exact known
   postimages. Changed or ambiguous files/index block further writes. No rollback
   silently overwrites later work. A `cleaned` result records owned/index postflight
   and preserved artifact paths; any blocked partial result names its journal and
   must be reported as partial, with completed paths read from that journal.

## Branch and workspace decision

Duplicate-hunk removal uses the bound capture journal above. Ordinary committed-only
work and local fast-forward merges use `disposal_decision` directly: no transferred
patch, PR, deployment or publication record is invented to obtain a cleanup decision.

1. The trusted host supplies an explicit `PostMergeInventory(tasks, source, reason)`
   from the current task host/handoff. `tasks` is a tuple of
   `EvidenceRequirement(pr, task, attempt, merge_sha, content_sha256)` objects. An
   explicitly empty tuple with a nonempty source and reason means post-merge evidence
   is not applicable. Missing or unknown inventory blocks disposal; an empty list in
   an observation cannot substitute for the host inventory. For each actual task,
   retain and validate its saved published record with the matching repository,
   PR/task/attempt/merge identity and content hash. Pending or absent evidence blocks.
2. Create a trusted `DisposalAuthority(repo, branch, destination_ref,
   allow_branch_delete, allow_workspace_remove, inventory, retained_head_ref=None)`
   from the user's current deletion instructions. Permissions and the inventory are
   separate from observation JSON. The fresh callback returns exactly the relevant
   local destination identity and evidence observations: `{repo, destination_sha,
   post_merge_evidence: [full_saved_records]}`. A local merge with no post-merge tasks
   uses an empty record list, without a PR identity. The host refreshes any applicable
   forge-backed local ref before this call; the helper performs no fetch.
3. Call `disposal_decision(authority=authority, observe=fresh_callback,
   session_created=bool)`. It rereads the actual destination ref and named branch tip,
   independently checks the current workspace HEAD, and reports `branch_decision`
   and `workspace_decision`. The top-level status is `eligible` only when both pass;
   callers may act solely on a separately eligible, currently authorized operation.
   Neither API executes deletion. The destination ref must survive branch deletion.
4. A branch decision proves its current local tip integrated through tree comparison.
   A workspace decision separately proves its current HEAD integrated, including the
   safe detached-on-base route. An unintegrated detached HEAD blocks workspace removal
   even when the old named branch is integrated. A trusted `retained_head_ref` may
   instead name a surviving local branch that exactly retains that HEAD; it must
   differ from the branch being deleted. Both proofs additionally require the real
   common Git directory to survive outside the exact workspace removal root (the
   guard's canonical repository root). The helper blocks whole-clone removal when
   common Git storage is inside that root, even with an integrated local destination,
   retained local ref or configured remote. It proves no external clone/publication
   fallback. Branch eligibility remains separate. Before returning, reread the common
   directory boundary and destination/retention identities. Without these proofs,
   keep the workspace and report its removal root and common Git directory.
5. Workspace safety checks index-versus-HEAD, worktree-versus-index, and unmerged
   entries separately. Foreign staged content with a compensating unstaged edit
   still blocks, even when `git diff HEAD` is empty. Untracked/ignored data or a
   workspace this session did not create also blocks workspace removal. Name retained
   resources without printing contents. Decision checks disable Git diff's automatic
   index refresh and verify HEAD, named tip, index and path inventory again before
   returning. A previous eligible result cannot authorize a later changed state.
6. The existing `deletion_decision(journal, authority=CleanupAuthority,
   observe=transfer_callback, branch=branch_name, session_created=bool)` remains
   compatible for transferred-hunk work. It repeats its stronger transfer authority,
   owned-tree integration and saved-evidence guard, then returns the same independent
   branch/workspace results. The transfer journal stays mandatory for duplicate-hunk
   mutation through `apply_cleanup`; it is unnecessary for committed-only disposal.
7. `--auto` supplies no force permission. Never reset a divergent local base; leave
   its commits and report it. Preserve actual pending evidence and ignored/untracked
   artifacts before reconsidering workspace removal. Explicit `discard` retains its
   separately confirmed loss scope; these integration decisions do not authorize or
   execute discard.

For an authorized local merge without post-merge tasks, construct `guard` for a
session-created linked worktree whose common Git storage survives outside its removal
root. The host can then use:

```python
inventory = PostMergeInventory((), "current local task handoff", "no post-merge tasks")
authority = DisposalAuthority(
    repo="<local-repository-identity>", branch="<feature>",
    destination_ref="refs/heads/<base>", allow_branch_delete=True,
    allow_workspace_remove=True, inventory=inventory,
)
result = guard.disposal_decision(
    authority=authority,
    observe=lambda: {"repo": authority.repo, "destination_sha": "<fresh-full-base-SHA>",
                     "post_merge_evidence": []},
    session_created=True,
)
```

Construct the authority and inventory from actual instructions and the current task
host; the example booleans and empty tuple do not grant those permissions or prove
that another project has no post-merge tasks.

Local regression tests use scratch Git repositories and harmless ignored placeholders:

```sh
python3 -m unittest discover -s skills/finalize/scripts -p test_cleanup_guard.py
```
