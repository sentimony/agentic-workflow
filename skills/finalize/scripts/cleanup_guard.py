"""Bounded local cleanup of explicitly owned regular-file content patches.

The trusted host serializes this repository for the entire call. Fresh rereads detect
changed state; they are not an OS lock against hostile concurrent file writers.
"""
from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit


class CleanupError(ValueError):
    """Missing ownership proof or unsupported/changed local state."""


@dataclass(frozen=True)
class CleanupAuthority:
    """Current trusted invocation authority, never decoded from observation JSON."""
    repo: str
    pr: int
    task: str
    attempt: str
    merge_sha: str
    allow_cleanup: bool
    destination_ref: str = "refs/heads/integrated"
    ownership_sha256: str = ""


@dataclass(frozen=True)
class EvidenceRequirement:
    pr: int
    task: str
    attempt: str
    merge_sha: str
    content_sha256: str


@dataclass(frozen=True)
class PostMergeInventory:
    """Explicit trusted host inventory; unknown inventory is never an empty one."""
    tasks: tuple
    source: str
    reason: str


@dataclass(frozen=True)
class DisposalAuthority:
    """Current disposal permissions and inventory, separate from observations."""
    repo: str
    branch: str
    destination_ref: str
    allow_branch_delete: bool
    allow_workspace_remove: bool
    inventory: PostMergeInventory
    retained_head_ref: str | None = None


def _require(value, reason):
    if not value:
        raise CleanupError(reason)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _encode(data):
    return base64.b64encode(data).decode("ascii")


def _decode(data):
    return base64.b64decode(data, validate=True)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class CleanupGuard:
    def __init__(self, repo, *, git, env):
        self.repo = Path(repo).resolve(strict=True)
        self.git, self.env = git, dict(env)
        _require(self._name("rev-parse", "--show-toplevel") == str(self.repo), "repository root required")
        self.index = Path(self._name("rev-parse", "--path-format=absolute", "--git-path", "index"))

    def _git(self, *args, data=None, index=None):
        env = {k: v for k, v in self.env.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS="0")
        for key in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            if key in self.env:
                env[key] = self.env[key]
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        result = subprocess.run([self.git, "-c", "diff.autoRefreshIndex=false", "-C", str(self.repo), *args], input=data,
                                env=env, capture_output=True, check=False)
        _require(result.returncode == 0, "Git operation failed: " + args[0])
        return result.stdout

    def _name(self, *args, **kwargs):
        # Names/SHA only. Patch bytes always use _git without whitespace trimming.
        return self._git(*args, **kwargs).decode().rstrip("\n")

    def _safe_file(self, name):
        _require(re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", name)
                 and all(p not in (".", "..", ".git") for p in name.split("/")), "unsupported patch path")
        path = self.repo / name
        _require(path.resolve() == path and path.is_file() and not path.is_symlink(), "regular file required")
        return path

    def _snapshot(self, name):
        path = self._safe_file(name)
        mode = stat.S_IMODE(path.stat().st_mode)
        _require(mode in (0o644, 0o755), "unsupported file permissions")
        return {"data": _encode(path.read_bytes()), "mode": mode}

    def _paths(self, patch):
        _require(type(patch) is bytes, "patch must be unchanged raw bytes")
        if not patch:
            return []
        _require(not re.search(rb"^(?:new file mode|deleted file mode|old mode|new mode|rename |copy |GIT binary patch|Binary files)", patch, re.M),
                 "only existing regular-file content patches supported")
        headers = re.findall(rb"^diff --git a/(\S+) b/(\S+)\n", patch, re.M)
        _require(headers and patch.count(b"diff --git ") == len(headers), "unsupported patch headers")
        names = []
        for left, right in headers:
            _require(left == right, "renames unsupported")
            name = left.decode("ascii")
            self._safe_file(name)
            names.append(name)
        _require(len(set(names)) == len(names), "duplicate patch paths")
        return names

    def _inventory(self):
        return {"untracked": self._git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")[:-1],
                "ignored": self._git("ls-files", "--others", "--ignored", "--exclude-standard", "-z").decode().split("\0")[:-1]}

    def _persist(self, path, proof):
        path = Path(path).absolute()
        _require(path.resolve() == path and self.repo not in path.parents, "journal must be outside source workspace")
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".cleanup-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(_json(proof))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def capture(self, journal, *, identity, index_patch=b"", worktree_patch):
        _require(set(identity) == {"repo", "pr", "task", "attempt"}, "exact task identity required")
        _require(not Path(journal).exists(), "existing cleanup journal must be retried")
        _require(not index_patch or index_patch == worktree_patch, "partially staged ownership unsupported")
        paths = sorted(set(self._paths(index_patch) + self._paths(worktree_patch)))
        _require(paths and worktree_patch, "owned worktree patch required")
        head = self._name("rev-parse", "HEAD")
        index_before = self.index.read_bytes()
        before = {name: self._snapshot(name) for name in paths}
        # Reject unmerged entries, symlink/submodule modes and untracked owned paths.
        for name in paths:
            entry = self._git("ls-files", "--stage", "--", name)
            _require(re.fullmatch(rb"100(?:644|755) [0-9a-f]+ 0\t[^\n]+\n", entry), "regular tracked index entry required")
        with tempfile.TemporaryDirectory() as temporary:
            idx = Path(temporary) / "index"
            idx.write_bytes(index_before)
            if index_patch:
                self._git("apply", "--cached", "--reverse", "--whitespace=nowarn", data=index_patch, index=idx)
            if not index_patch:
                try:
                    self._git("apply", "--cached", "--reverse", "--check", data=worktree_patch, index=idx)
                except CleanupError:
                    pass
                else:
                    raise CleanupError("staged ownership requires an explicit index patch")
            index_after = idx.read_bytes()
            idx.unlink()
            self._git("read-tree", head, index=idx)
            for name, saved in before.items():
                blob = self._name("hash-object", "-w", "--stdin", data=_decode(saved["data"]))
                mode = "100755" if saved["mode"] == 0o755 else "100644"
                self._git("update-index", "--cacheinfo", mode + "," + blob + "," + name, index=idx)
            self._git("apply", "--cached", "--reverse", "--whitespace=nowarn", data=worktree_patch, index=idx)
            after = {name: {"data": _encode(self._git("show", ":" + name, index=idx)),
                            "mode": saved["mode"]} for name, saved in before.items()}
            idx.unlink()
            self._git("read-tree", head, index=idx)
            # Bind the exact owned patch to a transferred tree, excluding foreign changes.
            self._git("apply", "--cached", "--whitespace=nowarn", data=worktree_patch, index=idx)
            projected_tree = self._name("write-tree", index=idx)
        proof = {"schema": "cleanup-proof-v1", "root": str(self.repo), "identity": dict(identity),
                 "source_head": head, "projected_tree": projected_tree,
                 "patches": {"index": _encode(index_patch), "worktree": _encode(worktree_patch)},
                 "patch_sha256": {"index": _sha(index_patch), "worktree": _sha(worktree_patch)},
                 "index_before": _encode(index_before), "index_after": _encode(index_after),
                 "before": before, "after": after, "artifacts": self._inventory(),
                 "phase": "captured", "completed": [], "integration": None, "postflight": None}
        proof["ownership_sha256"] = self._ownership_hash(proof)
        self._persist(journal, proof)
        return proof

    @staticmethod
    def _ownership_hash(proof):
        keys = ("schema", "root", "identity", "source_head", "projected_tree", "patches",
                "patch_sha256", "index_before", "index_after", "before", "after", "artifacts")
        return _sha(_json({key: proof[key] for key in keys}))

    def _gate(self, proof, authority, observe):
        _require(type(authority) is CleanupAuthority and authority.allow_cleanup is True, "current cleanup authority required")
        _require(authority.ownership_sha256 == proof["ownership_sha256"] == self._ownership_hash(proof), "trusted ownership binding mismatch")
        identity = proof["identity"]
        _require(all(getattr(authority, key) == value for key, value in identity.items()), "authority identity mismatch")
        observation = observe()
        _require(type(observation) is dict and all(observation.get(k) == v for k, v in identity.items()), "integration identity mismatch")
        merge = observation.get("merge_sha")
        destination = observation.get("destination_sha")
        _require(merge == authority.merge_sha and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", merge or ""), "merge identity mismatch")
        _require(authority.destination_ref.startswith("refs/heads/"), "local destination ref required")
        _require(self._name("rev-parse", authority.destination_ref) == destination, "stale destination observation")
        self._git("merge-base", "--is-ancestor", merge, destination)
        record = observation.get("evidence", {})
        self._verify_evidence(record, identity, merge)
        projected = self._name("-c", "user.name=Cleanup guard", "-c", "user.email=cleanup@example.invalid",
                               "commit-tree", proof["projected_tree"], "-p", proof["source_head"], data=b"Cleanup integration proof\n")
        merged_tree = self._name("merge-tree", "--write-tree", destination, projected)
        _require(merged_tree == self._name("rev-parse", destination + "^{tree}"), "owned patch not integrated")
        return {"merge_sha": merge, "destination_sha": destination, "destination_ref": authority.destination_ref,
                "canonical_url": record["canonical_url"], "content_sha256": record["content_sha256"]}

    def _verify_evidence(self, record, identity, merge):
        _require(type(record) is dict and record.get("schema") == "evidence-record-v1"
                 and all(record.get(k) == v for k, v in identity.items()) and record.get("merge_sha") == merge,
                 "evidence identity mismatch")
        keys = {"schema", "repo", "pr", "task", "attempt", "merge_sha", "deployment", "timestamp",
                "checks", "production_status", "author", "previous_attempt"}
        _require(keys <= record.keys() and _sha(_json({k: record[k] for k in keys})) == record.get("content_sha256"), "evidence content mismatch")
        url = urlsplit(record.get("canonical_url") or "")
        _require(record.get("evidence_status") == "published" and url.scheme == "https"
                 and url.netloc == identity["repo"].split("/")[0] and bool(url.path.strip("/")), "canonical evidence required")
        saved = json.loads(Path(record["local_pending_path"]).read_text())
        _require(saved.get("record") == record, "saved evidence mismatch")

    def _load(self, journal):
        proof = json.loads(Path(journal).read_text())
        _require(proof.get("schema") == "cleanup-proof-v1" and proof.get("root") == str(self.repo), "wrong cleanup proof")
        for key in ("index", "worktree"):
            _require(_sha(_decode(proof["patches"][key])) == proof["patch_sha256"][key], "patch hash mismatch")
        return proof

    def _states(self, proof):
        current_index = self.index.read_bytes()
        _require(current_index in (_decode(proof["index_before"]), _decode(proof["index_after"])), "index changed")
        for name in proof["before"]:
            _require(self._snapshot(name) in (proof["before"][name], proof["after"][name]), "owned path changed: " + name)
        return current_index

    def apply_cleanup(self, journal, *, authority, observe):
        """Recheck authority, fresh integration and source state inside every call."""
        try:
            proof = self._load(journal)
            integration = self._gate(proof, authority, observe)
            current = self._name("rev-parse", "HEAD")
            if current != proof["source_head"]:
                if (self._name("rev-parse", "HEAD^{tree}") == proof["projected_tree"]
                        and not self._git("diff", "HEAD", "--", *proof["before"])
                        and not self._git("diff", "--cached", "HEAD", "--", *proof["before"])):
                    return {"status": "already-integrated", "current_head": current}
                raise CleanupError("source HEAD changed")
            self._states(proof)
            _require(not Path(str(self.index) + ".lock").exists(), "index is locked")
            if proof["phase"] == "captured":
                _require(self.index.read_bytes() == _decode(proof["index_before"])
                         and all(self._snapshot(p) == proof["before"][p] for p in proof["before"]), "initial source state changed")
            proof.update(phase="applying", integration=integration)
            self._persist(journal, proof)
            for name, expected in proof["after"].items():
                self._gate(proof, authority, observe)
                _require(self._name("rev-parse", "HEAD") == proof["source_head"], "source HEAD changed")
                self._states(proof)
                if self._snapshot(name) != expected:
                    path = self._safe_file(name)
                    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".cleanup-")
                    try:
                        with os.fdopen(fd, "wb") as stream:
                            stream.write(_decode(expected["data"]))
                            stream.flush()
                            os.fchmod(stream.fileno(), expected["mode"])
                            os.fsync(stream.fileno())
                        os.replace(temporary, path)
                    finally:
                        if os.path.exists(temporary):
                            os.unlink(temporary)
                proof["completed"] = sorted(set(proof["completed"] + [name]))
                self._persist(journal, proof)
            self._gate(proof, authority, observe)
            _require(self._name("rev-parse", "HEAD") == proof["source_head"], "source HEAD changed")
            self._states(proof)
            if self.index.read_bytes() != _decode(proof["index_after"]):
                lock = Path(str(self.index) + ".lock")
                fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        _require(self.index.read_bytes() == _decode(proof["index_before"]), "index changed before replacement")
                        stream.write(_decode(proof["index_after"]))
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(lock, self.index)
                finally:
                    if lock.exists():
                        lock.unlink()
            _require(all(self._snapshot(p) == proof["after"][p] for p in proof["after"])
                     and self.index.read_bytes() == _decode(proof["index_after"]), "postflight mismatch")
            proof.update(phase="cleaned", current_head=current,
                         postflight={"owned_postimages": True, "index_postimage": True,
                                     "preserved_artifacts": self._inventory()})
            self._persist(journal, proof)
            return {"status": "cleaned", "proof": proof}
        except (CleanupError, OSError, ValueError, KeyError, TypeError) as error:
            return {"status": "blocked", "reason": str(error), "journal": str(journal)}

    def _integrated(self, destination, tip):
        tree = self._name("merge-tree", "--write-tree", destination, tip)
        _require(tree == self._name("rev-parse", destination + "^{tree}"), "tip not integrated")

    def _common_git_dir(self):
        common = Path(self._name("rev-parse", "--path-format=absolute", "--git-common-dir")).resolve(strict=True)
        _require(common.is_dir(), "common Git directory unavailable")
        return common

    def _disposal_checks(self, integration, *, branch, session_created,
                         allow_branch=True, allow_workspace=True, retained_head_ref=None):
        """Separate ref disposal from the current checkout's preservation checks."""
        _require(type(branch) is str and branch and not branch.startswith("-"), "invalid branch")
        self._git("check-ref-format", "refs/heads/" + branch)
        tip = self._name("rev-parse", "refs/heads/" + branch)
        head = self._name("rev-parse", "HEAD")
        index_hash = _sha(self.index.read_bytes())
        artifacts = self._inventory()
        common = self._common_git_dir()
        branch_result = {"status": "eligible", "tip": tip}
        workspace_result = {"status": "eligible", "head": head, "removal_root": str(self.repo),
                            "common_git_dir": str(common)}
        try:
            _require(allow_branch is True, "branch deletion not authorized")
            _require(integration.get("destination_ref") != "refs/heads/" + branch, "destination ref must survive branch deletion")
            self._integrated(integration["destination_sha"], tip)
        except CleanupError as error:
            branch_result.update(status="blocked", reason=str(error))
        try:
            _require(allow_workspace is True, "workspace removal not authorized")
            _require(session_created is True, "workspace not created by this session")
            _require(not artifacts["untracked"] and not artifacts["ignored"],
                     "preserve ignored/untracked resources: " + repr(artifacts))
            _require(not self._git("diff", "--cached", "HEAD", "--")
                     and not self._git("diff", "--")
                     and not self._git("ls-files", "--unmerged"), "preserve index/worktree changes")
            _require(common != self.repo and self.repo not in common.parents,
                     "preserve whole-clone Git storage inside removal root: " + str(self.repo))
            try:
                self._integrated(integration["destination_sha"], head)
                workspace_result["head_proof"] = "integrated"
            except CleanupError:
                _require(type(retained_head_ref) is str and retained_head_ref.startswith("refs/heads/")
                         and retained_head_ref != "refs/heads/" + branch,
                         "workspace HEAD not integrated or retained")
                _require(self._name("rev-parse", retained_head_ref) == head,
                         "workspace HEAD retention ref changed")
                workspace_result["head_proof"] = "retained by " + retained_head_ref
        except CleanupError as error:
            workspace_result.update(status="blocked", reason=str(error))
        _require(self._name("rev-parse", "HEAD") == head
                 and self._name("rev-parse", "refs/heads/" + branch) == tip
                 and _sha(self.index.read_bytes()) == index_hash
                 and self._inventory() == artifacts and self._common_git_dir() == common
                 and self._name("rev-parse", integration["destination_ref"]) == integration["destination_sha"],
                 "disposal state or Git storage boundary changed during checks")
        if workspace_result.get("head_proof", "").startswith("retained by "):
            _require(self._name("rev-parse", retained_head_ref) == head, "workspace HEAD retention ref changed")
        blocked = [v["reason"] for v in (branch_result, workspace_result) if v["status"] == "blocked"]
        result = {"status": "blocked" if blocked else "eligible", "tip": tip,
                  "branch_decision": branch_result, "workspace_decision": workspace_result,
                  "integration": integration}
        if blocked:
            result["reason"] = "; ".join(blocked)
        return result

    def deletion_decision(self, journal, *, authority, observe, branch, session_created=False):
        """Transfer-compatible decision API; the journal remains required here."""
        try:
            proof = self._load(journal)
            integration = self._gate(proof, authority, observe)
            return self._disposal_checks(integration, branch=branch, session_created=session_created)
        except (CleanupError, OSError, ValueError, KeyError, TypeError) as error:
            return {"status": "blocked", "reason": str(error), "workspace": str(self.repo), "branch": branch}

    def disposal_decision(self, *, authority, observe, session_created=False):
        """Committed-only/local-merge disposal; no patch, PR or deployment is invented."""
        try:
            _require(type(authority) is DisposalAuthority, "current disposal authority required")
            inventory = authority.inventory
            _require(type(inventory) is PostMergeInventory and type(inventory.tasks) is tuple
                     and type(inventory.source) is str and bool(inventory.source.strip())
                     and type(inventory.reason) is str and bool(inventory.reason.strip()),
                     "explicit trusted post-merge task inventory required")
            _require(all(type(task) is EvidenceRequirement for task in inventory.tasks), "invalid task inventory")
            observation = observe()
            _require(type(observation) is dict and observation.get("repo") == authority.repo,
                     "disposal repository identity mismatch")
            _require(authority.destination_ref.startswith("refs/heads/"), "local destination ref required")
            destination = self._name("rev-parse", authority.destination_ref)
            _require(destination == observation.get("destination_sha"), "stale destination observation")
            records = observation.get("post_merge_evidence")
            _require(type(records) is list and len(records) == len(inventory.tasks), "task evidence inventory mismatch")
            seen = set()
            for task in inventory.tasks:
                key = (task.pr, task.task, task.attempt)
                _require(key not in seen, "duplicate task inventory")
                seen.add(key)
                matches = [record for record in records if type(record) is dict
                           and (record.get("pr"), record.get("task"), record.get("attempt")) == key]
                _require(len(matches) == 1, "missing or ambiguous task evidence")
                record = matches[0]
                self._verify_evidence(record, {"repo": authority.repo, "pr": task.pr,
                                               "task": task.task, "attempt": task.attempt}, task.merge_sha)
                _require(record["content_sha256"] == task.content_sha256, "task evidence content changed")
                self._git("merge-base", "--is-ancestor", task.merge_sha, destination)
            integration = {"destination_sha": destination, "destination_ref": authority.destination_ref,
                           "evidence_status": "verified" if inventory.tasks else "not-applicable",
                           "inventory_source": inventory.source, "inventory_reason": inventory.reason}
            result = self._disposal_checks(integration, branch=authority.branch,
                                          session_created=session_created,
                                          allow_branch=authority.allow_branch_delete,
                                          allow_workspace=authority.allow_workspace_remove,
                                          retained_head_ref=authority.retained_head_ref)
            _require(self._name("rev-parse", authority.destination_ref) == destination,
                     "destination changed during disposal checks")
            return result
        except (CleanupError, OSError, ValueError, KeyError, TypeError) as error:
            return {"status": "blocked", "reason": str(error), "workspace": str(self.repo)}
