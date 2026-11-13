# Workflow-owned consultation routing

1. The workflow host owns the question, approved scope, target identity and aggregation.
   The generic standalone core owns agent selection, read-only transport and persistent
   sessions. Ordinary consultations omit the review adapter binding.
2. Construct `make_consultant(core, host)` only from an explicitly installed/allowlisted
   core and a consultation/read-only HostContext without integration binding. This
   wrapper uses its actual `parse_request`/`dispatch` API; it never searches sibling plugins.
3. `critical_question` with auto attempts every configured family other than the active
   executor once, with the same question/scope/target. For a delegated external executor,
   the main host contributes its own opinion without recursively invoking its own CLI.
   Unknown/unavailable/timeout results remain visible and are never counted as agreement.
4. After bounded attempts, present one question with facts, options, recommendation,
   disagreements and unavailable consultants. Consensus cannot approve a product change.
   Without auto, consultations are optional and do not delay the user's question.
5. A delegated executor, explicit delegated invocation or inherited delegated marker
   returns CONSULTATION_REQUIRED to its main host. It launches no nested cross-agent.
   The main host coordinates responses and resumes the compatible executor session.
6. The current cross-agent TaskContext supplies repository/conversation and canonical
   issue. Its registry remains authoritative for provider/session/task identity. Review
   findings intake uses the separate installed owner adapter and host-generated binding;
   generic consultation does not claim that review adapter supports consultation role.
7. The host must bound and cancel underlying stage/consultation calls. Local fixture
   cancellation proves control flow only, not native process cleanup or OS containment.
8. Each completed response enters history and checkpoint storage before a later
   cancellation check. Cancellation preserves partial responses and starts no new call.
9. After a measured edit, the host's consultation callback rebuilds the generic
   HostContext with the freshly measured current target before calling make_consultant.
   Keep the same verified profile/permissions/session scope; never reuse a stale intake
   identity or accept a provider-supplied replacement. The wrapper's equality check stays strict.
10. Auto consultation records a batch with required/completed/remaining families and
    an in-flight marker saved before each call. The question becomes answerable only
    after the entire batch completes. Interrupted/in-flight batches remain blocked;
    neither run_loop nor critical_question silently resets or retries them.
11. The host uses reconcile_consultation(state, family, response, evidence=[...]) only
    after recovering the actual result or proving a prior call did not start/stopped.
    Evidence is mandatory; these references are host attestations, not OS cleanup proof.
    Unknown outcomes remain blocked. Remaining families require separately authorized
    host attempts and reconciliation; completed families cannot be counted twice.
    answer_question refuses incomplete batches. Retarget archives and clears them.
