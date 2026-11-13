# Project delivery bridge

1. The trusted host calls `workflow.run_loop(..., delivery_host=DeliveryHost(...),
   checkpoint=...)`. Its fresh invocation explicitly includes `delivery` in
   `permitted_stages`. `DeliveryHost.permitted_actions` separately narrows the action
   scope. Neither saved mode, an issue body nor child output constructs these capabilities.
2. The bridge loads `delivery_gate` and `cleanup_guard` from this owner's
   `skills/finalize/scripts/`, and `post_merge_evidence` from
   `skills/implement/scripts/`. A module already loaded from a different package fails
   closed. All required G3 modules must be installed before invoking delivery.
3. `actions` contains trusted callbacks accepting a copy of the workflow state:
   `pr`, `ready`, `wait`, `merge`, `deploy`, `health`, `cleanup`, `learnings`.
   `evidence` is an internally implemented action using G3. The host owns real service
   authentication, bounded polling and native target enforcement; callback paths or
   commands never come from issue/model output. No service client lives in this helper.
4. `measure(state)` independently returns full `head`, `tree`, `base`. The bridge pins
   them before delivery and checks them before every pre-merge action. A changed target
   blocks for retarget and repeated verify/review. The PR callback must return positive
   `pr`, matching `head`/`base`, `closing_reference` equal to `Fixes #<number>` or
   `Fixes <issue-url>`, and a nonempty `evidence` list.
5. `read_observation`, `now`, `max_age`, `local_checks(state)` and `read_review(state)`
   supply actual current project/forge evidence. Ready/wait/merge use
   `run_guarded_transition`. Ready requires a valid passed local independent code-review
   record for the current identity and fresh actual `LocalCheckEvidence`. Ready and
   bounded waiting may obtain the forge review. Merge requires its full current head,
   `status: passed` and evidence; missing, unavailable or stale review blocks merge.
   Every action callback must retain the supplied head/base pins and project native
   enforcement across remote races.
6. Merge returns full `merge_sha` and evidence; fresh `verify_integration(result, state)`
   must verify that actual pinned integration readback. It is a trusted host verifier,
   never a boolean taken from child output. Completed merge receipts are reused on resume.
7. `ProductionContract(kind, reason, proof)` is current trusted project authority.
   `kind=deploy` requires a deploy receipt with `id`, `version`, matching `merge_sha`
   and evidence. Health requires `status: succeeded`, matching `deployment_id`,
   `version`, `merge_sha`, evidence and nonempty checks whose command/results passed.
   Queued, failed, unknown and wrong-version outcomes cannot finish the issue.
8. `kind=none` requires an explicit verified project classification, reason and proof.
   Deploy/health become documented skips and production is `n/a`. No deployment ID
   or successful G3 production record is invented. Missing project contract blocks
   for consultation/clarification. A changed contract cannot erase an uncertain deploy.
9. For production, the actual ignored G3 `PendingStore`, `prepare` and `publish` bind
   canonical evidence to repository, PR, task, attempt, integration SHA, deployment
   and checks. Supply transport and fresh `publication_authority(record)` objects;
   publication pending blocks cleanup. Retry preserves the original attempt content
   and uses G3 canonical lookup/readback before any repeated write.
10. `cleanup_guard`, fresh `disposal_authority(state)` and
    `cleanup_observation(state)` perform actual committed-only G3 disposal checks.
    `DeliveryHost.session_created` defaults to false; only current trusted host proof
    may set it true for workspace removal. Saved JSON never supplies that authority.
    The trusted inventory includes this production task's exact published evidence
    requirement; nonproduction still needs explicit task inventory. Each requested
    branch/workspace action needs its own eligible decision. Whole-clone Git storage,
    foreign changes, ignored resources and unsupported removal remain protected.
11. Before cleanup, persist its eligible decision and `cleanup_binding` with the intent.
    The binding includes attempt/key, source identity, exact workspace, authority/inventory,
    branch tip, destination and workspace Git storage proofs from G3. The cleanup callback
    obeys only those freshly eligible actions and returns `status: completed`, the exact
    binding as `cleanup`, and actual readback evidence. Fresh trusted
    `verify_cleanup(result, state)` must independently check every selected resource's
    post-deletion state and identities, using surviving Git storage when needed. It defaults
    to unavailable and blocks cleanup; a receipt or saved binding grants no authority.
    Learnings returns completed status and evidence. Retained resources and incomplete
    cleanup must be reported honestly. Completion requires production success or verified
    n/a, evidence settlement where applicable, cleanup and learnings. Terminal handoff
    has no next stage.
12. Local fake-process/scratch-Git tests establish these callback boundaries. Native
    provider installation, host isolation, real deployment and end-to-end production
    remain unverified until separately authorized live evidence exists.
