"""Offline delivery across actual gate, durable evidence and scratch Git cleanup."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
for directory in ("verify", "finalize", "implement"):
    sys.path.insert(0, str(ROOT / "skills" / directory / "scripts"))

from dependency_isolation import prepare_environment
import delivery_gate as gate
from cleanup_guard import CleanupAuthority, CleanupGuard
import post_merge_evidence as evidence
from test_post_merge_evidence import FakeTransport


class DeliveryIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="delivery-integration-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "source"
        self.repo.mkdir()
        tools = self.root / "tools"
        tools.mkdir()
        self.git_binary = shutil.which("git")
        self.assertIsNotNone(self.git_binary)
        (tools / "git").symlink_to(self.git_binary)
        (tools / "python3").symlink_to(sys.executable)
        self.env = prepare_environment(self.root / "private", tools)
        self.env.update(GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                        GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid",
                        PYTHONDONTWRITEBYTECODE="1")
        self.environment = patch.dict(os.environ, self.env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.git("init", "-q")
        self.git("config", "core.hooksPath", os.devnull)
        (self.repo / ".gitignore").write_text(".delivery-evidence/\nignored/\n")
        (self.repo / "plan.md").write_text("Post-merge completion: PR #23 evidence.\n")
        (self.repo / "spec.md").write_text("Approved local fixture contract.\n")
        (self.repo / "owned.txt").write_text("before\n")
        (self.repo / "foreign.txt").write_text("foreign\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial fixture")
        self.base = self.git("rev-parse", "HEAD").decode().strip()
        self.identity = dict(repo="forge.test/owner/repo", pr=23,
                             task="Task 9", attempt="attempt-1")
        self.events = []

    def git(self, *args, data=None, index=None):
        env = dict(self.env)
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        return subprocess.run([self.git_binary, "-C", str(self.repo), *args],
                              input=data, env=env, check=True, capture_output=True).stdout

    def transition(self, stage, record, head, perform, **kwargs):
        def read():
            self.events.append("read:" + stage)
            return deepcopy(self.observation)
        return gate.run_guarded_transition(
            stage, verified_head=head, verified_base=self.base,
            read_observation=read, perform=perform, now=lambda: 120,
            max_age=30, record=record, **kwargs)

    def test_actual_ci_step_rejects_an_empty_delivery_suite(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        match = re.search(r"^      - name: Test delivery helpers\n        run: \|\n"
                          r"((?:          .*\n|\n)+)", workflow, re.M)
        self.assertIsNotNone(match)
        empty = self.root / "empty-checkout"
        (empty / "skills/verify/scripts").mkdir(parents=True)
        result = subprocess.run(["/bin/bash", "-e", "-c", textwrap.dedent(match[1])],
                                cwd=empty, env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No tests discovered: skills/verify/scripts/test_dependency_isolation.py",
                      result.stderr)

    def test_delayed_checks_race_squash_pending_retry_and_cleanup(self):
        # An actual child receives private writable roots and no agent/forge fallback.
        child = subprocess.run([sys.executable, "-c", (
            "import json,os,shutil; print(json.dumps({'home':os.environ['HOME'],"
            "'native':[shutil.which(n) for n in ('codex','claude','agy','gh')]}))")],
            env=self.env, check=True, capture_output=True, text=True)
        child_state = json.loads(child.stdout)
        self.assertEqual(child_state["home"], self.env["HOME"])
        self.assertEqual(child_state["native"], [None] * 4)

        (self.repo / "owned.txt").write_text("after\n")
        owned_patch = self.git("diff", "--binary", "--", "owned.txt")
        (self.repo / "foreign.txt").write_text("foreign staged\n")
        self.git("add", "foreign.txt")
        (self.repo / "ignored").mkdir()
        (self.repo / "ignored" / "placeholder.txt").write_text("preserve local data\n")
        guard = CleanupGuard(self.repo, git=self.git_binary, env=self.env)
        journal = self.root / "cleanup.json"
        proof = guard.capture(journal, identity=self.identity, worktree_patch=owned_patch)
        source_index = guard.index.read_bytes()

        # Build a feature object with a temporary index; foreign staging never leaves source.
        index = self.root / "feature-index"
        self.git("read-tree", self.base, index=index)
        self.git("apply", "--cached", data=owned_patch, index=index)
        tree = self.git("write-tree", index=index).decode().strip()
        head = self.git("commit-tree", tree, "-p", self.base,
                        data=b"Feature fixture\n").decode().strip()
        self.observation = json.loads((ROOT / "skills/finalize/scripts/fixtures/required.json").read_text())

        def target(new_head):
            self.observation.update(head=new_head, base=self.base)
            self.observation["checks"]["head"] = new_head
            self.observation["mergeability"].update(head=new_head, base=self.base)
            for check in self.observation["checks"]["items"]:
                check["head"] = new_head

        target(head)
        successful_checks = deepcopy(self.observation["checks"]["items"])
        self.observation["checks"]["items"] = []
        self.observation["mergeability"]["state"] = "BLOCKED"
        waiting = gate.evaluate(self.observation, now=lambda: 110)
        self.assertEqual(waiting["result"], "blocked")

        def delayed_jobs(**pins):
            self.assertEqual(pins, dict(head=head, base=self.base))
            self.events.append("delayed-job-completed")
            self.observation["checks"]["items"] = successful_checks
            self.observation["mergeability"]["state"] = "CLEAN"

        self.transition("wait", waiting, head, delayed_jobs)
        ready = gate.evaluate(self.observation, now=lambda: 115)
        newer_head = self.git("commit-tree", tree, "-p", head,
                              data=b"New feature head\n").decode().strip()
        target(newer_head)
        with self.assertRaises(gate.TransitionBlocked):
            self.transition("wait", ready, head,
                            lambda **pins: self.fail("stale target invoked watcher"))

        # Reverification exercises the committed object and binds the new full identity.
        self.assertEqual(self.git("show", newer_head + ":owned.txt"), b"after\n")
        self.assertEqual(self.git("rev-parse", newer_head + "^{tree}").decode().strip(), tree)
        ready_jobs = deepcopy(self.observation["checks"]["items"])
        self.observation["checks"]["items"] = []
        self.observation["mergeability"]["state"] = "DRAFT"
        ready = gate.evaluate(self.observation, now=lambda: 118)
        local_checks = gate.LocalCheckEvidence(
            newer_head, self.base, tree, ("git show <verified-head>:owned.txt",),
            118, True, True, True)
        def become_ready(**pins):
            self.assertEqual(pins, dict(head=newer_head, base=self.base))
            self.events.append("ready")
            self.observation["checks"]["items"] = deepcopy(ready_jobs)
            self.observation["checks"]["items"][0].update(status="pending", conclusion=None)
            self.observation["mergeability"]["state"] = "BLOCKED"

        self.transition("ready", ready, newer_head, become_ready, hostless=True,
                        local_checks=local_checks, verified_tree=tree)
        self.assertEqual(ready["result"], "blocked")
        with self.assertRaises(gate.TransitionBlocked):
            self.transition("merge", ready, newer_head,
                            lambda **pins: self.fail("pending ready-triggered job merged"))

        def complete_ready_jobs(**pins):
            self.events.append("ready-job-completed")
            self.observation["checks"]["items"] = ready_jobs
            self.observation["mergeability"]["state"] = "CLEAN"

        self.transition("wait", ready, newer_head, complete_ready_jobs)
        ready = gate.evaluate(self.observation, now=lambda: 120)

        def squash(**pins):
            self.assertEqual(pins, dict(head=newer_head, base=self.base))
            merged = self.git("commit-tree", tree, "-p", self.base,
                              data=b"Simulated native squash\n").decode().strip()
            self.git("update-ref", "refs/heads/integrated", merged)
            self.events.append("pinned-squash")
            return merged

        merged = self.transition("merge", ready, newer_head, squash)
        self.assertNotEqual(merged, newer_head)
        hosts_before = {name: (self.repo / name).read_bytes() for name in ("plan.md", "spec.md")}
        store = evidence.PendingStore(self.repo)
        content = dict(schema="evidence-record-v1", **self.identity, merge_sha=merged,
                       deployment={"id": "scratch-only", "version": "fixture-1"}, timestamp=120,
                       checks=[{"command": "scratch committed-object checks", "result": "passed"}],
                       production_status="succeeded", author={"id": 17, "login": "owner"},
                       previous_attempt=None)
        path = evidence.prepare(content, store=store)
        pending = store.load(path)["record"]
        authority = evidence.PublicationAuthority(
            content["repo"], content["pr"], content["task"], content["attempt"],
            17, "owner", pending["content_sha256"], True)
        transport = FakeTransport(store, path)
        transport.unknown_write = True
        pending = evidence.publish(path, store=store, transport=transport, authority=authority)
        self.assertEqual(pending["evidence_status"], "evidence-pending")
        self.assertEqual(pending["production_status"], "succeeded")
        cleanup_authority = CleanupAuthority(**self.identity, merge_sha=merged,
            allow_cleanup=True, ownership_sha256=proof["ownership_sha256"])

        def observed(record):
            return dict(**self.identity, merge_sha=merged, destination_sha=merged, evidence=record)

        refused = guard.apply_cleanup(journal, authority=cleanup_authority,
                                      observe=lambda: observed(pending))
        self.assertEqual(refused["status"], "blocked")
        self.assertEqual((self.repo / "owned.txt").read_bytes(), b"after\n")
        self.assertEqual(guard.index.read_bytes(), source_index)
        transport.unknown_write = False
        published = evidence.publish(path, store=store, transport=transport, authority=authority)
        self.assertEqual(published["evidence_status"], "published")
        self.assertEqual(transport.writes, ["create"])
        self.assertEqual(len(transport.comments), 1)
        cleaned = guard.apply_cleanup(journal, authority=cleanup_authority,
                                      observe=lambda: observed(published))
        self.assertEqual(cleaned["status"], "cleaned")
        self.assertEqual((self.repo / "owned.txt").read_bytes(), b"before\n")
        self.assertEqual(guard.index.read_bytes(), source_index)
        self.assertEqual((self.repo / "foreign.txt").read_bytes(), b"foreign staged\n")
        self.assertEqual((self.repo / "ignored/placeholder.txt").read_text(), "preserve local data\n")
        self.assertEqual(self.git("show", merged + ":owned.txt"), b"after\n")
        self.assertEqual({name: (self.repo / name).read_bytes() for name in hosts_before}, hosts_before)
        self.assertEqual(self.git("diff", "HEAD", "--", "plan.md", "spec.md"), b"")
        self.assertEqual(self.events[-4:], ["read:wait", "ready-job-completed",
                                           "read:merge", "pinned-squash"])
        deletion = guard.deletion_decision(journal, authority=cleanup_authority,
            observe=lambda: observed(published), branch="integrated", session_created=True)
        self.assertEqual(deletion["status"], "blocked")
        self.assertIn("ignored/untracked", deletion["reason"])


if __name__ == "__main__":
    unittest.main()
