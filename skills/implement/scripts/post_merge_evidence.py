"""Durable local evidence with an injected, explicitly authorized comment transport.

No forge adapter, shell execution, or production action. Git is used only to locate
the main checkout and, for a legacy in-project store, to verify that it is ignored.
Publication status is independent of production.
One trusted host must serialize calls for a repo/PR/task/attempt.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit


class EvidenceError(ValueError):
    """Invalid evidence, identity, or ambiguous canonical state."""


class TransportError(Exception):
    """Unavailable transport, including a write whose outcome is unknown."""


@dataclass(frozen=True)
class PublicationAuthority:
    """Trusted current-invocation authority; never deserialize from evidence JSON."""

    repo: str
    pr: int
    task: str
    attempt: str
    author_id: int
    author_login: str
    content_sha256: str
    allow_publish: bool


CONTENT_KEYS = {"schema", "repo", "pr", "task", "attempt", "merge_sha", "deployment",
                "timestamp", "checks", "production_status", "author", "previous_attempt"}
PUBLICATION_KEYS = {"content_sha256", "evidence_status", "canonical_url", "local_pending_path", "history"}


def _require(condition, reason):
    if not condition:
        raise EvidenceError(reason)


def _text(value):
    return (type(value) is str and bool(value.strip()) and len(value) <= 65536
            and not any(ord(char) < 32 and char not in "\n\t" for char in value))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _key(record):
    return {key: record[key] for key in ("repo", "pr", "task", "attempt")}


def _content(record):
    return {key: deepcopy(record[key]) for key in CONTENT_KEYS}


def _validate(record):
    _require(type(record) is dict and set(record) == CONTENT_KEYS, "invalid content fields")
    _require(record["schema"] == "evidence-record-v1", "invalid evidence schema")
    _require(type(record["repo"]) is str and re.fullmatch(
        r"[a-z0-9.-]+/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", record["repo"]), "invalid repo")
    _require(type(record["pr"]) is int and record["pr"] > 0, "invalid PR")
    for key in ("task", "attempt"):
        _require(_text(record[key]) and "\n" not in record[key], "invalid " + key)
    _require(type(record["merge_sha"]) is str and re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", record["merge_sha"]), "invalid merge SHA")
    deployment = record["deployment"]
    _require(type(deployment) is dict and set(deployment) == {"id", "version"}
             and all(_text(v) for v in deployment.values()), "invalid deployment identity")
    timestamp = record["timestamp"]
    try:
        valid_time = type(timestamp) in (int, float) and math.isfinite(timestamp) and timestamp >= 0
    except OverflowError:
        valid_time = False
    _require(valid_time, "invalid timestamp")
    _require(record["production_status"] in ("succeeded", "failed", "unknown"), "invalid production status")
    author = record["author"]
    _require(type(author) is dict and set(author) == {"id", "login"}
             and type(author["id"]) is int and author["id"] > 0 and _text(author["login"]), "invalid author")
    checks = record["checks"]
    _require(type(checks) is list and bool(checks), "checks/results required")
    for check in checks:
        _require(type(check) is dict and set(check) == {"command", "result"}
                 and all(_text(v) for v in check.values()), "invalid check result")
    previous = record["previous_attempt"]
    if previous is not None:
        _require(type(previous) is dict and set(previous) == {"key", "content_sha256", "canonical_url"},
                 "invalid previous attempt")
        _require(type(previous["key"]) is dict and set(previous["key"]) == set(_key(record)),
                 "invalid previous attempt key")
        _require(all(previous["key"][k] == record[k] for k in ("repo", "pr", "task"))
                 and previous["key"]["attempt"] != record["attempt"]
                 and _text(previous["key"]["attempt"]), "previous attempt identity mismatch")
        _require(type(previous["content_sha256"]) is str and re.fullmatch(
            r"[0-9a-f]{64}", previous["content_sha256"]), "invalid previous content hash")
        _require(previous["canonical_url"] is None or _valid_url(previous["canonical_url"], record["repo"]),
                 "invalid previous canonical URL")


def _valid_url(url, repo):
    if type(url) is not str:
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.netloc == repo.split("/")[0]
                and bool(parsed.path.strip("/")) and not parsed.username and not parsed.password)
    except ValueError:
        return False


STATE_PARTS = (".sentimony", "agentflow", "implement")


def project_key(repo):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    done = subprocess.run(["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                          env=env, capture_output=True, text=True, check=False)
    _require(done.returncode == 0, "cannot read the Git common directory")
    common = Path(os.path.realpath(done.stdout.rstrip("\n")))
    return common.parent if common.name == ".git" else common


def slug(path):
    """Same algorithm as slug() in context-transfer; every skill carries its own copy."""
    resolved = str(Path(path).resolve())
    digest = hashlib.sha256(os.fsencode(resolved)).hexdigest()[:12]
    name, size = "", 0
    for char in Path(resolved).name or "root":
        size += len(os.fsencode(char))
        if size > 64:
            break
        name += char
    return name + "-" + digest


def _populated(folder):
    # A bare snapshot is not pending state: only an envelope decides which store a retry continues in.
    return folder.is_dir() and any(not item.name.startswith("snapshot-") for item in folder.glob("*.json"))


class PendingStore:
    """Atomic, fsynced state and immutable content snapshots in ~/.sentimony/agentflow/implement/<project>/.

    A populated legacy folder inside the repository keeps being used until the new location
    holds data; then the new one wins and ``unused_legacy`` names the old folder.
    """

    def __init__(self, repo_root, *, home=None, directory=".delivery-evidence"):
        self.repo = Path(repo_root).resolve(strict=True)
        _require(type(directory) is str and directory.startswith(".") and "/" not in directory
                 and directory not in (".", "..", ".git"), "invalid store directory")
        self._git("rev-parse", "--show-toplevel", expected=str(self.repo))
        text = os.fspath(home) if home is not None else os.environ.get("HOME", "")
        _require(bool(text) and os.path.isabs(text) and os.path.isdir(text), "HOME is not usable for the evidence store")
        self.base = Path(text).resolve(strict=True)
        _require(self.repo != self.base and self.repo not in self.base.parents,
                 "HOME must be outside the project, so the store writes nothing into it")
        names = (*STATE_PARTS, slug(project_key(self.repo)))
        new_root, legacy_root = self.base.joinpath(*names), self.repo / directory
        self.unused_legacy = None
        self.legacy = not _populated(new_root) and _populated(legacy_root)
        self.root = legacy_root if self.legacy else new_root
        if not self.legacy and _populated(legacy_root):
            self.unused_legacy = legacy_root
        if self.legacy:
            self._ignored(self.root / ".ignore-proof")
            self._safe(self.root)
            self.root.mkdir(mode=0o700, exist_ok=True)
        else:
            self._safe(self.root)
            self._make_private(names)

    def _make_private(self, names):
        # Path-based checks, like the rest of this store: a same-user process swapping a component
        # between the check and the use is outside the cooperative threat model of this helper.
        current = self.base
        for name in names:
            current = current / name
            _require(not current.is_symlink(), "symlink evidence path")
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            except OSError:
                raise EvidenceError("cannot create the evidence store") from None
            info = current.lstat()
            _require(stat.S_ISDIR(info.st_mode), "evidence store component is not a directory")
            _require(info.st_uid == os.getuid(), "evidence store belongs to another user")
            if info.st_mode & 0o077:
                current.chmod(0o700)

    def _git(self, *args, expected=None):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        result = subprocess.run(["git", "-C", str(self.repo), *args], env=env,
                                capture_output=True, text=True, check=False)
        _require(result.returncode == 0, "local Git store validation failed")
        if expected is not None:
            _require(result.stdout.rstrip("\n") == expected, "store must use repository root")

    def _safe(self, path):
        path = Path(path)
        top = self.repo if self.legacy else self.base
        _require(path.is_absolute() and self.root in (path, *path.parents), "path outside evidence store")
        _require(path.resolve(strict=False) == path, "symlink or noncanonical evidence path")
        for component in (path, *path.parents):
            if component == top:
                break
            _require(not component.is_symlink(), "symlink evidence path")
        return path

    def _ignored(self, path):
        if self.legacy:
            self._git("check-ignore", "--quiet", "--", str(path.relative_to(self.repo)))

    def path_for(self, key):
        return self.root / (_hash(key) + ".json")

    def _write(self, path, value, *, immutable=False):
        path = self._safe(path)
        self._ignored(path)
        data = (_json(value) + "\n").encode()
        fd, name = tempfile.mkstemp(prefix=".pending-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if immutable:
                try:
                    os.link(name, path)
                except FileExistsError:
                    _require(path.read_bytes() == data, "immutable evidence changed")
            else:
                os.replace(name, path)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def load(self, path):
        path = self._safe(path)
        self._ignored(path)
        state = json.loads(path.read_text())
        _require(type(state) is dict and set(state) == {"record", "write_state", "comment_id", "reason"},
                 "invalid pending envelope")
        record = state["record"]
        _require(type(record) is dict and set(record) == CONTENT_KEYS | PUBLICATION_KEYS, "invalid saved record")
        _validate(_content(record))
        _require(record["content_sha256"] == _hash(_content(record)), "saved content hash mismatch")
        _require(path == self.path_for(_key(record)) and record["local_pending_path"] == str(path),
                 "saved path mismatch")
        _require(state["write_state"] in ("never", "uncertain", "confirmed"), "invalid write state")
        _require(state["comment_id"] is None or (type(state["comment_id"]) is int
                 and state["comment_id"] > 0), "invalid comment ID")
        _require(record["evidence_status"] in ("evidence-pending", "published"), "invalid evidence status")
        _require(record["canonical_url"] is None or _valid_url(record["canonical_url"], record["repo"]),
                 "invalid saved canonical URL")
        _require(type(record["history"]) is list and all(type(h) is str and re.fullmatch(
            r"[0-9a-f]{64}", h) for h in record["history"]), "invalid revision history")
        return state

    def save(self, state):
        record = state["record"]
        self._write(self.path_for(_key(record)), state)

    def snapshot(self, record):
        content = _content(record)
        self._write(self.root / ("snapshot-" + _hash(content) + ".json"), content, immutable=True)


def previous_attempt(record):
    """Link a new attempt to the immutable desired content of an existing attempt."""
    return {"key": _key(record), "content_sha256": record["content_sha256"],
            "canonical_url": record["canonical_url"]}


def prepare(record, *, store):
    """Persist pending evidence before any publication; never write tracked hosts."""
    content = deepcopy(record)
    _validate(content)
    path = store.path_for(_key(content))
    prior = store.load(path) if path.exists() else None
    previous = content["previous_attempt"]
    if previous is not None:
        old = store.load(store.path_for(previous["key"]))["record"]
        _require(previous == previous_attempt(old), "previous attempt proof mismatch")
        store.snapshot(old)
    digest = _hash(content)
    if prior is not None and prior["record"]["content_sha256"] == digest:
        return path
    history = [] if prior is None else prior["record"]["history"] + [prior["record"]["content_sha256"]]
    store.snapshot(content)
    current = dict(content, content_sha256=digest, evidence_status="evidence-pending",
                   canonical_url=None, local_pending_path=str(path), history=history)
    state = {"record": current, "write_state": "never" if prior is None else prior["write_state"],
             "comment_id": None if prior is None else prior["comment_id"], "reason": "not-published"}
    store.save(state)
    return path


def _body(record):
    return "<!-- agentflow-evidence:v1 " + _hash(_key(record)) + " -->\n" + _json(_content(record))


def _own_comment(comment, record):
    _require(type(comment) is dict and set(comment) == {
        "id", "url", "repo", "pr", "author_id", "author_login", "body"}, "malformed comment")
    _require(type(comment["id"]) is int and comment["id"] > 0
             and _valid_url(comment["url"], record["repo"]), "invalid canonical comment identity")
    _require(type(comment["pr"]) is int and type(comment["author_id"]) is int
             and type(comment["author_login"]) is str and type(comment["repo"]) is str,
             "invalid canonical metadata types")
    _require((comment["repo"], comment["pr"], comment["author_id"], comment["author_login"])
             == (record["repo"], record["pr"], record["author"]["id"], record["author"]["login"]),
             "canonical comment ownership mismatch")
    prefix = "<!-- agentflow-evidence:v1 " + _hash(_key(record)) + " -->\n"
    _require(type(comment["body"]) is str and comment["body"].startswith(prefix), "invalid comment marker")
    content = json.loads(comment["body"][len(prefix):])
    _validate(content)
    _require(_key(content) == _key(record) and content["author"] == record["author"], "comment content identity mismatch")
    return content


def publish(path, *, store, transport, authority=None):
    """Publish through local callbacks only; every retry looks up canonical state.

    Transport methods: current_author(), lookup(repo, pr, key_hash),
    create(repo, pr, body, key_hash), update(comment_id, body), read(comment_id).
    lookup returns complete, absence_confirmed, matches; absence_confirmed must mean
    authoritative absence after all earlier writes settled, never an empty page.
    Writes return a comment ID. TransportError means unavailable/unknown outcome.
    """
    state = store.load(path)
    record = state["record"]
    # A crash or failed read after this point must never leave a published claim.
    record["evidence_status"] = "evidence-pending"
    record["canonical_url"] = None
    store.save(state)
    try:
        _require(type(authority) is PublicationAuthority and authority.allow_publish is True,
                 "publication not authorized")
        _require((authority.repo, authority.pr, authority.task, authority.attempt,
                  authority.author_id, authority.author_login, authority.content_sha256)
                 == (record["repo"], record["pr"], record["task"], record["attempt"],
                     record["author"]["id"], record["author"]["login"], record["content_sha256"]),
                 "publication authority mismatch")
        actor = transport.current_author()
        _require(type(actor) is dict and set(actor) == {"id", "login"}
                 and type(actor["id"]) is int and type(actor["login"]) is str
                 and actor == record["author"], "current authorized author mismatch")
        lookup = transport.lookup(record["repo"], record["pr"], _hash(_key(record)))
        _require(type(lookup) is dict and set(lookup) == {"complete", "absence_confirmed", "matches"}
                 and type(lookup["complete"]) is bool and type(lookup["absence_confirmed"]) is bool
                 and type(lookup["matches"]) is list and lookup["complete"], "incomplete canonical lookup")
        own = []
        for comment in lookup["matches"]:
            _require(type(comment) is dict and type(comment.get("author_id")) is int, "invalid lookup author")
            if comment["author_id"] != record["author"]["id"]:
                continue
            _own_comment(comment, record)
            own.append(comment)
        _require(len(own) <= 1, "ambiguous own canonical comments")
        body = _body(record)
        if own:
            found = own[0]
            _require(state["comment_id"] is None or state["comment_id"] == found["id"], "canonical comment moved")
            comment_id = found["id"]
            current = _own_comment(found, record)
            if found["body"] != body:
                _require(_hash(current) in record["history"], "unrecognized canonical revision")
                # Persist uncertain before invoking a write, including an update.
                state.update(write_state="uncertain", comment_id=comment_id, reason="write-in-flight")
                store.save(state)
                returned_id = transport.update(comment_id, body)
                _require(type(returned_id) is int and returned_id == comment_id, "update identity mismatch")
        else:
            _require(state["comment_id"] is None, "known canonical comment unavailable")
            _require(lookup["absence_confirmed"], "canonical absence unconfirmed after possible write")
            state.update(write_state="uncertain", reason="write-in-flight")
            store.save(state)
            comment_id = transport.create(record["repo"], record["pr"], body, _hash(_key(record)))
            _require(type(comment_id) is int and comment_id > 0, "invalid create identity")
            state["comment_id"] = comment_id
            store.save(state)
        readback = transport.read(comment_id)
        _own_comment(readback, record)
        _require(readback["id"] == comment_id and readback["body"] == body, "canonical readback mismatch")
        record.update(evidence_status="published", canonical_url=readback["url"])
        state.update(write_state="confirmed", comment_id=comment_id, reason=None)
        store.save(state)
    except (TransportError, EvidenceError, json.JSONDecodeError) as error:
        state["reason"] = type(error).__name__
        store.save(state)
    return deepcopy(record)
