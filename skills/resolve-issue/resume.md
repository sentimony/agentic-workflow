# Delivery recovery

1. Persist workflow state before each delivery action and after its receipt using the
   existing private, atomic, compare-and-swap `workflow.store`. Delivery refuses to run
   without a durable checkpoint. State stores a stable attempt ID, source/base pins,
   action index, results and one in-flight intent with a stable action key.
2. The current stage stays `delivery`; its substep is in the durable delivery state.
   Handoff retains task/issue/mode, current/next stage, workspace, full source identity,
   artifacts, scope, blockers and consultation history. Receipt proofs and integration
   references are appended to artifacts. Saved state never supplies reusable permissions.
3. A fresh manual invocation waits unless `approve_stage='delivery'`; that approval
   authorizes one action, then waits again. A fresh automatic invocation still needs
   explicit delivery stage scope and each action in the current host's permitted set.
   Outstanding product questions, cancellation and round limits remain stops.
4. An intent means the action may already have happened. Call the live trusted
   `reconcile(action, intent, state)` before another attempt. It returns one of:
   `status: completed` with the actual validated `result`; `status: absent` with
   `authoritative: true` and settled lookup `evidence`; or `status: unknown`.
   Unknown/incomplete lookup blocks. A timeout is never proof of absence.
5. Validate recovered PR, integration, deployment, health and cleanup receipts using
   the same identity/proof requirements as a new result. Recover an existing intent
   against its original pins before measuring freshness for a new mutation: successful
   merge may already have advanced the base. After authoritative absence, rerun current
   head/base and action gates before retrying. The independent host verifier checks
   integration readback. Never derive completion from a closed issue or queued merge.
   For completed cleanup, match its saved eligible decision/resource binding against
   current trusted disposal authority and the exact receipt, then require fresh
   `verify_cleanup` post-deletion readback. Pre-deletion eligibility requires resources
   that may now be absent; it runs only for new attempts, never completed recovery.
   A resumed host may supply no cleanup guard for an already removed workspace; its
   current disposal authority and postflight verifier must use the surviving storage.
   Unknown cleanup remains pending and never repeats a mutation without settled absence.
6. Evidence publication uses the existing G3 canonical retry protocol instead of a
   generic publication receipt. After an uncertain write, lookup and readback recover
   the existing comment; they do not create a duplicate or change attempt content.
7. A changed source/base before merge blocks for repeated verification and review.
   Retargeting archives unexecuted delivery progress. An unresolved action intent or
   completed merge must be reconciled under its original identity before changing the
   source target; retarget cannot discard potentially completed external work.
8. Resume cannot reinterpret an uncertain deployment as nonproduction. Its current
   trusted production contract must match the contract already bound to the attempt.
   Preserve partial results on health failure, evidence pending or cleanup failure;
   these outcomes remain incomplete and do not automatically repeat mutations.
9. Terminal replay preserves completed action receipts and performs no repeated
   PR/merge/deploy callbacks. It rechecks the current contract, trusted integration
   readback and saved canonical evidence binding before reporting completion.
