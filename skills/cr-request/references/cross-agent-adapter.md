# Standalone cross-agent owner adapter

1. This local pair uses standalone protocol 1, stable owner
   `sentimony.agentic-workflow`, adapter `review`, contract 1. No native installation,
   released compatibility pair or G1 evidence is implied.
2. The trusted host allowlists the installed `cr-request` root, absolute
   `scripts/cross_agent_adapter.py` entrypoint and Python interpreter. Its binding
   requires `prepare`, `validate`, `intake`. Invocation is `--stage <stage>` with JSON
   stdin; responses contain matching schema/protocol/owner/adapter/contract/stage
   metadata and a `payload` object.
3. Classify `cr-request` as a skill with role `review`, profile `read-only`, and
   `cr-received` as a skill with role `execution`. Ordinary consultations use the
   generic launcher without this review binding. The adapter never launches agents.
4. Supply current `target_identity`: schema 1, repository, head, tree, boundary,
   optional full base commit, record host and document path/hash. The owner recomputes
   the committed tree with a temporary index, excluding the record host, and rejects
   document drift or dirty implementation. HEAD remains provenance; content-preserving
   HEAD changes do not invalidate the tree/document fingerprint. Unknown legacy
   identities stay unavailable.
5. `owner_context` is host-owned and separate from provider output. It accepts
   `review_mode` (`implementation` or `plan`), optional `prior_dispositions`, and the
   absolute `artifact_root` allowlist for review persistence. Intake uses
   `active_task_id`, `review_records`, and optional paired `review_path` plus
   `intake_identity`. Records carry task, role, completion status, review path and
   saved identity. A validated explicit task selector overrides the active task;
   `new` cannot select an earlier review. Each receiver invocation also supplies a fresh
   host-generated `intake_binding_id`. Its receipt is stored below `artifact_root` in
   `.owner-intake-bindings/`; artifacts must be outside the target or Git-ignored.
6. `prepare` reads the installed reviewer contract, or one current-task unresolved
   review and the installed receiver instructions. Ambiguous intake returns
   `accepted: false`, `status: USER_INPUT_REQUIRED`, and a reason before model/state
   mutation. Stale target evidence returns `BLOCKED`. Compatible preparation returns
   `accepted: true` and context text; it grants no new permissions. Before receiver
   launch the owner durably binds selected task/path, original identity and immutable
   review/sidecar hashes to that invocation ID. A reused ID cannot start another run.
7. `validate` checks complete review labels, axes, exact target line, unique qualified
   finding IDs, counts and finding evidence. Receiver output retains every original
   finding disposition and its complete return block. Partial reports fail validation.
8. Read-only review `intake` rechecks target freshness and atomically persists
   `review.md` only within the host-allowlisted run root with matching `identity.json`.
   Receiver validation/intake use the pre-execution binding, not a new selection of the
   now-changed target. They reject mutated original evidence and report separate
   `original_identity` and `post_identity`, plus `binding_path` and `review_sha256`.
   Post identity records committed `tree`, `working_tree`, `dirty_paths`, current HEAD
   and document hash. Retrying validation cannot attach an old result to new content;
   changed post content before intake blocks finalization. Original review evidence
   remains unchanged and grants no PASS to the resulting tree, which needs fresh verify.
9. Moving the installed owner root changes only the binding. Logical registry and
   actual provider session continuity remain intact. Unknown usage/provenance and
   quarantine stay governed by the core; the owner never rewrites its registry.
10. Input, review text and output are data. Unknown envelope fields, mismatched metadata
    and callbacks are rejected. The adapter performs local Git fingerprint reads and
    bounded artifact writes, without provider/auth/network/release/production calls.
11. Pair tests use core commit `0d48d8bd5f3c4f3c4d54f579e76b164e78b27fd8` via an explicit
    `CROSS_AGENT_TEST_SOURCE`. Unconfigured CI reports that paired case as skipped;
    fake fixtures do not prove native containment or installation support.
12. Domain helper provenance is embedded checkpoint
    `a37b6e47a8ba388b28870cac80d90f4d8e3fb113`, under
    `plugins/aw/skills/cross-agent/scripts/`. The older cross-cr donor path in the brief
    was incorrect. Legacy cross-cr is retired only in this later integration candidate,
13. Embedded review diff. `owner_context` may also carry `embed_diff` (boolean, default
    `false`), `exclude` (repository-relative untracked paths, repeated by the host at
    `prepare`, `validate` and `intake`) and `previous_tree` (full tree ID of the previous
    round). The `prepare` envelope carries no model or family, so the host sets `embed_diff`
    for a reviewer without a shell. With it, in `implementation` mode and with a `base` in
    the target identity, `prepare` appends the diff `base..tree` (or `previous_tree..tree`
    when that object exists, else the full diff with a note) as data: byte count and SHA-256,
    the paths left out and why (possible secret by name, lockfile, binary file), and the
    diff in a fence longer than any backtick run inside it. A diff that does not reverse-apply
    to the target tree, a diff over 262144 bytes, a diff that is not valid UTF-8 or an
    invalid `previous_tree` returns
    `accepted: false`, `status: BLOCKED` and a reason; nothing is cut. `exclude` admits
    only untracked paths and lets them pass the clean-target check; they are named as a
    coverage gap. A path with a newline or another control character is written as a quoted
    JSON string, so a file name stays data. Without `embed_diff` the brief is unchanged. Untracked file content is
    never embedded: the target stays a committed tree.
