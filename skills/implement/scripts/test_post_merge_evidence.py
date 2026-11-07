"""Real ignored filesystem and scratch Git; callback-only fake forge."""

from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
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
        self.home = self.repo.parent / (self.repo.name + "-home")
        self.home.mkdir()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.git("init", "-q")
        (self.repo / "plan.md").write_text("Completion in PR #23.\n")
        (self.repo / "spec.md").write_text("Approved spec.\n")
        self.git("add", "plan.md", "spec.md")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                 "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Fixture squash result")
        self.record = {"schema": "evidence-record-v1", "repo": "forge.test/owner/repo", "pr": 23,
            "task": "Task 9", "attempt": "attempt-1", "merge_sha": self.git("rev-parse", "HEAD"),
            "deployment": {"id": "deployment-8", "version": "build-19"}, "timestamp": 100,
            "checks": [{"command": "verify-deployment", "result": "health checks passed"}],
            "production_status": "succeeded", "author": {"id": 17, "login": "owner"}, "previous_attempt": None}
        self.store = evidence.PendingStore(self.repo, home=self.home)
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
        self.assertEqual(self.git("status", "--porcelain", "--ignored"), "")


class PendingStoreLocationTests(unittest.TestCase):
    """Where the pending store lives: ~/.sentimony first, a populated legacy folder otherwise."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve() / "repo"
        self.repo.mkdir()
        self.home = Path(self.temp.name).resolve() / "home"
        self.home.mkdir()
        self.git("init", "-q")
        (self.repo / "plan.md").write_text("Completion in PR #23.\n")
        self.git("add", "plan.md")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                 "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Fixture")
        self.record = {"schema": "evidence-record-v1", "repo": "forge.test/owner/repo", "pr": 23,
            "task": "Task 9", "attempt": "attempt-1", "merge_sha": self.git("rev-parse", "HEAD"),
            "deployment": {"id": "deployment-8", "version": "build-19"}, "timestamp": 100,
            "checks": [{"command": "verify-deployment", "result": "health checks passed"}],
            "production_status": "succeeded", "author": {"id": 17, "login": "owner"}, "previous_attempt": None}

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def exclude(self):
        return Path(self.git("rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))

    def new_root(self):
        return self.home / ".sentimony" / "agentflow" / "implement" / evidence.slug(evidence.project_key(self.repo))

    def make_legacy(self, ignored=True):
        legacy = self.repo / ".delivery-evidence"
        legacy.mkdir(mode=0o700)
        if ignored:
            self.exclude().write_text(self.exclude().read_text() + "\n/.delivery-evidence/\n")
        (legacy / "pending.json").write_text("{}")
        return legacy

    def test_slug_matches_the_context_transfer_vectors(self):
        self.assertEqual(evidence.slug("/"), "root-8a5edab28263")
        name, _, _ = evidence.slug(self.repo.parent / ("щ" * 100)).rpartition("-")
        self.assertEqual(name, "щ" * 32)

    def test_fresh_run_uses_a_private_folder_and_leaves_the_project_untouched(self):
        exclude_before = self.exclude().read_bytes() if self.exclude().exists() else None
        store = evidence.PendingStore(self.repo, home=self.home)
        self.assertEqual(store.root, self.new_root())
        self.assertFalse(store.legacy)
        self.assertIsNone(store.unused_legacy)
        for part in (store.root, store.root.parent, store.root.parent.parent, store.root.parent.parent.parent):
            self.assertEqual(part.stat().st_mode & 0o777, 0o700)
        evidence.prepare(self.record, store=store)
        self.assertEqual(self.git("status", "--porcelain", "--ignored"), "")
        self.assertEqual(self.exclude().read_bytes() if self.exclude().exists() else None, exclude_before)

    def test_two_worktrees_share_one_store(self):
        tree = self.repo.parent / "linked"
        self.git("worktree", "add", "-q", str(tree), "-b", "other")
        self.assertEqual(evidence.PendingStore(self.repo, home=self.home).root,
                         evidence.PendingStore(tree, home=self.home).root)

    def test_populated_legacy_is_kept_until_the_new_place_has_data(self):
        self.make_legacy()
        store = evidence.PendingStore(self.repo, home=self.home)
        self.assertTrue(store.legacy)
        self.assertEqual(store.root, self.repo / ".delivery-evidence")
        path = evidence.prepare(self.record, store=store)
        self.assertFalse((self.home / ".sentimony").exists())
        again = evidence.PendingStore(self.repo, home=self.home)
        self.assertTrue(again.legacy)
        self.assertEqual(again.load(path)["record"]["task"], "Task 9")
        self.assertTrue((again.root / ("snapshot-" + again.load(path)["record"]["content_sha256"] + ".json")).is_file())

    def test_new_place_wins_when_both_have_data(self):
        store = evidence.PendingStore(self.repo, home=self.home)
        evidence.prepare(self.record, store=store)
        legacy = self.make_legacy()
        chosen = evidence.PendingStore(self.repo, home=self.home)
        self.assertFalse(chosen.legacy)
        self.assertEqual(chosen.root, self.new_root())
        self.assertEqual(chosen.unused_legacy, legacy)
        self.assertEqual((legacy / "pending.json").read_text(), "{}")

    def test_a_legacy_folder_must_still_be_ignored_and_real(self):
        legacy = self.make_legacy(ignored=False)
        with self.assertRaises(evidence.EvidenceError):
            evidence.PendingStore(self.repo, home=self.home)
        shutil.rmtree(legacy)
        real = self.repo.parent / "elsewhere"
        real.mkdir()
        (real / "pending.json").write_text("{}")
        self.exclude().write_text(self.exclude().read_text() + "\n/.delivery-evidence\n")
        legacy.symlink_to(real, target_is_directory=True)
        with self.assertRaises(evidence.EvidenceError):
            evidence.PendingStore(self.repo, home=self.home)

    def test_a_symlink_on_any_component_is_refused(self):
        evidence.PendingStore(self.repo, home=self.home)
        outside = self.repo.parent / "outside"
        names = [".sentimony", "agentflow", "implement", evidence.slug(evidence.project_key(self.repo))]
        for depth in range(len(names)):
            with self.subTest(depth=depth):
                shutil.rmtree(self.home / ".sentimony", ignore_errors=True)
                if (self.home / ".sentimony").is_symlink():
                    (self.home / ".sentimony").unlink()
                shutil.rmtree(outside, ignore_errors=True)
                outside.mkdir()
                current = self.home
                for name in names[:depth]:
                    current = current / name
                    current.mkdir(mode=0o700)
                (current / names[depth]).symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(evidence.EvidenceError, "symlink"):
                    evidence.PendingStore(self.repo, home=self.home)
                self.assertEqual(list(outside.iterdir()), [])

    def test_wide_folders_are_narrowed_and_foreign_owners_refused(self):
        store = evidence.PendingStore(self.repo, home=self.home)
        for part in (store.root, store.root.parent, store.root.parent.parent, store.root.parent.parent.parent):
            part.chmod(0o777)
        evidence.PendingStore(self.repo, home=self.home)
        self.assertEqual(store.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(store.root.parent.parent.parent.stat().st_mode & 0o777, 0o700)
        with patch.object(evidence.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(evidence.EvidenceError):
                evidence.PendingStore(self.repo, home=self.home)

    def test_a_snapshot_alone_does_not_hide_a_legacy_envelope(self):
        store = evidence.PendingStore(self.repo, home=self.home)
        evidence.prepare(self.record, store=store)
        for envelope in store.root.glob("*.json"):
            if not envelope.name.startswith("snapshot-"):
                envelope.unlink()
        self.make_legacy()
        chosen = evidence.PendingStore(self.repo, home=self.home)
        self.assertTrue(chosen.legacy)
        self.assertIsNone(chosen.unused_legacy)

    def test_inherited_git_variables_do_not_change_the_project_key(self):
        other = self.repo.parent / "other"
        other.mkdir()
        subprocess.run(["git", "-C", str(other), "init", "-q"], check=True)
        expected = self.new_root()
        with patch.dict(os.environ, {"GIT_DIR": str(other / ".git"), "GIT_COMMON_DIR": str(other / ".git")}):
            self.assertEqual(evidence.PendingStore(self.repo, home=self.home).root, expected)

    def test_a_home_inside_the_project_is_refused(self):
        inside = self.repo / "fake-home"
        inside.mkdir()
        with self.assertRaisesRegex(evidence.EvidenceError, "outside the project"):
            evidence.PendingStore(self.repo, home=inside)
        self.assertEqual(list(inside.iterdir()), [])

    def test_an_unusable_home_is_refused_without_creating_anything(self):
        with self.assertRaisesRegex(evidence.EvidenceError, "HOME"):
            evidence.PendingStore(self.repo, home=self.home / "missing")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(evidence.EvidenceError, "HOME"):
                evidence.PendingStore(self.repo)
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
