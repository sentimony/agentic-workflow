# AGENTS.md

## Layout

- `plugin.json` - the full manifest: it carries `skills: "./skills/"` and the Codex `interface` under `extensions.com.openai`. A hidden manifest exists only for a host listed in `KEPT_HIDDEN` of `scripts/check_plugin_layout.py`.
- `skills/<skill>/` - `SKILL.md`, `CHANGELOG.md`, `LICENSE`, `references/`.
- `.github/workflows/ci.yml` - metadata, manifests, Unicode, and review-helper validation.
  The caller delegates to
  `sentimony/github-workflows/.github/workflows/auto-reviewer-shared.yaml@v0.0.5`
  using the `validate` CI job adapter. The tag must be published before this consumer
  merges; see README's Review operations for the release order.
  The shared workflow owns the engine and its tests;
  local `scripts/test_auto_reviewer.py` checks the caller contract. Run it with
  `python3 -m unittest discover -s scripts -p 'test_auto_reviewer.py'`.

  Repository variables configure the review: `CLAUDE_REVIEW_MODEL` defaults to
  `claude-sonnet-5-5`, `CLAUDE_REVIEW_EFFORT` to `medium`, and
  `CLAUDE_REVIEW_MAX_ROUNDS` to 10 when empty. Invalid values fail before inference.
  `REVIEW_SKILLS_REF` can pin a full SHA instead of the latest released `cr-request`.
  One `auto-review-rounds-N` label overrides the configured round limit; malformed or
  multiple labels fail validation. An explicit yngwald request or dispatch bypasses the
  count while retaining the other guards. The count includes manual reviews. CI
  eligibility uses a successful push or workflow_dispatch run on the full head SHA.
  Automatic triggers start the first review of an eligible PR; repeats require a new
  head and new or unresolved prior Critical or Important findings. The shared schema
  and transport retain compatibility with older released
  skills; changing the pin does not bypass the compatibility check.

## Rules

- New skill: place it in root `skills/`; frontmatter `name` equals the directory.
  The root `plugin.json` is the full manifest: it carries `skills: "./skills/"` and the Codex `interface` under `extensions.com.openai`. A hidden manifest exists only for a host listed in `KEPT_HIDDEN` of `scripts/check_plugin_layout.py`; keep its name/version equal to the root.
- Versions: patch bumps; manifest `version` equals the release tag without `v`; the top
  `CHANGELOG.md` entry matches `metadata.version`. README shows the repository
  version, each plugin version, and each skill version.
- No marketplace of its own: the `agentflow` entry lives in sentimony/marketplace (both
  `marketplace.json` files), and CI fails if `.claude-plugin/marketplace.json` or
  `.agents/plugins/marketplace.json` comes back. After a release tag, bump that entry's `ref`
  with a sentimony/marketplace patch release.
- Releases go through the `rc-verifier` and `releaser` roles (contracts and the release
  checklist in the `skills-aiassist` workbench): `rc-verifier` approves the tree, then
  `releaser` commits, squash-merges the PR, and pushes the annotated tag.
- `auto-reviewer.yaml` changes in a PR reach `workflow_run` only after merge (it uses the default
  branch copy); `pull_request` runs use the PR branch copy. `.auto-reviewer/` is reserved for the
  review job and must not be tracked.
  To test a changed workflow on its own PR, push, wait for green CI, then open the PR or request
  yngwald: on the first head the `main` copy's `workflow_run` shares the review job's per-PR
  group and can cancel the PR copy's review. The `workflow_run` run carries the `main` head SHA,
  not the PR head: wait for `gh run list --commit <full head SHA> --workflow CI` and then for
  `gh run list --event workflow_run --limit 1` to complete before requesting yngwald. The
  `/cr-request` version in the review footer shows which workflow copy posted it.
- The shared workflow keeps one run per head SHA (workflow-level concurrency), so automatic
  runs for one head no longer race, and a late CI run for an older head cannot cancel the review
  of a newer one; the review job's per-PR group lets a newer head's review cancel an older one,
  which publish reports as superseded. A `workflow_dispatch` run and an event-driven run for the
  same head meet only in that job group, so one review cancels the other and the head can end
  with an `error` status and no review: an accepted trade-off, not a defect for review;
  re-requesting yngwald recovers, and the status is advisory.
- A review run that fails with `is_error: true` after a few turns and the log line "You've hit
  your session limit · resets <time>" hit the OAuth usage limit: re-request yngwald after that
  time instead of changing the workflow.
- The `publish` footer check accepts the signature with the measured duration followed by a
  `Next step` line in its full format, and the pre-0.0.6 order with the signature last. The
  posted review drops the reason after ` · ` from the `Next step` line, on the owner's
  choice: an accepted trade-off, not a defect for review. The chain form
  (``Next step: `/verify <plan>` -> `/finalize` squash``) and the findings form
  (`` Next step: `/cr-received PR #<n>` ``) carry no reason and stay whole.
  The shared repository tests the engine, including footer grammar, gates, ledgers,
  recovery, and merged summaries. Local tests check the caller contract.
  CI validates both review helpers:

  1. `python3 -m unittest discover -s skills/cr-received/scripts -p 'test_*.py'`
  2. `python3 -m unittest discover -s skills/cr-request/scripts -p 'test_*.py'`

  Paired owner/core tests require an explicit `CROSS_AGENT_TEST_SOURCE`; without one
  CI reports that case skipped and makes no compatibility-pair claim.
- The reviewer writes `review-actions.json` without a write PAT. Trusted publish
  validates its schema, identities, current PR head, and yngwald token ownership, then
  persists a `claude-review-ledger:v1` envelope in the review body with PUT/GET readback
  before actions. Review artifacts are temporary transport; the ledger is the durable
  source. Publishing reviews/replies needs Pull requests RW; accepted defer issues need
  Issues RW on the selected repository and organization approval. The yngwald PAT and
  its rights stay unchanged; yngwald authors reviews, issues, replies, ledgers, and
  merged summaries. Only the API-only `resolve_threads` job gets `contents: write` and
  `pull-requests: write` on GITHUB_TOKEN, which expires with the job; it resolves as
  `github-actions[bot]`. This is an accepted trade-off, not a defect for review: a
  long-lived Contents-write PAT would risk pushes to main. The job still has
  content-write power during its lifetime, so it has no PAT, checkout, PR code,
  artifacts, or model-output parser. It obtains thread IDs from GitHub metadata after
  checking the current PR/head/review and origin/root; accepted defer also requires
  fresh open-issue and root-bound reply metadata. Publish and completion keep
  `pull-requests: read`, `statuses: write` on GITHUB_TOKEN. Completion independently
  reads canonical, issue, reply, and thread evidence from the API before recording
  success. Resolve readback accepts earlier actors too, without a
  `resolvedBy == yngwald` requirement; source review, issue, and reply authors stay
  yngwald. Do not infer write access from a successful metadata GET or widen token
  rights automatically. Deferred work counts as complete only after issue, reply, and
  resolve readback; retries recover recorded progress instead of duplicating writes. The
  host's bounded REJECT helper reuses an identical disposition marker and stops on a
  changed marker for an owner ruling.
- REJECT and fully confirmed accepted deferrals stop blocking automatic rounds. Accepted
  deferrals are bound to the snapshot prepared before inference; a proposal changed after that
  snapshot stops the action. The publish finalizer ends only its own pending status after a
  failure and leaves a newer run's status alone.
- The merged-only summary reads GitHub history without checkout or inference, validates
  yngwald ledgers and source markers, and updates one own summary comment. REJECT counts
  rejected findings; DECLINED defer does not. Later structured evidence determines each
  finding's bucket; missing legacy evidence or duration stays unknown. Closed unmerged PRs
  and PRs without yngwald reviews produce no summary. Its concurrency is separate from review.
1. A hostless ready PR requires fresh project checks on its current committed target,
   with commands/results in the report and PR body; undefined or unavailable checks
   require draft/clarification. Ready uses fresh local verification; remote jobs may
   start after ready. Unknown merge policy remains unknown, and merge still requires
   every applicable check. No tracked host is created solely for this gate.
   This supersedes the old exemption for ready PRs only. Other hostless integration
   semantics remain an accepted trade-off, not a defect for review, because the
   approved delivery scope revises ready verification without redesigning those routes.
2. Delivery contracts live in `skills/finalize/references/squash.md`,
   `skills/implement/references/post-merge.md` and
   `skills/finalize/references/cleanup.md`. Read the applicable contract before ready,
   merge, post-merge evidence or cleanup. Canonical completion uses an authorized own
   PR comment with readback; unavailable publication remains evidence-pending in a
   private store under `~/.sentimony`. Post-merge tasks leave tracked plan/spec files on the base
   unchanged. `PendingStore` checks paths before use rather than through directory descriptors; a
   same-user process could swap a component in between. This is an accepted trade-off, not a defect
   for review: the store is a private 0700 directory outside the project, one trusted host
   serializes it, and a `dir_fd` redesign risks the evidence flow.
   Removing transferred duplicate hunks requires the captured ownership journal and
   canonical evidence. Branch/workspace disposal is separate: require current user
   authority, current branch/workspace integration or retention and data guards, plus
   an explicit trusted inventory of post-merge tasks. An explicit no-task inventory
   makes evidence not applicable; committed-only/local merges need no fabricated
   patch, PR or deployment. Unknown inventory or actual tasks with pending evidence
   block disposal. Preserve foreign staging and all local data; auto supplies no force.
   The helper conservatively blocks whole-clone removal when its common Git storage
   is inside the removal root. Linked-worktree removal requires proof that common Git
   storage and retaining refs survive outside that root; a local ref alone is no proof.
3. After delivery changes run the nonempty suites in CI's `Test delivery helpers`:
   `python3 -m unittest discover -s skills/verify/scripts -p test_dependency_isolation.py`,
   `python3 -m unittest discover -s skills/finalize/scripts -p test_delivery_gate.py`,
   `python3 -m unittest discover -s skills/finalize/scripts -p test_cleanup_guard.py`,
   `python3 -m unittest discover -s skills/implement/scripts -p test_post_merge_evidence.py`,
   and `python3 -m unittest discover -s scripts -p test_delivery_integration.py`.
   The actual CI step rejects zero discovered tests for each suite. Offline fixtures
   do not prove production adapters, live forge actions, deployment or native evals.
- `finalize` advises `pr --draft` for a `working` verdict although a draft carries only
  committed work: the uncommitted paths are listed as not integrated, and committing them is
  the user's call under the commit policy. This is an accepted trade-off, not a defect for
  review.
- Renaming a released skill: the new name starts at `0.0.1`, its CHANGELOG names the old one,
  and README Install says to remove the old skill or reinstall.
1. `resolve-issue` owns issue orchestration. Stage skills remain usable standalone.
   Without auto, finish a meaningful stage and ask for the next transition. With auto,
   continue within current verified authority and pass the flag to every invoked skill.
   An orchestrated stage returns evidence/next action to its owner rather than launching
   another stage itself. Historical mode never restores permission in a new session.
   Critical product decisions, Round rule, quality gates and explicit bans remain.
   Configured delivery uses the installed G3 host bridge, fresh action authority and
   verified project contracts; unknown contracts block their actions. Native/full
   production acceptance remains unverified by synthetic tests. The installed review
   adapter remains owner of review policy; ordinary consultations use the generic core.
- agentflow skills replace their sentimony/skills devflow counterparts (scope-triage,
  plan-crafting, plan-execution, plan-orchestration, verification-gate, branch-finish,
  review-request, review-resolution, cross-review): a description opens with
  `You MUST use this when`, as devflow's do, and names the skill it replaces.
1. The installed cross-agent owner adapter reads its own `brief.md` and `lenses.md`
   headings. Keep Reviewer instructions, Result contract, Severity, Intent, System
   and Craft stable; after edits run the owner adapter fixture suite. The host-only
   closing-line rules after the Not checkable paragraph stay outside reviewer context.
2. A delegated CLI reviewer and same-host subagent can read local review archives
   despite snapshot exclusion: an accepted trade-off, not a defect for review,
   because stronger OS containment remains a separate design.

1. Generic cr-request review output belongs to the skill. Auto Reviewer presentation,
  footer validation, transport, and their fixtures belong to `sentimony/github-workflows`;
  preserve compatibility with the generic review result when changing either contract.
- A review fix that rewords a skill's `SKILL.md` also updates the same wording in that skill's
  unreleased top `CHANGELOG.md` entry, in the same commit.
- License: MIT, Ihor Orlovskyi.
- Branches: `YYMMDD-dev-session`, squash-merged into `main` via PR.
- English only, plain hyphen.
