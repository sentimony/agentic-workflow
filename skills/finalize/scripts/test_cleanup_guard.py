"""Real scratch Git fixtures, with no forge, host credentials or native agents."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from cleanup_guard import (CleanupAuthority, CleanupError, CleanupGuard, DisposalAuthority,
                           EvidenceRequirement, PostMergeInventory)


class CleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        tools = self.root / "tools"
        tools.mkdir()
        self.git = shutil.which("git")
        (tools / "git").symlink_to(self.git)
        home = self.root / "home"
        home.mkdir()
        self.env = {"HOME": str(home), "PATH": str(tools), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                    "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
        self.gitrun("init", "-q")
        (self.repo / ".gitignore").write_text("ignored/\n.delivery-evidence/\n")
        self.original = b"first\n" + b"context\n" * 8 + b"own-before\n" + b"context\n" * 8 + b"foreign-before\n"
        (self.repo / "a.txt").write_bytes(self.original)
        (self.repo / "b.txt").write_bytes(b"second-before\n")
        self.gitrun("add", ".")
        self.gitrun("commit", "-qm", "initial")
        self.base = self.sha()
        self.guard = CleanupGuard(self.repo, git=self.git, env=self.env)
        self.journal = self.root / "cleanup.json"
        self.identity = {"repo": "example.invalid/o/r", "pr": 1, "task": "Task 6", "attempt": "one"}

    def gitrun(self, *args, data=None):
        return subprocess.run([self.git, "-C", str(self.repo), *args], input=data,
                              env=self.env, check=True, capture_output=True).stdout

    def sha(self):
        return self.gitrun("rev-parse", "HEAD").decode().strip()

    def own_change(self, second=False):
        path = self.repo / "a.txt"
        path.write_bytes(path.read_bytes().replace(b"own-before", b"own-after"))
        if second:
            (self.repo / "b.txt").write_bytes(b"second-after\n")
        # Raw bytes, including the final context newline, must reach git apply unchanged.
        return self.gitrun("diff", "--binary", "--", "a.txt", "b.txt")

    def integration(self, patch):
        self.gitrun("apply", "--cached", data=patch)
        tree = self.gitrun("write-tree").decode().strip()
        transfer = self.gitrun("commit-tree", tree, "-p", self.base, data=b"transfer\n").decode().strip()
        self.gitrun("read-tree", self.base)
        self.merge = transfer
        self.gitrun("update-ref", "refs/heads/integrated", transfer)
        content = dict(schema="evidence-record-v1", **self.identity, merge_sha=transfer,
                       deployment={"id": "scratch", "version": "1"}, timestamp=1,
                       checks=[{"command": "scratch", "result": "passed"}],
                       production_status="succeeded", author={"id": 1, "login": "fixture"},
                       previous_attempt=None)
        digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.evidence = dict(content, content_sha256=digest, evidence_status="published",
                             canonical_url="https://example.invalid/o/r/pull/1#comment-1",
                             local_pending_path=str(self.root / "evidence.json"), history=[])
        Path(self.evidence["local_pending_path"]).write_text(json.dumps({"record": self.evidence}))
        self.authority = CleanupAuthority(**self.identity, merge_sha=transfer, allow_cleanup=True)
        self.observation = dict(**self.identity, merge_sha=transfer, destination_sha=transfer,
                                evidence=self.evidence)

    def capture(self, journal, **kwargs):
        proof = self.guard.capture(journal, **kwargs)
        self.authority = replace(self.authority, ownership_sha256=proof["ownership_sha256"])
        return proof

    def apply(self, authority=None, observe=None):
        return self.guard.apply_cleanup(self.journal,
                                        authority=self.authority if authority is None else authority,
                                        observe=(lambda: self.observation) if observe is None else observe)

    def state(self):
        return (self.sha(), self.gitrun("ls-files", "--stage", "-z"),
                {str(p.relative_to(self.repo)): p.read_bytes()
                 for p in self.repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.repo).parts})

    def test_changed_head_blocks_without_reverse_diff(self):
        patch = self.own_change()
        self.integration(patch)
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        self.gitrun("commit", "--allow-empty", "-qm", "new source head")
        before = self.state()
        result = self.apply()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.state(), before)

    def test_observation_without_current_authority_cannot_mutate(self):
        patch = self.own_change()
        self.integration(patch)
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        before = self.state()
        result = self.guard.apply_cleanup(self.journal, authority=None, observe=lambda: self.observation)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.state(), before)

    def prepare(self, second=False):
        patch = self.own_change(second=second)
        self.integration(patch)
        return patch

    def test_success_preserves_foreign_staged_and_adjacent_worktree_changes(self):
        patch = self.prepare()
        path = self.repo / "a.txt"
        foreign_index = self.original.replace(b"foreign-before", b"foreign-staged")
        blob = self.gitrun("hash-object", "-w", "--stdin", data=foreign_index).decode().strip()
        self.gitrun("update-index", "--cacheinfo", "100644," + blob + ",a.txt")
        path.write_bytes(path.read_bytes().replace(b"foreign-before", b"foreign-working"))
        staged_before = self.gitrun("show", ":a.txt")
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        result = self.apply()
        self.assertEqual(result["status"], "cleaned", result)
        self.assertEqual(path.read_bytes(), self.original.replace(b"foreign-before", b"foreign-working"))
        self.assertEqual(self.gitrun("show", ":a.txt"), staged_before)
        self.assertEqual(self.sha(), self.base)
        self.assertEqual(self.apply()["status"], "cleaned")

    def test_staged_own_patch_is_removed_while_foreign_index_survives(self):
        patch = self.prepare()
        path = self.repo / "a.txt"
        path.write_bytes(path.read_bytes().replace(b"foreign-before", b"foreign-staged"))
        self.gitrun("add", "a.txt")
        self.capture(self.journal, identity=self.identity, index_patch=patch, worktree_patch=patch)
        result = self.apply()
        self.assertEqual(result["status"], "cleaned", result)
        expected = self.original.replace(b"foreign-before", b"foreign-staged")
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(self.gitrun("show", ":a.txt"), expected)

    def test_tampered_proof_cannot_rebind_trusted_ownership(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        proof = json.loads(self.journal.read_text())
        proof["after"]["a.txt"]["mode"] = 0o755
        proof["ownership_sha256"] = self.guard._ownership_hash(proof)
        self.journal.write_text(json.dumps(proof))
        before = self.state()
        self.assertEqual(self.apply()["status"], "blocked")
        self.assertEqual(self.state(), before)

    def test_partially_staged_ownership_blocks_capture_without_mutation(self):
        patch = self.prepare(second=True)
        before = self.state()
        with self.assertRaises(CleanupError):
            self.guard.capture(self.journal, identity=self.identity,
                               index_patch=patch[:patch.index(b"diff --git a/b.txt")],
                               worktree_patch=patch)
        self.assertEqual(self.state(), before)
        self.assertFalse(self.journal.exists())

    def test_staged_own_changes_require_explicit_index_ownership(self):
        patch = self.prepare()
        self.gitrun("add", "a.txt")
        before = self.state()
        with self.assertRaises(CleanupError):
            self.guard.capture(self.journal, identity=self.identity, worktree_patch=patch)
        self.assertEqual(self.state(), before)
        self.assertFalse(self.journal.exists())

    def test_new_adjacent_change_blocks_without_losing_any_files(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        path = self.repo / "a.txt"
        path.write_bytes(path.read_bytes().replace(b"foreign-before", b"new adjacent edit"))
        before = self.state()
        self.assertEqual(self.apply()["status"], "blocked")
        self.assertEqual(self.state(), before)

    def test_changed_index_blocks_without_losing_foreign_stage(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        (self.repo / "b.txt").write_bytes(b"new staged change\n")
        self.gitrun("add", "b.txt")
        before = self.state()
        self.assertEqual(self.apply()["status"], "blocked")
        self.assertEqual(self.state(), before)

    def test_already_integrated_head_never_reverse_applies(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        self.gitrun("read-tree", self.merge)
        self.gitrun("update-ref", "HEAD", self.merge)
        before = self.state()
        self.assertEqual(self.apply()["status"], "already-integrated")
        self.assertEqual(self.state(), before)

    def test_partial_retry_recovers_actual_postimage_after_interruption(self):
        patch = self.prepare(second=True)
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        calls = []
        def interrupted_observation():
            calls.append(True)
            if len(calls) == 3:
                raise OSError("scratch interruption after first owned file")
            return self.observation
        self.assertEqual(self.apply(observe=interrupted_observation)["status"], "blocked")
        self.assertEqual((self.repo / "a.txt").read_bytes(), self.original)
        self.assertEqual((self.repo / "b.txt").read_bytes(), b"second-after\n")
        self.assertEqual(json.loads(self.journal.read_text())["phase"], "applying")
        result = self.apply()
        self.assertEqual(result["status"], "cleaned", result)
        self.assertEqual((self.repo / "b.txt").read_bytes(), b"second-before\n")

    def test_wrong_attempt_pending_evidence_and_stale_destination_block(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        before = self.state()
        for field, value in (("attempt", "other"), ("destination_sha", self.base)):
            observation = dict(self.observation, **{field: value})
            self.assertEqual(self.apply(observe=lambda: observation)["status"], "blocked")
            self.assertEqual(self.state(), before)
        self.observation["evidence"] = dict(self.evidence, evidence_status="evidence-pending")
        self.assertEqual(self.apply()["status"], "blocked")
        self.assertEqual(self.state(), before)

    def test_unintegrated_destination_blocks_without_source_mutation(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        self.gitrun("update-ref", "refs/heads/integrated", self.base)
        self.observation["destination_sha"] = self.base
        before = self.state()
        self.assertEqual(self.apply()["status"], "blocked")
        self.assertEqual(self.state(), before)

    def test_deletion_decision_preserves_ignored_untracked_and_divergent_tip(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        self.assertEqual(self.apply()["status"], "cleaned")
        branch = self.gitrun("branch", "--show-current").decode().strip()
        ignored = self.repo / "ignored"
        ignored.mkdir()
        (ignored / "placeholder").write_bytes(b"harmless fixture credential placeholder")
        (self.repo / "untracked.txt").write_bytes(b"keep me")
        before = self.state()
        result = self.guard.deletion_decision(self.journal, authority=self.authority,
                                             observe=lambda: self.observation, branch=branch,
                                             session_created=True)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("ignored/placeholder", result["reason"])
        self.assertNotIn("harmless fixture credential placeholder", self.journal.read_text())
        self.assertEqual(self.state(), before)
        (self.repo / "untracked.txt").unlink()
        (ignored / "placeholder").unlink()
        ignored.rmdir()
        (self.repo / "b.txt").write_bytes(b"unintegrated local commit\n")
        self.gitrun("add", "b.txt")
        self.gitrun("commit", "-qm", "local only")
        before = self.state()
        result = self.guard.deletion_decision(self.journal, authority=self.authority,
                                             observe=lambda: self.observation, branch=branch,
                                             session_created=True)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.state(), before)


    def test_disposal_blocks_canceled_foreign_staged_content(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        self.assertEqual(self.apply()["status"], "cleaned")
        branch = self.gitrun("branch", "--show-current").decode().strip()
        path = self.repo / "b.txt"
        path.write_bytes(b"foreign staged only copy\n")
        self.gitrun("add", "b.txt")
        path.write_bytes(b"second-before\n")
        self.assertEqual(self.gitrun("diff", "HEAD", "--"), b"")
        self.assertTrue(self.gitrun("diff", "--cached", "HEAD", "--"))
        before = self.state()
        result = self.guard.deletion_decision(self.journal, authority=self.authority,
                                             observe=lambda: self.observation, branch=branch,
                                             session_created=True)
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(self.state(), before)

    def test_disposal_blocks_unintegrated_detached_workspace_head(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        self.assertEqual(self.apply()["status"], "cleaned")
        branch = self.gitrun("branch", "--show-current").decode().strip()
        self.gitrun("switch", "--detach", self.merge)
        safe = self.guard.deletion_decision(self.journal, authority=self.authority,
                                           observe=lambda: self.observation, branch=branch,
                                           session_created=True)
        self.assertEqual(safe["branch_decision"]["status"], "eligible", safe)
        self.assertEqual(safe["workspace_decision"]["status"], "blocked", safe)
        (self.repo / "b.txt").write_bytes(b"only detached commit retains this\n")
        self.gitrun("add", "b.txt")
        self.gitrun("commit", "-qm", "detached local work")
        before = self.state()
        result = self.guard.deletion_decision(self.journal, authority=self.authority,
                                             observe=lambda: self.observation, branch=branch,
                                             session_created=True)
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["branch_decision"]["status"], "eligible")
        self.assertEqual(result["workspace_decision"]["status"], "blocked")
        self.assertEqual(self.state(), before)

    def linked_guard(self, head):
        path = self.root / "linked-worktree"
        self.gitrun("worktree", "add", "--detach", str(path), head)
        return CleanupGuard(path, git=self.git, env=self.env)

    def test_committed_only_cleanup_needs_no_transfer_journal(self):
        self.own_change()
        self.gitrun("add", "a.txt")
        self.gitrun("commit", "-qm", "ordinary committed feature")
        destination = self.sha()
        branch = self.gitrun("branch", "--show-current").decode().strip()
        self.gitrun("update-ref", "refs/heads/integrated", destination)
        before = self.state()
        authority = DisposalAuthority("local-fixture", branch, "refs/heads/integrated", True, True,
                                      PostMergeInventory((), "current task host", "no post-merge tasks defined"))
        linked = self.linked_guard(destination)
        result = linked.disposal_decision(authority=authority,
                                          observe=lambda: {"repo": "local-fixture", "destination_sha": destination,
                                                              "post_merge_evidence": []},
                                             session_created=True)
        self.assertEqual(result["status"], "eligible", result)
        self.assertEqual(self.state(), before)
        self.assertFalse(self.journal.exists())


    def test_local_fast_forward_cleanup_uses_explicit_empty_task_inventory(self):
        base_branch = self.gitrun("branch", "--show-current").decode().strip()
        self.gitrun("switch", "-c", "feature")
        self.own_change()
        self.gitrun("add", "a.txt")
        self.gitrun("commit", "-qm", "committed local feature")
        self.gitrun("switch", base_branch)
        self.gitrun("merge", "--ff-only", "feature")
        destination = self.sha()
        authority = DisposalAuthority("local-fixture", "feature", "refs/heads/" + base_branch,
                                      True, True, PostMergeInventory((), "local task host", "no post-merge tasks"))
        observation = {"repo": "local-fixture", "destination_sha": destination, "post_merge_evidence": []}
        before = self.state()
        linked = self.linked_guard(destination)
        result = linked.disposal_decision(authority=authority, observe=lambda: observation,
                                             session_created=True)
        self.assertEqual(result["status"], "eligible", result)
        self.assertEqual(result["integration"]["evidence_status"], "not-applicable")
        self.assertEqual(self.state(), before)
        self.assertFalse(self.journal.exists())

    def test_unknown_inventory_or_json_permissions_cannot_authorize_disposal(self):
        branch = self.gitrun("branch", "--show-current").decode().strip()
        self.gitrun("update-ref", "refs/heads/integrated", self.base)
        observation = {"repo": "local-fixture", "destination_sha": self.base, "post_merge_evidence": [],
                       "inventory": [], "allow_branch_delete": True, "allow_workspace_remove": True}
        authority = DisposalAuthority("local-fixture", branch, "refs/heads/integrated", True, True, None)
        before = self.state()
        for current in (authority, {"repo": "local-fixture", "inventory": []}):
            result = self.guard.disposal_decision(authority=current, observe=lambda: observation,
                                                 session_created=True)
            self.assertEqual(result["status"], "blocked", result)
            self.assertEqual(self.state(), before)

    def test_committed_disposal_requires_each_actual_task_saved_evidence(self):
        patch = self.prepare()
        self.capture(self.journal, identity=self.identity, worktree_patch=patch)
        self.assertEqual(self.apply()["status"], "cleaned")
        branch = self.gitrun("branch", "--show-current").decode().strip()
        requirement = EvidenceRequirement(self.identity["pr"], self.identity["task"], self.identity["attempt"],
                                          self.merge, self.evidence["content_sha256"])
        authority = DisposalAuthority(self.identity["repo"], branch, "refs/heads/integrated", True, True,
                                      PostMergeInventory((requirement,), "current task host", "one post-merge task"))
        observation = {"repo": self.identity["repo"], "destination_sha": self.merge,
                       "post_merge_evidence": [self.evidence]}
        before = self.state()
        linked = self.linked_guard(self.merge)
        good = linked.disposal_decision(authority=authority, observe=lambda: observation,
                                           session_created=True)
        self.assertEqual(good["status"], "eligible", good)
        for records in ([], [dict(self.evidence, evidence_status="evidence-pending")],
                        [dict(self.evidence, attempt="other")]):
            observation["post_merge_evidence"] = records
            blocked = linked.disposal_decision(authority=authority, observe=lambda: observation,
                                                  session_created=True)
            self.assertEqual(blocked["status"], "blocked", blocked)
            self.assertEqual(self.state(), before)

    def test_retention_and_separate_disposal_permissions(self):
        self.gitrun("update-ref", "refs/heads/integrated", self.base)
        branch = self.gitrun("branch", "--show-current").decode().strip()
        self.gitrun("switch", "--detach", self.base)
        (self.repo / "b.txt").write_bytes(b"retained detached change\n")
        self.gitrun("add", "b.txt")
        self.gitrun("commit", "-qm", "detached retained change")
        self.gitrun("update-ref", "refs/heads/retained", self.sha())
        authority = DisposalAuthority("local-fixture", branch, "refs/heads/integrated", False, True,
                                      PostMergeInventory((), "current task host", "no post-merge tasks"),
                                      retained_head_ref="refs/heads/retained")
        observation = {"repo": "local-fixture", "destination_sha": self.base, "post_merge_evidence": []}
        before = self.state()
        linked = self.linked_guard(self.sha())
        result = linked.disposal_decision(authority=authority, observe=lambda: observation,
                                             session_created=True)
        self.assertEqual(result["branch_decision"]["status"], "blocked")
        self.assertEqual(result["workspace_decision"]["status"], "eligible")
        self.assertEqual(result["workspace_decision"]["head_proof"], "retained by refs/heads/retained")
        self.assertEqual(self.state(), before)


    def test_whole_clone_disposal_keeps_its_only_git_storage(self):
        branch = self.gitrun("branch", "--show-current").decode().strip()
        self.gitrun("update-ref", "refs/heads/integrated", self.base)
        self.gitrun("remote", "add", "origin", str(self.root / "never-published"))
        authority = DisposalAuthority("local-fixture", branch, "refs/heads/integrated", True, True,
                                      PostMergeInventory((), "current handoff", "no post-merge tasks"))
        observation = {"repo": "local-fixture", "destination_sha": self.base, "post_merge_evidence": []}
        before = self.state()
        result = self.guard.disposal_decision(authority=authority, observe=lambda: observation,
                                             session_created=True)
        self.assertEqual(result["branch_decision"]["status"], "eligible", result)
        self.assertEqual(result["workspace_decision"]["status"], "blocked", result)
        self.assertEqual(self.state(), before)

    def test_whole_clone_retained_ref_is_not_external_retention(self):
        branch = self.gitrun("branch", "--show-current").decode().strip()
        self.gitrun("update-ref", "refs/heads/integrated", self.base)
        self.gitrun("switch", "--detach", self.base)
        (self.repo / "b.txt").write_bytes(b"only local retained ref copy\n")
        self.gitrun("add", "b.txt")
        self.gitrun("commit", "-qm", "retained only inside clone")
        self.gitrun("update-ref", "refs/heads/retained", self.sha())
        authority = DisposalAuthority("local-fixture", branch, "refs/heads/integrated", True, True,
                                      PostMergeInventory((), "current handoff", "no post-merge tasks"),
                                      retained_head_ref="refs/heads/retained")
        observation = {"repo": "local-fixture", "destination_sha": self.base, "post_merge_evidence": []}
        before = self.state()
        result = self.guard.disposal_decision(authority=authority, observe=lambda: observation,
                                             session_created=True)
        self.assertEqual(result["branch_decision"]["status"], "eligible", result)
        self.assertEqual(result["workspace_decision"]["status"], "blocked", result)
        self.assertEqual(self.state(), before)


    def test_linked_workspace_storage_survives_and_detached_new_work_is_blocked(self):
        branch = self.gitrun("branch", "--show-current").decode().strip()
        self.gitrun("update-ref", "refs/heads/integrated", self.base)
        linked = self.linked_guard(self.base)
        authority = DisposalAuthority("local-fixture", branch, "refs/heads/integrated", True, True,
                                      PostMergeInventory((), "current handoff", "no post-merge tasks"))
        observation = {"repo": "local-fixture", "destination_sha": self.base, "post_merge_evidence": []}
        before = self.state()
        result = linked.disposal_decision(authority=authority, observe=lambda: observation,
                                          session_created=True)
        self.assertEqual(result["status"], "eligible", result)
        self.assertFalse(Path(result["workspace_decision"]["common_git_dir"]).is_relative_to(linked.repo))
        self.assertEqual(self.state(), before)
        path = linked.repo / "b.txt"
        path.write_bytes(b"unintegrated detached linked work\n")
        linked._git("add", "b.txt")
        linked._git("commit", "-qm", "new detached linked work")
        result = linked.disposal_decision(authority=authority, observe=lambda: observation,
                                          session_created=True)
        self.assertEqual(result["branch_decision"]["status"], "eligible", result)
        self.assertEqual(result["workspace_decision"]["status"], "blocked", result)
        self.assertEqual(path.read_bytes(), b"unintegrated detached linked work\n")
        self.assertEqual(self.state(), before)



if __name__ == "__main__":
    unittest.main()
