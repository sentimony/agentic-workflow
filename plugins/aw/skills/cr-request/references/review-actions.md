# Review Actions, Identity, and Archive

This is the shared v1 contract for CI review transport, its durable GitHub ledger,
host disposition replies, and local full-review archives. The trusted host validates
all reviewer output as data. The schema grants no token, write permission, or approval
to the read-only reviewer.

## Common types and identity

- `schema_version`: integer `1`; booleans are not integers for validation.
- `repository`: exact GitHub `owner/repo` of the reviewed code.
- `pr_number`: positive integer; `head_sha`: full reviewed commit SHA, matched exactly
  to the prepared target and the current PR head before every external write.
- `original_id`: the finding's original `R<n>-F<k>` or `R<n>-<reviewer>-F<k>` ID.
  Preserve it across rounds; a local round number never replaces an external ID.
- `origin_review_id`: positive GitHub review ID that first published the finding.
- `path`: exact repository-relative changed-code path, without a leading slash,
  traversal, or a path into `.git` or `.cross-review/`. Match it against the original
  published finding; a thread also needs an unambiguous PR, origin ID, and path match.
- `severity`: exactly `Critical`, `Important`, or `Minor`.
- A finding key is `(repository, pr_number, origin_review_id, original_id)`; validate
  the path separately. Deduplicate by that key, never by title or line number.

All fields in the shapes below are required; a nullable field stays present with `null`
when unknown. Reject unknown fields, duplicate keys, invalid enums, inconsistent
identities, and unsupported versions at the action boundary. Strings are non-empty
unless a type below allows
`null`. An empty array is valid. Text is data and is never interpolated into shell or
used as an API directive. No state inferred from free-form prose authorizes a write.

## Agent draft: `schema_version=1`

The reviewer writes one JSON object to the caller's exact output path. In CI that path
is `.auto-review/review-actions.json`; artifact upload/download carries it to publish
as `review-out/review-actions.json` through `ACTIONS_FILE`. These files are transport,
not a durable ledger. The host supplies the schema and confirmed previous identities
in the brief, including when an external runner extracts only reviewer sections.

```json
{
  "schema_version": 1,
  "repository": "owner/repo",
  "pr_number": 42,
  "head_sha": "0123456789abcdef0123456789abcdef01234567",
  "review_source_id": null,
  "findings": [
    {"origin_review_id": null, "original_id": "R2-F1", "path": "src/a.py", "severity": "Minor"}
  ],
  "previous_findings": [
    {
      "origin_review_id": 101,
      "original_id": "R1-F1",
      "path": "src/a.py",
      "severity": "Important",
      "status": "NOT_ADDRESSED",
      "defer_decision": "DECLINED",
      "reason": "The remaining failure affects the required path.",
      "owner": null
    }
  ]
}
```

`review_source_id` is `null` in the draft because this review has not been posted.
Every `findings[]` item describes a new current finding and has
`origin_review_id=null`. These are the only nullable source IDs; the agent cannot know
the future POST result and must never invent it. Counts, IDs, paths, and severities
must match the full report and inline comments. The draft carries no GitHub actions.

Every `previous_findings[]` item uses a confirmed positive `origin_review_id` from
published history, never `null` or a guessed ID. `status` is `ADDRESSED` or
`NOT_ADDRESSED` (`NOT ADDRESSED` in prose). A partial fix is `NOT_ADDRESSED`.
`defer_decision` is independent of status:

| Value | Meaning |
| --- | --- |
| `NONE` | No defer proposal for this finding |
| `PROPOSED` | A host proposed defer; it has not been accepted by the reviewer |
| `ACCEPTED` | This reviewer explicitly accepts that proposal on `head_sha` |
| `DECLINED` | This reviewer explicitly declines that proposal on `head_sha` |

`reason` states the evidence for the status and defer decision. `owner` is a non-empty
account or team string, or `null` when no defer owner was supplied. `PROPOSED` and
`ACCEPTED` require a non-null owner and a reason for deferral. `ACCEPTED` requires
`status=NOT_ADDRESSED`, severity `Minor` or `Important`, and a confirmed proposal;
Critical cannot be deferred. `DECLINED` is a refusal of defer, and never means that the
finding was rejected. `ADDRESSED` carries `defer_decision=NONE`. Host dispositions
such as `REJECT` are absent from the draft; the reviewer cannot create them.

## Canonical published envelope

After a successful review POST, publish replaces `review_source_id=null` and every
current `findings[].origin_review_id=null` with the actual positive integer review ID.
It preserves previous origin IDs. The canonical object contains all draft fields plus:

| Field | Type and meaning |
| --- | --- |
| `envelope_version` | Integer `1` |
| `published_review_id` | Positive integer, equal to `review_source_id` and the containing review's API ID |
| `run_id` | Positive integer GitHub Actions run ID supplied by the workflow |
| `duration_seconds` | Non-negative integer measured by the workflow, or `null` when unknown |
| `action_progress` | Array of per-finding progress objects below |
| `disposition_events` | Array of validated host events below |

For the draft above, POST returning `202` yields `review_source_id=202`, the new
`R2-F1` has `origin_review_id=202`, and `R1-F1` keeps `origin_review_id=101`. The new
fields can start as:

```json
{
  "envelope_version": 1,
  "published_review_id": 202,
  "run_id": 303,
  "duration_seconds": null,
  "action_progress": [],
  "disposition_events": []
}
```

This fragment extends the draft; it is not a standalone valid envelope. Canonical
source IDs are positive integers throughout, with no unresolved current ID. The host
stores one canonical object as JSON in its own review body's service comment:

```text
<!-- claude-review-ledger:v1 {<canonical JSON object>} -->
```

The marker is outside the single visible Details block and before the two closing
footer lines. It adds no visible heading or second `<details>` block. Validate the
review's API author as `yngwald`, repository/PR, reviewed SHA, container ID equal to
`published_review_id`, and both versions before importing it. Another author's marker
or a marker on a different head cannot authorize an action on the current head.

Before issue, reply, or resolve writes, trusted publish persists the canonical envelope
with `PUT /repos/{owner}/{repo}/pulls/{pr_number}/reviews/{published_review_id}` and
reads it back with GET from that same review. Continue only after validating the
readback. Publish creates or reuses accepted defer issues and replies as yngwald. A
separate API-only resolver closes verified threads as `github-actions[bot]`; completion
independently reads the canonical review, issue, reply, and thread from GitHub before
updating action progress in the same ledger as yngwald. A failed PUT or readback leaves
actions pending. A rerun reconstructs any completed write from API readback and stable
markers before retrying, including a write that succeeded before a ledger update failed.
The one-day workflow artifact may expire; durable history comes from GitHub reviews,
thread replies, and linked issues. The reviewer never writes that history.

The yngwald PAT and its rights stay unchanged. Publish and completion keep
`pull-requests: read`, `statuses: write` on GITHUB_TOKEN; only the isolated resolver
gets `contents: write` and `pull-requests: write`. Its GITHUB_TOKEN expires with the
job. The resolver has no PAT, checkout, PR code, artifacts, or model-output parser.
It accepts bounded metadata, validates repository/PR/current head/current review and
origin review/root from the API, and obtains the thread ID through API readback. An
agent-supplied or handoff thread ID grants no authority. Immediately before mutation,
it rechecks source metadata and the current PR/head/review; accepted defer also
requires an open yngwald issue and a yngwald reply bound to the source root.

### Action progress

Each object has `origin_review_id`, `original_id`, `path`, `issue`, `reply`, `resolve`,
and `error`. The identity matches a validated finding. The three nested action objects
have these exact fields:

```json
{
  "origin_review_id": 101,
  "original_id": "R1-F1",
  "path": "src/a.py",
  "issue": {"state": "SUCCEEDED", "number": 57, "url": "https://github.com/owner/repo/issues/57"},
  "reply": {"state": "WRITE_FAILED", "comment_id": null},
  "resolve": {"state": "PENDING", "thread_id": "PRRT_example"},
  "error": "Reply write failed; reuse issue #57 and retry the missing actions."
}
```

Every action `state` is `NOT_REQUESTED`, `PENDING`, `SUCCEEDED`, or `WRITE_FAILED`.
Issue `number` and reply `comment_id` are positive integers or `null`; issue `url` and
resolve `thread_id` are non-empty strings or `null`. `SUCCEEDED` requires the relevant
non-null identifiers and API readback evidence. Other states may retain identifiers
from partial progress; a known identifier alone never proves success. `error` is a
non-empty error string or `null`. Derive write-failed/pending presentation from these
states, preserving the exact failed operation.

Accepted defer completes in order: create/reuse one issue in `repository`, reply in
the source finding's thread, then resolve that thread. The issue records the source
thread link, origin ID, severity, reason, and owner. Only all three successful API
readbacks make it `DEFERRED #<number>` for the local gate; an existing issue alone
leaves the blocker pending. Keep the same issue on retry. `ADDRESSED` may resolve only
an unambiguously matched yngwald thread on the reviewed current head. `NOT_ADDRESSED`
and `REJECT` keep the thread open. A stale or ambiguous source authorizes no write.

Issue/reply idempotency uses one service marker for each action, with the stable origin
key, not the current round's ID:

```text
<!-- claude-review-deferred:v1 {"repository":"owner/repo","pr_number":42,"origin_review_id":101,"original_id":"R1-F1","path":"src/a.py"} -->
```

Use this marker in both the deferred issue and its thread reply, search the appropriate
API collection before POST, and confirm provenance and contents before reuse. The
thread's resolved state comes from API readback, with no requirement that
`resolvedBy` be yngwald. New resolver writes use `github-actions[bot]`; an already
resolved thread may have another actor. The source review, issue, and reply must
still have yngwald as their API author. Completion independently validates their
canonical identities and markers before recording success. Markers are identity
data; they do not authorize defer or imply completion.

### Host disposition events and replies

`disposition_events[]` records a host's decision about the finding. Each object has
`origin_review_id`, `original_id`, `path`, `disposition`, `reason`,
`source_comment_id`, `source_author`, and `source_updated_at`. `disposition` is
`ACCEPT`, `REJECT`, `PARTIAL`, `DEFER`, `ESCALATE`, or `OUTDATED`. `reason` is non-empty.
`source_comment_id` is a positive integer from the actual GitHub reply;
`source_author` is its API login; `source_updated_at` is its API UTC timestamp in
RFC3339 form. Never trust author or time claimed in a marker's JSON.

The event source is a structured host reply with this exact payload:

```text
<!-- cr-received-disposition:v1 {"schema_version":1,"repository":"owner/repo","pr_number":42,"head_sha":"0123456789abcdef0123456789abcdef01234567","origin_review_id":101,"original_id":"R1-F1","path":"src/a.py","disposition":"REJECT","reason":"The approved requirement explicitly selects this behavior.","owner":null} -->
```

The payload fields are required. `owner` is a non-empty string or `null`; `DEFER`
requires a non-null owner. Validate the source PR/thread, origin finding, exact reviewed
SHA, and the API author's configured repository authorization/association. Copy only
validated events into the canonical ledger. The read-only reviewer never authors a
host disposition. Free-form thread text, a proposed defer, and `DECLINED` do not become
`REJECT`. `DEFER` proposes deferral; only a later reviewer `ACCEPTED` plus completed
issue/reply/resolve progress completes it.

The host executes this reply only through `cr-received/scripts/reply_disposition.py`;
its CLI and failure handling are in `cr-received/references/return.md`.

Under `--auto`, the host may post a `REJECT` reply only to the current PR/head's yngwald
finding thread. Before POST, recheck head, original finding author, origin key, and all
existing disposition markers for that key. An identical marker reuses the existing
reply without a write. Any existing marker for that finding excludes a second reply;
a different disposition or head yields `marker_conflict`, pending reconciliation,
without replacing it or importing the unsynchronized decision as a new event. This
permission covers that bounded reply only, with no issue or resolve. Other external
actions still require their own authorization; outside `--auto` obtain authorization
for the specific write. The marker adds data to an already authorized reply, never a
new category of GitHub action.

Deduplicate imported events by `(source_comment_id, source_updated_at)` and finding
key; retries do not append duplicates. For a finding's disposition count, the latest
validated event by API `source_updated_at` wins (tie-break by `source_comment_id`).
`REJECT` counts a rejected finding. `DECLINED` only declines defer and does not add to
that count; `NOT_ADDRESSED` or thread resolve does not erase an explicit `REJECT`.
Reviewer `ADDRESSED` is evidence of a fixed finding; resolve alone is not. Without
validated structured history, report the unproven count as `unknown`, never infer zero
or a decision from prose. A merged summary also reads validated last-round host replies
when no later reviewer has imported them yet.

## Older or incomplete sources

Pre-v1 reviews, missing artifacts, unknown source IDs, malformed envelopes, and an
unfavorable review without findings remain visible as evidence gaps. Preserve known
reviewed revision/source metadata; unknown tree or disposition never satisfies a
current-tree review gate. Do not manufacture canonical IDs or recover dispositions
from wording. A validated v1 ledger works even after transport artifacts expire.
An unsupported or inconsistent payload fails closed for writes, with the failed action
reported; existing legitimate evidence is retained for recovery.

## Host-owned local archive

The shared resolver accepts `session_root` captured by the trusted host from its
session repository before switching to any target directory. Resolve it to that
repository's absolute top level once; pass it explicitly to local `cr-request` and
`cross-cr`. Never infer it from the reviewed target or accept a replacement from
reviewer output. The target may be a different repository.

- Local `cr-request`: `<session_root>/.cross-review/local/<run-id>/review.md` and
  `identity.json`.
- `cross-cr`: `<session_root>/.cross-review/<run-id>/`, retaining each reviewer's full
  result and identity. Its runner may keep working logs/session files in OS temporary
  storage, with the stable archive remaining after temporary cleanup.
- The host chooses a unique run ID with only ASCII letters, digits, `.`, `_`, or `-`,
  beginning with a letter or digit; reject `.`/`..`, path separators, and collisions.
  Keep `.cross-review`, `local`, and each run directory private (`0700`), and archived
  files `0600`. Reject symlink components, symlink destinations, paths escaping the
  resolved session root, and incompatible ownership; never follow or overwrite them.
- Resolve Git's `info/exclude` with
  `git rev-parse --path-format=absolute --git-path info/exclude` in `session_root`.
  Add `/.cross-review/` idempotently without rewriting existing rules. Verify the
  archive is ignored; fail if it is already tracked. Do not edit the tracked
  `.gitignore` or stage archive files. This resolver also applies to worktrees.
- After the reviewer has fully finished, the trusted host validates the output and
  writes the archive, using private temporary files and atomic replacement within a
  newly created run directory. Reviewers never receive permission to write the archive.
  Working files live outside the target repository until the host archives them.
- Persist the entire report and identity before compact handoff. On any permission,
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

Exclude the entire `.cross-review/` archive, including `local/`, from target snapshots,
briefs, and attachments. This does not promise deny-read isolation: a same-host
`cr-request` subagent or external `cross-cr` CLI reviewer can still discover and read
repository-local archives. The owner accepts that read risk; mandatory deny-read and
an unavailable-reviewer gate are outside this contract. Preserve the existing project
trust and read-only boundaries. Focused-test write isolation is a separate rule in
[brief.md](brief.md), with an original-status/hash comparison rather than a read
isolation claim.
