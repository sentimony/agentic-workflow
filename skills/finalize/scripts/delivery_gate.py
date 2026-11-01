"""Gate evaluation and guarded callbacks, with no built-in transport or waiting.

Adapters must authenticate sources and enumerate effective policy/checks. Structural
validation cannot authenticate a forge response. OwnerDecision is trusted caller
authority from this invocation, never a value decoded from observations.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re


SAFE_CONCLUSIONS = {"success", "skipped", "neutral"}
RED_CONCLUSIONS = {"failure", "cancelled", "timed_out", "action_required", "stale", "startup_failure", "error"}
MERGE_STATES = {"CLEAN", "HAS_HOOKS", "UNKNOWN", "UNSTABLE", "BLOCKED", "DIRTY", "BEHIND", "DRAFT"}


@dataclass(frozen=True)
class OwnerDecision:
    """Trusted host decision to continue unknown policy through the native gate."""

    head: str
    base: str
    observation_id: str
    decision_id: str
    reason: str
    allow_unknown_policy: bool
    bypass: bool


def _require(condition, field):
    if not condition:
        raise ValueError("invalid " + field)


def _object(value, keys, field):
    _require(type(value) is dict and set(value) == set(keys.split()), field)


def _text(value, field):
    _require(type(value) is str and bool(value.strip()) and len(value) <= 4096
             and not any(ord(c) < 32 for c in value), field)


def _sha(value, field):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is not None, field)


def _time(value, field):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    _require(valid, field)


def _requirements(items, field):
    _require(type(items) is list, field)
    ids = set()
    for item in items:
        _object(item, "id accepted semantics_source", field)
        _text(item["id"], field + ".id")
        _text(item["semantics_source"], field + ".semantics_source")
        accepted = item["accepted"]
        _require(type(accepted) is list and bool(accepted)
                 and all(type(c) is str for c in accepted), field + ".accepted")
        _require(len(set(accepted)) == len(accepted)
                 and set(accepted) <= SAFE_CONCLUSIONS, field + ".accepted")
        _require(item["id"] not in ids, field + ".duplicate")
        ids.add(item["id"])


def _validate(obs, current):
    _object(obs, "schema head base observed_at deadline policy project_checks checks mergeability native_gate", "observation")
    _require(obs["schema"] == "gate-observation-v1", "schema")
    for key in ("head", "base"):
        _sha(obs[key], key)
    _require(len(obs["head"]) == len(obs["base"]), "object-format")
    for key in ("observed_at", "deadline"):
        _time(obs[key], key)
    _require(obs["observed_at"] <= current and obs["deadline"] > obs["observed_at"], "observation time range")
    policy = obs["policy"]
    _object(policy, "source retrieval coverage coverage_evidence absence_proof required", "policy")
    _text(policy["source"], "policy.source")
    _require(policy["retrieval"] in ("ok", "denied", "not-found", "error"), "policy.retrieval")
    _require(policy["coverage"] in ("complete", "incomplete"), "policy.coverage")
    _text(policy["coverage_evidence"], "policy.coverage_evidence")
    if policy["absence_proof"] is not None:
        _text(policy["absence_proof"], "policy.absence_proof")
    _requirements(policy["required"], "policy.required")
    _require(not (policy["required"] and policy["absence_proof"] is not None),
             "contradictory policy absence proof")
    _requirements(obs["project_checks"], "project_checks")
    checks = obs["checks"]
    _object(checks, "source head complete items", "checks")
    _text(checks["source"], "checks.source")
    _sha(checks["head"], "checks.head")
    _require(type(checks["complete"]) is bool and type(checks["items"]) is list, "checks snapshot")
    ids = set()
    for check in checks["items"]:
        _object(check, "id head status conclusion", "check")
        _text(check["id"], "check.id")
        _sha(check["head"], "check.head")
        _require(check["id"] not in ids, "check.duplicate")
        ids.add(check["id"])
        _require(check["status"] in ("pending", "completed"), "check.status")
        conclusion = check["conclusion"]
        _require(conclusion is None or (type(conclusion) is str
                 and conclusion in SAFE_CONCLUSIONS | RED_CONCLUSIONS), "check.conclusion")
        _require((check["status"] == "pending") == (conclusion is None), "check status/conclusion")
    merge = obs["mergeability"]
    _object(merge, "source head base state", "mergeability")
    _text(merge["source"], "mergeability.source")
    _sha(merge["head"], "mergeability.head")
    _sha(merge["base"], "mergeability.base")
    _require(type(merge["state"]) is str and merge["state"] in MERGE_STATES, "mergeability.state")
    native = obs["native_gate"]
    if native is not None:
        _object(native, "source head base state bypass", "native_gate")
        _text(native["source"], "native_gate.source")
        _sha(native["head"], "native_gate.head")
        _sha(native["base"], "native_gate.base")
        _require(native["state"] in ("passed", "blocked", "unknown"), "native_gate.state")
        _require(type(native["bypass"]) is bool, "native_gate.bypass")


def observation_id(observation):
    """Identity of evidence, independent of the time a fresh read acquired it."""
    evidence = {key: value for key, value in observation.items() if key != "observed_at"}
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate(observation, *, now, owner_decision=None):
    """Evaluate one snapshot; blocked snapshots must be refreshed before deadline.

    `now` is an injected zero-argument clock using the observation's time scale.
    Malformed data raises ValueError; well-formed insufficient evidence blocks.
    """
    current = now()
    _time(current, "now")
    obs = deepcopy(observation)
    _validate(obs, current)
    identity = observation_id(obs)
    if owner_decision is not None:
        _require(type(owner_decision) is OwnerDecision, "owner_decision authority")
        for key in ("decision_id", "reason", "observation_id"):
            _text(getattr(owner_decision, key), "owner_decision." + key)
        _sha(owner_decision.head, "owner_decision.head")
        _sha(owner_decision.base, "owner_decision.base")
        _require(type(owner_decision.allow_unknown_policy) is bool
                 and type(owner_decision.bypass) is bool, "owner_decision flags")
    policy = obs["policy"]
    complete = policy["retrieval"] == "ok" and policy["coverage"] == "complete"
    state = "unknown"
    if complete and policy["required"]:
        state = "known-required"
    elif complete and policy["absence_proof"] is not None:
        state = "known-none"
    reasons = []
    failures = []
    if current >= obs["deadline"]:
        reasons.append("deadline-expired")
    checks = obs["checks"]
    if checks["head"] != obs["head"]:
        reasons.append("checks-head-changed")
    if not checks["complete"]:
        reasons.append("checks-incomplete")
    requirements = {}
    # A project convention cannot loosen a forge requirement with the same ID.
    for requirement in obs["project_checks"] + policy["required"]:
        key = requirement["id"]
        accepted = set(requirement["accepted"])
        requirements[key] = requirements.get(key, accepted) & accepted
    observed = {}
    for check in checks["items"]:
        if check["head"] != obs["head"]:
            reasons.append("stale-check:" + check["id"])
            continue
        observed[check["id"]] = check
        if check["status"] == "pending":
            reasons.append("pending-check:" + check["id"])
        elif check["conclusion"] in RED_CONCLUSIONS:
            failures.append("red-check:" + check["id"])
        elif check["conclusion"] not in requirements.get(check["id"], {"success"}):
            reasons.append("unaccepted-conclusion:" + check["id"])
    for key in requirements:
        if key not in observed:
            reasons.append("missing-check:" + key)
    merge = obs["mergeability"]
    if (merge["head"], merge["base"]) != (obs["head"], obs["base"]):
        reasons.append("mergeability-identity-changed")
    if merge["state"] not in ("CLEAN", "HAS_HOOKS"):
        reasons.append("mergeability:" + merge["state"])
    native = obs["native_gate"]
    native_positive = False
    if native is not None:
        if (native["head"], native["base"]) != (obs["head"], obs["base"]):
            reasons.append("native-gate-identity-changed")
        elif native["bypass"] or native["state"] != "passed":
            reasons.append("native-gate:" + native["state"])
        else:
            native_positive = True
    owner_positive = (owner_decision is not None
                      and owner_decision.allow_unknown_policy and not owner_decision.bypass
                      and (owner_decision.head, owner_decision.base, owner_decision.observation_id)
                      == (obs["head"], obs["base"], identity))
    if state == "unknown" and not (native_positive or owner_positive):
        reasons.append("policy-unknown")
    result = "failed" if failures else "blocked" if reasons else "passed"
    return {
        "schema": "gate-record-v1", "policy_state": state,
        "policy_source": policy["source"], "policy_coverage": policy["coverage"],
        "head": obs["head"], "base": obs["base"], "deadline": obs["deadline"],
        "observed_at": obs["observed_at"], "evaluated_at": current,
        "required_checks": deepcopy(policy["required"]),
        "project_checks": deepcopy(obs["project_checks"]),
        "observed_checks": deepcopy(checks["items"]),
        "mergeability": deepcopy(merge), "observation_id": identity,
        "observation": obs, "result": result, "reasons": failures + reasons,
        "unknown_policy_basis": "native-gate" if state == "unknown" and native_positive
        else "owner-decision" if state == "unknown" and owner_positive else None,
        "owner_decision_id": owner_decision.decision_id if owner_positive else None,
    }


def _ready_eligible(record):
    """Outstanding remote jobs/policy do not make a local ready transition a merge."""
    if record.get("result") == "failed":
        return False
    state = record["mergeability"]["state"]
    pending = any(r.startswith(("missing-check:", "pending-check:"))
                  for r in record["reasons"])
    if state not in {"CLEAN", "HAS_HOOKS", "DRAFT"} and not (
            state in {"BLOCKED", "UNSTABLE"} and pending):
        return False
    return all(r.startswith(("missing-check:", "pending-check:"))
               or r in {"policy-unknown", "mergeability:" + state}
               for r in record["reasons"])


def _fresh(record, *, observation, now, max_age, owner_decision=None, readiness=False):
    """Re-evaluate exact evidence; changed policy/checks/base invalidate readiness.

    Callers must supply a newly authenticated observation at ready/merge boundaries.
    The predicate cannot discover remote changes without that adapter read.
    """
    try:
        _time(max_age, "max_age")
        current = now()
        _time(current, "now")
        if type(record) is not dict or record.get("schema") != "gate-record-v1":
            return False
        fresh = evaluate(observation, now=lambda: current, owner_decision=owner_decision)
        def acceptable(result):
            return _ready_eligible(result) if readiness else result.get("result") == "passed"
        if not acceptable(fresh):
            return False
        _time(record["evaluated_at"], "evaluated_at")
        # Every stored evidence/result field is re-derived, never trusted from JSON.
        original = evaluate(record["observation"], now=lambda: record["evaluated_at"],
                            owner_decision=owner_decision)
        return (record == original and acceptable(original)
                and record["observation_id"] == fresh["observation_id"]
                and record["evaluated_at"] <= current
                and current - record["observed_at"] <= max_age
                and current - observation["observed_at"] <= max_age)
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def is_fresh(record, *, observation, now, max_age, owner_decision=None):
    """Validate merge evidence against a fresh authenticated adapter observation."""
    return _fresh(record, observation=observation, now=now, max_age=max_age,
                  owner_decision=owner_decision)


def is_ready(record, *, observation, now, max_age, owner_decision=None):
    """Fresh readiness observations only; the transition also requires local checks.

    Remote jobs may still be missing/pending and policy may remain unknown. This
    predicate never changes a gate-record result into passed or authorizes merge.
    """
    return _fresh(record, observation=observation, now=now, max_age=max_age,
                  owner_decision=owner_decision, readiness=True)


class TransitionBlocked(ValueError):
    """The requested transition needs new evidence, checks, or a target decision."""


@dataclass(frozen=True)
class LocalCheckEvidence:
    """Trusted host result of isolated project checks, never decoded forge content."""

    head: str
    base: str
    tree: str
    commands: tuple
    checked_at: float
    defined: bool
    available: bool
    passed: bool


def run_guarded_transition(stage, *, verified_head, verified_base, read_observation,
                           perform, now, max_age, record=None, hostless=False,
                           local_checks=None, verified_tree=None, owner_decision=None):
    """Read and guard before invoking one caller-owned action with pinned identity.

    The adapter owns authentication, permissions, bounded polling and actual commands.
    `perform(head=..., base=...)` must preserve these pins and use native enforcement;
    no local read can prevent a subsequent remote base race. No retries or bypass flags
    are supplied. A draft may become ready but cannot merge while still a draft.
    """
    try:
        _require(stage in ("expensive-checks", "ready", "wait", "merge"), "stage")
        _sha(verified_head, "verified_head")
        _sha(verified_base, "verified_base")
        _time(max_age, "max_age")
        _require(type(hostless) is bool, "hostless")
        observation = read_observation()
        current = now()
        fresh = evaluate(observation, now=lambda: current, owner_decision=owner_decision)
        _require((fresh["head"], fresh["base"]) == (verified_head, verified_base),
                 "target changed; rerun applicable verify/review")
        _require(current - fresh["observed_at"] <= max_age, "stale observation")
        _require(current < fresh["deadline"], "deadline expired")
        merge = fresh["mergeability"]
        _require((merge["head"], merge["base"]) == (verified_head, verified_base),
                 "mergeability target changed")
        allowed = {"CLEAN", "HAS_HOOKS"}
        if stage in ("expensive-checks", "wait", "ready"):
            allowed.add("DRAFT")
        if stage == "ready" and _ready_eligible(fresh):
            allowed.update({"BLOCKED", "UNSTABLE"})
        # Missing/pending checks can explain BLOCKED while CI is still starting.
        # Unexplained protection blockers and explicit failures remain blockers.
        waiting_checks = any(reason.startswith(("missing-check:", "pending-check:"))
                             for reason in fresh["reasons"])
        only_waiting = waiting_checks and all(
            reason.startswith(("missing-check:", "pending-check:"))
            or reason == "mergeability:" + merge["state"]
            or (stage == "wait" and reason == "policy-unknown")
            for reason in fresh["reasons"])
        if stage in ("expensive-checks", "wait"):
            _require(fresh["result"] != "failed", "explicit failed check")
            if only_waiting:
                allowed.add("BLOCKED")
                if stage == "wait":
                    allowed.add("UNSTABLE")
            if stage == "wait":
                # Polling may resolve UNKNOWN, bounded by the checked deadline.
                allowed.add("UNKNOWN")
        _require(merge["state"] in allowed, "mergeability blocks transition")
        if stage in ("ready", "merge"):
            predicate = is_ready if stage == "ready" else is_fresh
            _require(predicate(record, observation=observation, now=lambda: current,
                               max_age=max_age, owner_decision=owner_decision),
                     "stale or insufficient gate evidence")
        if stage == "ready":
            _require(type(local_checks) is LocalCheckEvidence, "local project check evidence")
            _sha(verified_tree, "verified_tree")
            _time(local_checks.checked_at, "checked_at")
            _require((local_checks.head, local_checks.base, local_checks.tree)
                     == (verified_head, verified_base, verified_tree), "local check target changed")
            _require(all(value is True for value in (
                local_checks.defined, local_checks.available, local_checks.passed)),
                "project checks undefined, unavailable, or failed; draft or clarify")
            _require(type(local_checks.commands) is tuple and bool(local_checks.commands),
                     "missing project check commands")
            for command in local_checks.commands:
                _text(command, "project check command")
            _require(0 <= current - local_checks.checked_at <= max_age, "stale local checks")
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise TransitionBlocked(str(error)) from error
    return perform(head=verified_head, base=verified_base)
