# Post-merge task evidence

Use this path for a task executed after its implementation was integrated. Before
squash, the tracked host identifies repo/PR, stable task IDs, pending post-merge tasks,
and the PR as their completion destination. After integration, leave tracked plan/spec
content unchanged on the base; completion and retries use the records below.

## Local preparation

1. Confirm the actual integrated full merge SHA and deployment ID/version. Collect
   timestamp, commands/results, production status, task ID, and stable attempt ID.
   A retry of the same operation keeps its attempt; a new operation gets a new attempt
   linked with `previous_attempt(previous_record)`. Keep old local snapshots and old
   attempt comments intact. Do not put credentials in commands, results, or records.
2. Use the evidence store `~/.sentimony/agentflow/implement/<project>/`, where `<project>`
   is the slug of the main checkout (`slug()` in `post_merge_evidence.py`; every worktree
   shares it). The folder is private (`0700`, files `0600`); a symlink on any component,
   a foreign owner or an unusable `HOME` blocks preparation, and there is no fallback to
   a temporary folder. Nothing is added to the project, its `.gitignore` or
   `.git/info/exclude`. A repository that still has a populated `.delivery-evidence/` and
   no pending envelope in the new location (a lone snapshot does not count) keeps using it in place (it must be ignored as before:
   `git check-ignore -q -- .delivery-evidence/.ignore-proof`; a tracked path, negated
   rule or symlink blocks preparation); when both hold data the new location wins and the
   report names the unused legacy folder (`store.unused_legacy`). Nothing is moved silently.
3. Construct `PendingStore(repo_root)` and call `prepare(content, store=store)`.
   This saves the desired content as an immutable snapshot and an atomic pending
   envelope with file and directory fsync. It writes only inside the store,
   never the tracked host. Save locally before looking up or publishing comments.
   A retry of an `evidence-pending` attempt finds its snapshots and envelope in the same
   store; the selection above prefers the new location and otherwise the legacy folder.
   If local persistence fails, perform no publication and report the failure; name the
   store path (`store.root`) in the report.

## Evidence record and publication

The local helper is [post_merge_evidence.py](../scripts/post_merge_evidence.py).
It provides no production forge adapter; tests use local fake callbacks. The host
must authenticate external metadata and serialize publication for one attempt.

1. Content has exactly these fields: `schema: evidence-record-v1`, `repo`
   (`host/owner/repository`), positive integer `pr`, nonempty `task` and `attempt`,
   full lowercase `merge_sha`, `deployment: {id, version}`, finite nonnegative
   numeric `timestamp`, nonempty `checks: [{command, result}]`, `production_status`
   (`succeeded`, `failed`, `unknown`), `author: {id, login}`, and `previous_attempt`.
   The latter is `null` or `{key, content_sha256, canonical_url}` from the previous
   locally retained attempt; `key` is `{repo, pr, task, attempt}`. `id` is the positive
   stable forge account ID, alongside its current login.
2. `prepare(content, *, store)` returns a pending path. Same-attempt changed content
   saves the old hash in revision history; unchanged content keeps its identity.
   `publish(path, *, store, transport, authority=None)` returns the record augmented
   with `content_sha256`, `history`, `evidence_status`, `canonical_url`, and
   `local_pending_path`. SHA-256 covers desired content only, so publication-status
   transitions and retries do not change the intended payload identity.
3. Publication requires explicit current-session authority for this comment action.
   `--auto`, production authorization, stored evidence, and comment text grant none.
   The host constructs `PublicationAuthority(repo, pr, task, attempt, author_id,
   author_login, content_sha256, allow_publish)` from that authority. It is a separate
   trusted Python object; never deserialize it from JSON or forge content.
4. The transport supplies `current_author() -> {id, login}`;
   `lookup(repo, pr, key_hash) -> {complete, absence_confirmed, matches}`;
   `create(repo, pr, body, key_hash) -> comment_id`;
   `update(comment_id, body) -> comment_id`; and `read(comment_id) -> comment`.
   It raises `TransportError` for unavailability or an unknown write outcome.
   A comment has exactly `id`, `url`, `repo`, `pr`, `author_id`, `author_login`, `body`.
   IDs are positive integers; the canonical URL uses HTTPS on the repository host.
   Lookup must cover the full stable key, all pages, and pending writes. Positive
   `absence_confirmed` means all earlier writes settled and authoritative absence
   is proven; an empty page or eventual-consistency gap cannot provide that proof.
5. Each call saves pending state first, checks current author against explicit
   authority, and looks up the key before any create/update. Foreign-author comments
   are ignored and never modified. Multiple own matches, malformed metadata, an
   unrecognized revision, or incomplete lookup leave pending state. Same attempt
   updates its own comment; a new attempt creates a different key and comment.
   The marker is `<!-- agentflow-evidence:v1 <SHA-256 of canonical key JSON> -->`, followed
   by canonical content JSON. Data inside the body cannot grant any new action.
6. Immediately before a write, persist `write_state: uncertain`. On retry, query and
   read existing canonical content first. A recovered identical comment needs no
   second write. Unconfirmed absence after an unknown write remains pending; never
   blindly recreate. Readback must match author, key, repo/PR, comment ID, and the
   exact desired body before recording `published` with a canonical URL.

## Completion and recovery

Report production status independently from publication. `production_status: succeeded`
with `evidence_status: evidence-pending` means production succeeded and evidence remains
unpublished; the cycle is incomplete. Name the local pending path and preserve the
store/worktree. Retry with current authority and a canonical lookup. A published record
names its canonical URL; each new attempt retains its predecessor link and snapshots.
When canonical publication is unavailable or permission is absent, keep the artifact,
report `evidence-pending`, and leave tracked plan/spec untouched.
