"""Real ignored filesystem and scratch Git; callback-only fake forge."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import post_merge_evidence as evidence


class FakeTransport:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self.comments, self.writes = {}, []
        self.actor = {"id": 17, "login": "owner"}
        self.unknown_write = self.unavailable = self.mismatch = self.hidden = False

    def current_author(self):
        return deepcopy(self.actor)

    def lookup(self, repo, pr, key_hash):
        if self.unavailable:
            raise evidence.TransportError("offline")
        prefix = "<!-- agentflow-evidence:v1 " + key_hash + " -->\n"
        matches = [] if self.hidden else [c for c in self.comments.values() if c["body"].startswith(prefix)]
        return {"complete": True, "absence_confirmed": not self.hidden, "matches": deepcopy(matches)}

    def before_write(self, operation):
        state = self.store.load(self.path)
        assert state["write_state"] == "uncertain"
        assert state["record"]["evidence_status"] == "evidence-pending"
        assert (self.store.root / ("snapshot-" + state["record"]["content_sha256"] + ".json")).is_file()
        self.writes.append(operation)

    def create(self, repo, pr, body, key_hash):
        self.before_write("create")
        comment_id = max(self.comments, default=0) + 1
        self.comments[comment_id] = {"id": comment_id, "repo": repo, "pr": pr,
            "url": "https://forge.test/owner/repo/pull/23#comment-" + str(comment_id),
            "author_id": self.actor["id"], "author_login": self.actor["login"], "body": body}
        if self.unknown_write:
            raise evidence.TransportError("unknown write")
        return comment_id

    def update(self, comment_id, body):
        self.before_write("update")
        self.comments[comment_id]["body"] = body
        if self.unknown_write:
            raise evidence.TransportError("unknown write")
        return comment_id

    def read(self, comment_id):
        comment = deepcopy(self.comments[comment_id])
        if self.mismatch:
            content = json.loads(comment["body"].split("\n", 1)[1])
            content["checks"][0]["result"] = "changed after write"
            comment["body"] = comment["body"].split("\n", 1)[0] + "\n" + json.dumps(content)
        return comment


class PostMergeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        self.git("init", "-q")
        (self.repo / ".gitignore").write_text(".delivery-evidence/\n")
        (self.repo / "plan.md").write_text("Completion in PR #23.\n")
        (self.repo / "spec.md").write_text("Approved spec.\n")
        self.git("add", ".gitignore", "plan.md", "spec.md")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                 "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Fixture squash result")
        self.record = {"schema": "evidence-record-v1", "repo": "forge.test/owner/repo", "pr": 23,
            "task": "Task 9", "attempt": "attempt-1", "merge_sha": self.git("rev-parse", "HEAD"),
            "deployment": {"id": "deployment-8", "version": "build-19"}, "timestamp": 100,
            "checks": [{"command": "verify-deployment", "result": "health checks passed"}],
            "production_status": "succeeded", "author": {"id": 17, "login": "owner"}, "previous_attempt": None}
        self.store = evidence.PendingStore(self.repo)
        self.path = evidence.prepare(self.record, store=self.store)
        self.transport = FakeTransport(self.store, self.path)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def authority(self):
        r = self.store.load(self.path)["record"]
        return evidence.PublicationAuthority(r["repo"], r["pr"], r["task"], r["attempt"],
            r["author"]["id"], r["author"]["login"], r["content_sha256"], True)

    def publish(self, **kwargs):
        return evidence.publish(self.path, store=self.store, transport=self.transport,
                                authority=kwargs.get("authority", self.authority()))

    def test_unknown_write_retry_does_not_duplicate(self):
        self.transport.unknown_write = True
        first = self.publish()
        self.assertEqual(first["evidence_status"], "evidence-pending")
        self.assertEqual(first["production_status"], "succeeded")
        self.transport.unknown_write = False
        second = self.publish()
        self.assertEqual(second["evidence_status"], "published")
        self.assertEqual(second["content_sha256"], first["content_sha256"])
        self.assertEqual(self.transport.writes, ["create"])
        self.assertEqual(len(self.transport.comments), 1)

    def test_readback_mismatch_never_reports_published(self):
        self.transport.mismatch = True
        result = self.publish()
        self.assertEqual(result["evidence_status"], "evidence-pending")
        self.assertIsNone(result["canonical_url"])
        self.assertTrue(self.path.is_file())

    def test_canonical_unavailable_keeps_evidence_pending(self):
        self.transport.unavailable = True
        result = self.publish()
        self.assertEqual(result["evidence_status"], "evidence-pending")
        self.assertEqual(result["production_status"], "succeeded")
        self.assertEqual(self.transport.writes, [])
        self.assertEqual(self.store.load(self.path)["record"], result)

    def test_same_attempt_updates_and_recovers_unknown_update(self):
        first = self.publish()
        self.record["checks"][0]["result"] = "health and smoke checks passed"
        self.path = evidence.prepare(self.record, store=self.store)
        self.transport.unknown_write = True
        self.assertEqual(self.publish()["evidence_status"], "evidence-pending")
        self.transport.unknown_write = False
        result = self.publish()
        self.assertEqual(result["evidence_status"], "published")
        self.assertEqual(result["canonical_url"], first["canonical_url"])
        self.assertIn(first["content_sha256"], result["history"])
        self.assertEqual(self.transport.writes, ["create", "update"])

    def test_unknown_write_hidden_by_lookup_never_blindly_recreates(self):
        self.transport.unknown_write = True
        self.publish()
        self.transport.unknown_write, self.transport.hidden = False, True
        self.assertEqual(self.publish()["evidence_status"], "evidence-pending")
        self.assertEqual(self.transport.writes, ["create"])

    def test_new_attempt_preserves_previous_local_and_canonical_record(self):
        old = self.publish()
        old_file, old_comment = self.path.read_bytes(), deepcopy(self.transport.comments[1])
        self.record.update(attempt="attempt-2", previous_attempt=evidence.previous_attempt(old), timestamp=200)
        self.path = evidence.prepare(self.record, store=self.store)
        self.transport.path = self.path
        result = self.publish()
        self.assertEqual(result["evidence_status"], "published")
        self.assertEqual(result["previous_attempt"], evidence.previous_attempt(old))
        self.assertEqual(Path(old["local_pending_path"]).read_bytes(), old_file)
        self.assertEqual(self.transport.comments[1], old_comment)
        self.assertEqual(len(self.transport.comments), 2)

    def test_foreign_comments_untouched_and_own_ambiguity_blocks(self):
        self.publish()
        foreign = deepcopy(self.transport.comments[1])
        foreign.update(id=2, author_id=99, author_login="outsider")
        self.transport.comments[2] = deepcopy(foreign)
        self.record["timestamp"] = 101
        self.path = evidence.prepare(self.record, store=self.store)
        self.assertEqual(self.publish()["evidence_status"], "published")
        self.assertEqual(self.transport.comments[2], foreign)
        duplicate = deepcopy(self.transport.comments[1])
        duplicate["id"] = 3
        self.transport.comments[3] = duplicate
        self.assertEqual(self.publish()["evidence_status"], "evidence-pending")
        self.assertEqual(self.transport.writes, ["create", "update"])

    def test_current_author_and_authority_both_required(self):
        for authority in (None, {}, replace(self.authority(), allow_publish=False),
                          replace(self.authority(), attempt="other")):
            self.assertEqual(self.publish(authority=authority)["evidence_status"], "evidence-pending")
        self.transport.actor = {"id": 99, "login": "outsider"}
        self.assertEqual(self.publish()["evidence_status"], "evidence-pending")
        self.assertEqual(self.transport.writes, [])

    def test_store_requires_gitignore_and_rejects_symlink(self):
        (self.repo / ".gitignore").write_text("")
        with self.assertRaises(evidence.EvidenceError):
            evidence.PendingStore(self.repo)
        exclude = Path(self.git("rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
        exclude.write_text(exclude.read_text() + "\n/.delivery-evidence/\n")
        self.assertEqual(evidence.PendingStore(self.repo).root, self.store.root)
        (self.repo / ".gitignore").write_text(".delivery-evidence/\n.other/\n")
        (self.repo / ".other").symlink_to(self.store.root, target_is_directory=True)
        with self.assertRaises(evidence.EvidenceError):
            evidence.PendingStore(self.repo, directory=".other")

    def test_atomic_fsync_store_and_failed_replace_retains_old_file(self):
        self.record["timestamp"] = 102
        with patch.object(evidence.os, "fsync", wraps=evidence.os.fsync) as sync:
            evidence.prepare(self.record, store=self.store)
            self.assertGreaterEqual(sync.call_count, 4)
        prepared = self.path.read_bytes()
        state = self.store.load(self.path)
        state["reason"] = "later"
        with patch.object(evidence.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.store.save(state)
        self.assertEqual(self.path.read_bytes(), prepared)

    def test_scratch_squash_result_keeps_tracked_plan_spec_clean(self):
        before = {name: (self.repo / name).read_bytes() for name in ("plan.md", "spec.md")}
        before_head = self.git("rev-parse", "HEAD")
        self.publish()
        self.assertEqual(self.git("rev-parse", "HEAD"), before_head)
        self.assertEqual({name: (self.repo / name).read_bytes() for name in before}, before)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertIn(".delivery-evidence/", self.git("status", "--porcelain", "--ignored"))


if __name__ == "__main__":
    unittest.main()
