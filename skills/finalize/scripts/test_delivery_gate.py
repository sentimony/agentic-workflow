"""Offline contract tests for policy, delayed checks, and gate freshness."""

import copy
import json
from pathlib import Path
import unittest

import delivery_gate as gate


class DeliveryGateTests(unittest.TestCase):
    def setUp(self):
        self.obs = json.loads((Path(__file__).parent / "fixtures/required.json").read_text())

    def evaluate(self, **kwargs):
        return gate.evaluate(self.obs, now=lambda: 110, **kwargs)

    def unknown(self):
        self.obs["policy"]["retrieval"] = "denied"

    def test_delayed_required_job_waits_until_it_appears(self):
        success = copy.deepcopy(self.obs["checks"]["items"])
        self.obs["checks"]["items"] = []
        waiting = self.evaluate()
        self.assertEqual(waiting["result"], "blocked")
        self.assertIn("missing-check:app:1/validate", waiting["reasons"])
        self.obs["checks"]["items"] = success
        self.assertEqual(self.evaluate()["result"], "passed")

    def test_unknown_policy_with_green_checks_is_blocked(self):
        self.unknown()
        result = self.evaluate()
        self.assertEqual(result["policy_state"], "unknown")
        self.assertEqual(result["result"], "blocked")

    def test_incomplete_policy_never_claims_known_none(self):
        self.obs["policy"].update(coverage="incomplete", required=[], absence_proof="nothing visible")
        self.assertEqual(self.evaluate()["policy_state"], "unknown")
        self.assertEqual(self.evaluate()["result"], "blocked")

    def test_timeout_blocks_even_green_checks(self):
        self.obs["deadline"] = 110
        self.assertEqual(self.evaluate()["result"], "blocked")
        self.assertIn("deadline-expired", self.evaluate()["reasons"])

    def test_empty_checks_need_positive_absence_proof_and_complete_policy(self):
        self.obs["policy"]["required"] = []
        self.obs["checks"]["items"] = []
        self.assertEqual(self.evaluate()["result"], "blocked")
        self.obs["policy"]["absence_proof"] = "effective policy explicitly has zero required contexts"
        self.assertEqual(self.evaluate()["policy_state"], "known-none")
        self.assertEqual(self.evaluate()["result"], "passed")
        for retrieval in ("not-found", "denied", "error"):
            with self.subTest(retrieval=retrieval):
                self.obs["policy"]["retrieval"] = retrieval
                self.assertEqual(self.evaluate()["policy_state"], "unknown")
                self.assertEqual(self.evaluate()["result"], "blocked")

    def test_project_declared_checks_still_wait_under_known_none(self):
        self.obs["project_checks"] = copy.deepcopy(self.obs["policy"]["required"])
        self.obs["policy"].update(required=[], absence_proof="effective policy has no requirements")
        self.obs["checks"]["items"] = []
        self.assertEqual(self.evaluate()["result"], "blocked")

    def test_every_visible_pending_or_red_check_stops_merge(self):
        for conclusion in (None, *sorted(gate.RED_CONCLUSIONS)):
            with self.subTest(conclusion=conclusion):
                self.obs["checks"]["items"].append({
                    "id": "app:2/advisory", "head": self.obs["head"],
                    "status": "pending" if conclusion is None else "completed",
                    "conclusion": conclusion,
                })
                self.assertEqual(self.evaluate()["result"], "blocked" if conclusion is None else "failed")
                self.obs["checks"]["items"].pop()

    def test_skip_and_neutral_need_explicit_conclusion_semantics(self):
        for conclusion in ("skipped", "neutral"):
            with self.subTest(conclusion=conclusion):
                self.obs["policy"]["required"][0]["accepted"] = ["success"]
                self.obs["checks"]["items"][0]["conclusion"] = conclusion
                self.assertEqual(self.evaluate()["result"], "blocked")
                self.obs["policy"]["required"][0]["accepted"].append(conclusion)
                self.assertEqual(self.evaluate()["result"], "passed")

    def test_project_cannot_loosen_forge_semantics(self):
        self.obs["project_checks"] = copy.deepcopy(self.obs["policy"]["required"])
        self.obs["project_checks"][0]["accepted"].append("skipped")
        self.obs["checks"]["items"][0]["conclusion"] = "skipped"
        self.assertEqual(self.evaluate()["result"], "blocked")

    def test_wrong_sha_or_incomplete_snapshot_blocks(self):
        for mutate in (
            lambda o: o["checks"].update(head="c" * 40),
            lambda o: o["checks"]["items"][0].update(head="c" * 40),
            lambda o: o["checks"].update(complete=False),
            lambda o: o["mergeability"].update(base="c" * 40),
            lambda o: o["mergeability"].update(head="c" * 40),
        ):
            with self.subTest(mutate=mutate):
                original = copy.deepcopy(self.obs)
                mutate(self.obs)
                self.assertEqual(self.evaluate()["result"], "blocked")
                self.obs = original

    def test_mergeability_unknown_and_conflicting_states_block(self):
        for state in sorted(gate.MERGE_STATES - {"CLEAN", "HAS_HOOKS"}):
            with self.subTest(state=state):
                self.obs["mergeability"]["state"] = state
                self.assertEqual(self.evaluate()["result"], "blocked")

    def test_native_gate_is_positive_only_for_exact_identity_without_bypass(self):
        self.unknown()
        self.obs["native_gate"] = {"source": "forge:native-gate/decision-1",
                                   "head": self.obs["head"], "base": self.obs["base"],
                                   "state": "passed", "bypass": False}
        self.assertEqual(self.evaluate()["unknown_policy_basis"], "native-gate")
        self.assertEqual(self.evaluate()["result"], "passed")
        for key, value in (("head", "c" * 40), ("base", "c" * 40),
                           ("bypass", True), ("state", "blocked"), ("state", "unknown")):
            with self.subTest(key=key, value=value):
                original = copy.deepcopy(self.obs["native_gate"])
                self.obs["native_gate"][key] = value
                self.assertEqual(self.evaluate()["result"], "blocked")
                self.obs["native_gate"] = original
        self.obs["checks"]["items"][0].update(status="pending", conclusion=None)
        self.assertEqual(self.evaluate()["result"], "blocked")

    def decision(self, **changes):
        values = dict(head=self.obs["head"], base=self.obs["base"],
                      observation_id=gate.observation_id(self.obs), decision_id="session:owner/1",
                      reason="Owner explicitly chose native merge under unknown policy",
                      allow_unknown_policy=True, bypass=False)
        values.update(changes)
        return gate.OwnerDecision(**values)

    def test_owner_authority_is_separate_pinned_and_cannot_bypass(self):
        self.unknown()
        self.assertEqual(self.evaluate(owner_decision=self.decision())["result"], "passed")
        for changes in ({"head": "c" * 40}, {"base": "c" * 40},
                        {"observation_id": "old"}, {"allow_unknown_policy": False}, {"bypass": True}):
            with self.subTest(changes=changes):
                self.assertEqual(self.evaluate(owner_decision=self.decision(**changes))["result"], "blocked")
        with self.assertRaises(ValueError):
            self.evaluate(owner_decision={"allow_unknown_policy": True})
        self.obs["owner_decision"] = {"allow_unknown_policy": True}
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_strict_validation_rejects_empty_forged_or_malformed_input(self):
        mutations = (
            lambda o: o.clear(), lambda o: o.update(head="abc"),
            lambda o: o.update(head="A" * 40), lambda o: o.update(deadline=float("inf")),
            lambda o: o.update(observed_at=111), lambda o: o["checks"].update(complete="true"),
            lambda o: o["policy"].update(coverage_evidence=""),
            lambda o: o["policy"]["required"][0].update(accepted=["failure"]),
            lambda o: o["checks"]["items"].append(copy.deepcopy(o["checks"]["items"][0])),
            lambda o: o["checks"]["items"][0].update(conclusion="invented"),
            lambda o: o["checks"]["items"][0].update(status="pending"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                original = copy.deepcopy(self.obs)
                mutate(self.obs)
                with self.assertRaises(ValueError):
                    self.evaluate()
                self.obs = original

    def test_freshness_rederives_evidence_and_expires(self):
        record = self.evaluate()
        check = lambda r=record, t=120, o=self.obs: gate.is_fresh(
            r, observation=o, now=lambda: t, max_age=30)
        self.assertTrue(check())
        self.assertFalse(check(t=131))
        self.assertFalse(check(t=109))
        self.assertFalse(check(t=200))
        fake = copy.deepcopy(record)
        fake["observed_checks"] = []
        self.assertFalse(check(r=fake))
        changed = copy.deepcopy(self.obs)
        changed["policy"]["source"] = "forge:repo/base/policy/revision-2"
        self.assertFalse(check(o=changed))
        changed = copy.deepcopy(self.obs)
        changed["checks"]["items"][0].update(status="pending", conclusion=None)
        self.assertFalse(check(o=changed))
        self.assertFalse(check(r={"schema": "gate-record-v1", "result": "passed"}))

    def test_evaluation_copies_evidence_without_mutating_input(self):
        original = copy.deepcopy(self.obs)
        record = self.evaluate()
        self.assertEqual(self.obs, original)
        self.obs["policy"]["required"].clear()
        self.assertEqual(len(record["required_checks"]), 1)


class DeliveryTransitionTests(unittest.TestCase):
    def setUp(self):
        self.obs = json.loads((Path(__file__).parent / "fixtures/required.json").read_text())
        self.record = gate.evaluate(self.obs, now=lambda: 110)
        self.events = []

    def run_stage(self, stage, observation=None, **kwargs):
        if stage == "ready":
            kwargs.setdefault("verified_tree", "d" * 40)
            kwargs.setdefault("local_checks", gate.LocalCheckEvidence(
                self.record["head"], self.record["base"], "d" * 40,
                ("python3 project_check.py",), 115, True, True, True))
        def read():
            self.events.append("read")
            return copy.deepcopy(self.obs if observation is None else observation)

        def perform(**identity):
            self.events.append((stage, identity))
            return "performed"

        return gate.run_guarded_transition(
            stage, verified_head=self.record["head"], verified_base=self.record["base"],
            read_observation=read, perform=perform, now=lambda: 120, max_age=30,
            record=self.record, **kwargs)

    def test_new_read_of_unchanged_evidence_remains_fresh(self):
        fresh = copy.deepcopy(self.obs)
        fresh["observed_at"] = 119
        self.assertTrue(gate.is_fresh(self.record, observation=fresh,
                                     now=lambda: 120, max_age=30))

    def test_head_and_base_races_prevent_every_callback(self):
        for stage in ("expensive-checks", "ready", "wait", "merge"):
            for field in ("head", "base"):
                with self.subTest(stage=stage, field=field):
                    self.events.clear()
                    changed = copy.deepcopy(self.obs)
                    changed[field] = "c" * 40
                    with self.assertRaises(gate.TransitionBlocked):
                        self.run_stage(stage, changed)
                    self.assertEqual(self.events, ["read"])

    def test_actual_order_and_verified_sha_reach_fake_merge(self):
        self.assertEqual(self.run_stage("merge"), "performed")
        self.assertEqual(self.events, ["read", ("merge", {
            "head": "a" * 40, "base": "b" * 40})])

    def test_sequential_reads_stop_a_base_race_after_checks(self):
        self.assertEqual(self.run_stage("expensive-checks"), "performed")
        self.obs["base"] = "c" * 40
        with self.assertRaises(gate.TransitionBlocked):
            self.run_stage("ready")
        self.assertEqual([event for event in self.events if isinstance(event, tuple)],
                         [("expensive-checks", {"head": "a" * 40, "base": "b" * 40})])

    def test_checks_may_run_and_wait_before_checks_are_green(self):
        self.obs["checks"]["items"] = []
        self.record = gate.evaluate(self.obs, now=lambda: 110)
        for stage in ("expensive-checks", "wait"):
            with self.subTest(stage=stage):
                self.assertEqual(self.run_stage(stage), "performed")
        self.assertEqual(self.run_stage("ready"), "performed")
        with self.assertRaises(gate.TransitionBlocked):
            self.run_stage("merge")

    def test_conflict_unknown_and_timeout_prevent_work(self):
        for state in ("DIRTY", "BEHIND", "UNKNOWN"):
            with self.subTest(state=state):
                self.obs["mergeability"]["state"] = state
                with self.assertRaises(gate.TransitionBlocked):
                    self.run_stage("expensive-checks")
        self.obs["mergeability"]["state"] = "CLEAN"
        self.obs["deadline"] = 120
        with self.assertRaises(gate.TransitionBlocked):
            self.run_stage("wait")

    def test_pending_checks_allow_blocked_preflight_and_bounded_wait(self):
        self.obs["mergeability"]["state"] = "BLOCKED"
        self.obs["checks"]["items"] = []
        self.assertEqual(self.run_stage("expensive-checks"), "performed")

        def watcher(**identity):
            self.events.append(("watcher", identity))
            self.obs["mergeability"]["state"] = "CLEAN"
            self.obs["checks"]["items"] = copy.deepcopy(self.record["observed_checks"])

        gate.run_guarded_transition(
            "wait", verified_head=self.record["head"], verified_base=self.record["base"],
            read_observation=lambda: copy.deepcopy(self.obs), perform=watcher,
            now=lambda: 120, max_age=30, record=self.record)
        self.assertEqual(self.events[-1][0], "watcher")
        self.assertEqual(self.run_stage("merge"), "performed")

    def test_transient_wait_never_relaxes_ready_merge_or_conflicts(self):
        for state in ("BLOCKED", "UNSTABLE", "UNKNOWN"):
            self.obs["mergeability"]["state"] = state
            self.obs["checks"]["items"] = []
            self.assertEqual(self.run_stage("wait"), "performed")
            for stage in ("ready", "merge"):
                with self.subTest(state=state, stage=stage):
                    with self.assertRaises(gate.TransitionBlocked):
                        self.run_stage(stage)
        for state in ("DIRTY", "BEHIND"):
            self.obs["mergeability"]["state"] = state
            with self.assertRaises(gate.TransitionBlocked):
                self.run_stage("wait")
        self.obs["mergeability"]["state"] = "UNKNOWN"
        self.obs["deadline"] = 120
        with self.assertRaises(gate.TransitionBlocked):
            self.run_stage("wait")

    def test_unexplained_blocked_state_and_red_checks_do_not_start_work(self):
        self.obs["mergeability"]["state"] = "BLOCKED"
        for stage in ("expensive-checks", "wait"):
            with self.assertRaises(gate.TransitionBlocked):
                self.run_stage(stage)
        self.obs["checks"]["items"][0]["conclusion"] = "failure"
        self.obs["mergeability"]["state"] = "UNKNOWN"
        with self.assertRaises(gate.TransitionBlocked):
            self.run_stage("wait")

    def test_hostless_ready_requires_defined_available_current_local_checks(self):
        for evidence in (None, {"head": self.obs["head"]}):
            with self.subTest(evidence=evidence):
                with self.assertRaises(gate.TransitionBlocked):
                    self.run_stage("ready", hostless=True, local_checks=evidence)
        evidence = gate.LocalCheckEvidence(
            head=self.obs["head"], base=self.obs["base"], tree="d" * 40,
            commands=("python3 project_check.py",), checked_at=115,
            defined=True, available=True, passed=True)
        self.assertEqual(self.run_stage("ready", hostless=True, local_checks=evidence,
                                        verified_tree="d" * 40), "performed")
        from dataclasses import replace
        for changes in ({"head": "c" * 40}, {"base": "c" * 40}, {"tree": "e" * 40},
                        {"commands": ()}, {"defined": False}, {"available": False},
                        {"passed": False}, {"checked_at": 80}, {"checked_at": 125}):
            with self.subTest(changes=changes):
                with self.assertRaises(gate.TransitionBlocked):
                    self.run_stage("ready", hostless=True,
                                   local_checks=replace(evidence, **changes), verified_tree="d" * 40)

    def test_draft_ready_is_allowed_but_draft_merge_is_blocked(self):
        self.obs["mergeability"]["state"] = "DRAFT"
        self.record = gate.evaluate(self.obs, now=lambda: 110)
        self.assertEqual(self.run_stage("ready"), "performed")
        with self.assertRaises(gate.TransitionBlocked):
            self.run_stage("merge")
        self.obs["checks"]["items"] = []
        self.record = gate.evaluate(self.obs, now=lambda: 110)
        self.assertEqual(self.run_stage("ready"), "performed")

    def test_ready_callback_starts_required_job_then_waits_before_pinned_merge(self):
        successful = copy.deepcopy(self.obs["checks"]["items"])
        self.obs["checks"]["items"] = []
        self.obs["mergeability"]["state"] = "DRAFT"
        self.record = gate.evaluate(self.obs, now=lambda: 110)
        self.assertEqual(self.record["result"], "blocked")

        def ready(**pins):
            self.events.append(("ready-started-job", pins))
            self.obs["mergeability"]["state"] = "BLOCKED"
            self.obs["checks"]["items"] = copy.deepcopy(successful)
            self.obs["checks"]["items"][0].update(status="pending", conclusion=None)

        gate.run_guarded_transition(
            "ready", verified_head=self.record["head"], verified_base=self.record["base"],
            read_observation=lambda: copy.deepcopy(self.obs), perform=ready,
            now=lambda: 120, max_age=30, record=self.record, verified_tree="d" * 40,
            local_checks=gate.LocalCheckEvidence(self.record["head"], self.record["base"],
                "d" * 40, ("python3 project_check.py",), 115, True, True, True))
        self.assertEqual(self.events[0][0], "ready-started-job")
        with self.assertRaises(gate.TransitionBlocked):
            self.run_stage("merge")

        def wait(**pins):
            self.events.append(("job-completed", pins))
            self.obs["checks"]["items"] = successful
            self.obs["mergeability"]["state"] = "CLEAN"

        gate.run_guarded_transition("wait", verified_head=self.record["head"],
            verified_base=self.record["base"], read_observation=lambda: copy.deepcopy(self.obs),
            perform=wait, now=lambda: 120, max_age=30)
        self.record = gate.evaluate(self.obs, now=lambda: 120)
        self.assertEqual(self.run_stage("merge"), "performed")
        self.assertEqual([e[0] for e in self.events if isinstance(e, tuple)],
                         ["ready-started-job", "job-completed", "merge"])

    def test_ready_keeps_unknown_policy_unknown_and_requires_local_checks(self):
        self.obs["policy"]["retrieval"] = "denied"
        self.record = gate.evaluate(self.obs, now=lambda: 110)
        self.assertEqual(self.run_stage("ready"), "performed")
        self.assertEqual(self.record["policy_state"], "unknown")
        self.assertEqual(self.record["result"], "blocked")
        with self.assertRaises(gate.TransitionBlocked):
            self.run_stage("merge")
        with self.assertRaises(gate.TransitionBlocked):
            self.run_stage("ready", local_checks=None)
        self.obs["mergeability"]["state"] = "BLOCKED"
        self.obs["checks"]["items"][0].update(status="pending", conclusion=None)
        self.assertEqual(self.run_stage("wait"), "performed")
        self.assertEqual(self.record["policy_state"], "unknown")


if __name__ == "__main__":
    unittest.main()
