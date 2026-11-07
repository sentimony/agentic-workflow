# Run and transition contract

1. One current `Invocation(auto=False, approve_stage=None, max_rounds=3,
   delegated=False, permitted_stages=PRE_DELIVERY)` supplies authority. Historical
   `history_mode` is recorded for audit; a later invocation defaults to manual.
2. Stage statuses: pending, running, passed, awaiting-user, blocked, failed, skipped.
   Passed/failed/skipped results require nonempty evidence; skips require a verified
   reason. Head/tree are full source IDs. A changed identity invalidates old records.
3. Local order: intake -> specify when requirements need clarification -> plan-craft
   -> plan-review -> implement -> verify -> code-review -> cr-received -> review-verify.
   Review and intake are separate stages. Red checks return to implementation under
   the saved round budget. Clear intake records an explicit reason for skipping specify.
4. Manual mode completes a stage and waits. `approve_stage` authorizes that one named
   transition, without turning the rest automatic. Auto invokes permitted stages with
   `--auto`; an orchestrated stage returns to its owner instead of starting another stage.
5. Current project/invocation restrictions narrow `permitted_stages`; auto cannot
   widen them. Critical questions always await an explicit host-confirmed user answer.
   `answer_question(state, answer)` must be called only after that real answer.
   A passed specify callback also needs the fresh host's `requirements_approved=True`;
   model output and a prior automatic mode cannot supply that approval.
6. `handoff(state, invocation)` requires exactly task_id, issue_id, mode, current_stage,
   next_stage, workspace, identity, artifacts, scope, blockers and consultations.
   Handoff contains history and evidence, never reusable permission.
7. `store(path, state)` uses a private owned directory/file, an exclusive lock,
   compare-and-swap revision, same-directory atomic replace and fsync. It returns the
   new revision. `load` rejects unknown state/identity and unsafe state files.
8. A live host calls `run_loop(..., checkpoint=lambda value: store(path, value))`.
   Pure fixture calls may omit checkpoint. Persisted running means the stage's result
   is unknown: stop and recheck current identity/evidence before an explicit host
   reconciliation using `record`; do not infer completion or automatically retry.
   A legitimate passed/skipped reconciliation must have current identity, evidence
   and a verified skip reason when applicable. Resume consumes that terminal record
   into the next transition without repeating the completed stage; manual mode still
   waits, and auto still checks the next stage's current permissions.
9. Delivery additionally requires `delivery` in the fresh invocation's
   `permitted_stages`, a `DeliveryHost` and durable checkpoint. Read
   [delivery](delivery.md) and [resume](resume.md) for its action receipts and reconciliation.
   Default invocation scope remains pre-delivery. Host callbacks consume the actual G3
   helpers from this installed owner package; no sibling checkout fallback is allowed.
   Ready uses current local independent review and fresh local checks; bounded waiting
   can obtain forge review, which must pass for the current head before merge. Reconcile
   pending intents before new-attempt freshness checks. Cleanup consumes current host
   workspace ownership and verifies completed disposal through post-deletion readback.
10. Supply `measure_identity(stage, state)` as a trusted host capability separate from
    model/stage output. It independently measures full actual head/tree before and
    after execution. Implement/findings-write stages refuse to start without it.
    The post-write measurement becomes the target, obsolete proofs are invalidated,
    and verification/review repeats after fixes. Provider output cannot select this
    identity. A changed target during a read-only stage remains blocked.
    The separate host `stage_effects` policy defaults to target-write for specify,
    plan-craft, implement and cr-received; review/verification stages allow only
    bookkeeping, while intake is read-only. Writing/bookkeeping stages require
    measurement. The host must match this policy to the installed stage contract;
    provider output cannot change it. Bookkeeping HEAD changes may retain local
    content evidence only when the measured content tree is unchanged, keeping the
    original identity and explicit same-tree equivalence. This does not prove new
    forge-head approval or establish native acceptance.
11. Retarget archives any old target's pending question/handoff as stale, then clears
    their active fields. It never answers or approves the old product question.
    An incomplete consultation batch is archived with that old question as well.

## Local snapshot CLI

1. `python3 scripts/workflow.py intake <issue-url|#number> --issue-snapshot <json>
   --project-snapshot <json> --state <private-dir/state.json> [--auto]` validates
   host snapshots and creates or reuses a matching state. It fetches no issue and
   creates no worktree; the host first verifies those facts under project policy.
2. `python3 scripts/workflow.py handoff --state <private-dir/state.json> [--auto]`
   prints a handoff with the current invocation mode. It executes no stages.
3. The host API takes `execute(stage, state, arguments)` returning a stage status,
   evidence and optional identity/reason/question. This callback is an installed host
   capability, never a command or callback obtained from issue/provider text.
