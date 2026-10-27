"""Hand a plan or implementation review to another agent CLI.

This module holds the loop guard and the reviewer command adapters. Every CLI
invocation is an argv list meant for subprocess with shell=False.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Mapping, Optional

DEPTH_VAR = "CROSS_REVIEW_DEPTH"

# Reviewer agents. Adding one means one entry here plus its command builder,
# read-only policy, usage parser, and prices when it has any. model and effort are
# always passed explicitly so the reviewer's global config never wins. env_prefixes
# name the variables its CLI needs for authentication and configuration. priced is
# False for a reviewer whose cost is never known: its usage is complete with tokens
# alone.
REVIEWERS = {
    "codex": {"cli": "codex", "model": "gpt-6.1-sol", "effort": "low",
              "env_prefixes": ("CODEX_", "OPENAI_"), "priced": True},
    "claude-code": {"cli": "claude", "model": "claude-opus-5-5", "effort": "medium",
                    "env_prefixes": ("ANTHROPIC_", "CLAUDE_CONFIG_DIR",
                                     "CLAUDE_CODE_USE_", "CLAUDE_CODE_OAUTH_TOKEN"),
                    "priced": True},
    "antigravity": {"cli": "agy", "model": "gemini-4-argon", "effort": "medium",
                    "env_prefixes": ("AGY_", "GEMINI_API_KEY"), "priced": False},
}
DEFAULTS = {name: (spec["model"], spec["effort"]) for name, spec in REVIEWERS.items()}
# run.log headers written before 1.55.0 name the Claude reviewer by its CLI.
_LEGACY_AGENTS = {"claude": "claude-code"}
# Reviewer families of the argument groups (`<family> [model] [effort]`) and --agent.
FAMILIES = {"claude": "claude-code", "codex": "codex", "gemini": "antigravity",
            "claude-code": "claude-code", "antigravity": "antigravity"}
# Model shorthands: the newest model of each family the runner knows. Any other value
# is a full model id and passes through unchanged.
MODEL_ALIASES = {
    "claude-code": {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5",
                    "haiku": "claude-haiku-5-5", "fable": "claude-fable-5-1"},
    "codex": {"sol": "gpt-6.1-sol", "terra": "gpt-6.1-terra", "astra": "gpt-6-astra",
              "luna": "gpt-6-luna"},
    "antigravity": {"argon": "gemini-4-argon", "flash": "gemini-3.8-flash"},
}
# The host agent and the reviewer that runs when the user names none.
OPPOSITE = {"claude-code": "codex", "codex": "claude-code"}

# Every CLI accepts exactly these levels (codex model_reasoning_effort, claude and agy
# --effort).
EFFORTS = ("low", "medium", "high", "xhigh", "max")

# The reviewer gets only these variables, the LC_* locale, its agent's env_prefixes,
# CROSS_REVIEW_DEPTH, and names passed with --pass-env.
ENV_ALLOWLIST = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM", "LANG", "TZ",
    "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
    "XDG_RUNTIME_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy",
    "https_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
    "__CF_USER_TEXT_ENCODING",
)
_ENV_NAME_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")

EXIT_OK = 0
EXIT_INVALID_INPUT = 2
EXIT_NESTED = 20
EXIT_MISSING_CLI = 21
EXIT_REVIEWER_FAILED = 22
EXIT_EMPTY_RESULT = 23
EXIT_NO_SESSION = 24
EXIT_IDLE_AFTER_ANSWER = 25  # agy answered, then did not exit; review.md holds the answer
EXIT_INTERRUPTED = 130  # SIGINT or SIGTERM

LOG_SCHEMA_VERSION = 1
ARTIFACTS = ("brief.md", "review.md", "session.txt", "run.log")
USAGE_FILE = "usage.json"
USAGE_SCHEMA_VERSION = 1
# Claude and agy --output-format json land here first; review.md gets the parsed answer.
CLAUDE_RAW = "claude-output.json"
AGY_RAW = "agy-output.json"
RAW_OUTPUTS = {"claude-code": CLAUDE_RAW, "antigravity": AGY_RAW}

# agy can finish its answer and then never exit: once agy-output.json holds a complete
# answer and the process stays alive this long, the runner stops it.
AGY_IDLE_SECONDS = 60
AGY_POLL_SECONDS = 1

# Reviewers that cannot run Git get the diff and the untracked files in the brief.
EMBED_REVIEWERS = ("claude-code", "antigravity")
# Embedded material above this size fails the run instead of being truncated. A 1.5 MB
# Antigravity brief has completed a review, so the limit stays above that.
MAX_EMBED_BYTES = 4 << 20

# The installed cr-request skill next to this one: the source of the standard sections.
CR_REQUEST_DIR = Path(__file__).resolve().parents[2] / "cr-request"
MODES = ("plan", "implementation")

PRICES_AS_OF = "2026-10-10"
# Codex: USD per 1M tokens (input, cached input, output), standard tier.
# Source: https://developers.openai.com/api/docs/pricing
# gpt-5.6-sol carries promotional pricing at least through 2026-11-21; gpt-5.5 is the
# under-272K-context price.
PRICES = {
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.5": (5.00, 0.50, 30.00),
    "gpt-5.3-codex": (1.75, 0.175, 14.00),
}
# Claude: USD per 1M tokens (input, 5-minute cache write, cache hit, output). Fallback
# only: the CLI-reported total_cost_usd wins when present. claude-haiku-5-5 is the
# price for prompts up to 100K tokens.
# Source: https://platform.claude.com/docs/en/about-claude/pricing
CLAUDE_PRICES = {
    "claude-fable-5-1": (10.00, 12.50, 0.25, 50.00),
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
}

# input includes cached_input and cache_write; output includes reasoning.
TOKEN_KEYS = ("input", "cached_input", "cache_write", "output", "reasoning")
_CODEX_USAGE_FIELDS = (
    ("input", "input_tokens"),
    ("cached_input", "cached_input_tokens"),
    ("cache_write", "cache_write_input_tokens"),
    ("output", "output_tokens"),
    ("reasoning", "reasoning_output_tokens"),
)
_SKILL_PATH_RE = re.compile(r"([A-Za-z0-9._-]+)/SKILL\.md\b")

# Read-only policy for the Claude reviewer: built-ins limited to Read/Grep/Glob,
# no MCP, no skills or slash commands, and no settings files at all. --restricted
# ignores user, project, and local settings and confines file tools to the repo;
# an empty --setting-sources list states the same intent explicitly. Settings from
# the reviewed repository could otherwise add the server-side advisor tool, hooks,
# or environment variables.
_CLAUDE_POLICY = (
    "--permission-mode", "default",
    "--tools", "Read,Grep,Glob",
    "--allowedTools", "Read,Grep,Glob",
    "--disallowedTools", "Write,Edit,NotebookEdit,Bash,Agent,Skill,mcp__*",
    "--strict-mcp-config",
    "--disable-slash-commands",
    "--safe-mode",
    "--restricted",
    "--setting-sources", "",
)

# Antigravity has no read-only flag: headless agy denies file writes, reads outside the
# workspace, and commands missing from the user's permissions.allow, and a denial ends
# the turn. --disable-slash-commands keeps the brief from expanding slash commands and
# skills, and --print-timeout 0 pins the default wait for the whole turn.
_AGY_POLICY = ("--disable-slash-commands", "--print-timeout", "0")

# Codex sandbox tokens. exec resume has no -s and would inherit the user's global
# sandbox, so read-only is forced through a config override there.
_CODEX_RUN_SANDBOX = ("-s", "read-only")
_CODEX_RESUME_SANDBOX = ("-c", 'sandbox_mode="read-only"')

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_UUID_RE = re.compile(r"\A%s\Z" % _UUID)


class _Terminated(BaseException):
    """Raised from the SIGTERM handler so termination unwinds like Ctrl-C."""


def _raise_terminated(signum, frame):
    raise _Terminated()


class CrossReviewError(Exception):
    """Error that maps to a specific process exit code."""

    def __init__(self, code: int, message: str, run_dir: Optional[Path] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        # Set once a run directory exists, so callers can still find partial artifacts.
        self.run_dir = run_dir


def ensure_not_nested(env: Mapping[str, str]) -> None:
    """Refuse to run inside a reviewer process; an empty value still counts."""
    if DEPTH_VAR in env:
        raise CrossReviewError(
            EXIT_NESTED,
            "You are already the cross-reviewer; do the review yourself "
            "instead of delegating it again.",
        )


def validate_pass_env(names) -> list:
    """Return the --pass-env names after checking each is a plain variable name."""
    names = list(names or [])
    for name in names:
        if not isinstance(name, str) or not _ENV_NAME_RE.match(name):
            raise CrossReviewError(EXIT_INVALID_INPUT,
                                   "--pass-env needs a variable name, got %r" % (name,))
    return names


def reviewer_environment(env: Mapping[str, str], reviewer: str = "codex",
                         pass_env=()) -> dict:
    """Return the reviewer child's environment: the allowlist only, depth marker set.

    Kept: ENV_ALLOWLIST, LC_* locale variables, variables starting with the agent's
    env_prefixes, and the explicit pass_env names. Everything else in the host
    environment, including unrelated secrets, stays out of the reviewer process.
    """
    prefixes = REVIEWERS[reviewer]["env_prefixes"]
    extra = set(validate_pass_env(pass_env))
    child = {key: value for key, value in env.items()
             if key in ENV_ALLOWLIST or key in extra or key.startswith("LC_")
             or key.startswith(prefixes)}
    child[DEPTH_VAR] = "1"
    return child


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CrossReviewError(EXIT_INVALID_INPUT, "%s must be a non-empty string" % name)


def _require_agent(reviewer: str) -> None:
    if reviewer not in REVIEWERS:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "agent must be one of: %s" % ", ".join(sorted(REVIEWERS)))


def _validate_common(reviewer: str, model: str, effort: str) -> None:
    _require_agent(reviewer)
    _require_text("model", model)
    _require_text("effort", effort)
    # The fixed set also keeps effort safe inside the Codex -c TOML string.
    if effort not in EFFORTS:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "effort must be one of: %s" % ", ".join(EFFORTS))
    # An option-like value would be read by the CLI as a flag.
    if model.startswith("-"):
        raise CrossReviewError(EXIT_INVALID_INPUT, "model looks like a command-line option")


def expand_model(reviewer: str, model: Optional[str]) -> Optional[str]:
    """A family shorthand (opus, sol, argon) becomes its full model id; others pass."""
    if model is None:
        return None
    return MODEL_ALIASES.get(reviewer, {}).get(model, model)


def resolve_reviewers(tokens, host: str) -> list:
    """Parse argument groups `<family> [model] [effort]` into one reviewer each.

    No groups: one reviewer, the CLI opposite to host. same_cli marks a reviewer on the
    host's own CLI, which only an explicit group selects.
    """
    if host not in OPPOSITE:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "host must be one of: %s" % ", ".join(sorted(OPPOSITE)))
    groups = []
    for token in tokens or []:
        if token in FAMILIES:
            groups.append({"agent": FAMILIES[token], "model": None, "effort": None})
            continue
        if not groups:
            raise CrossReviewError(EXIT_INVALID_INPUT,
                                   "%r comes before a family (claude, codex, gemini)" % token)
        group = groups[-1]
        if token in EFFORTS:
            if group["effort"] is not None:
                raise CrossReviewError(EXIT_INVALID_INPUT, "two efforts in one group")
            group["effort"] = token
        elif group["model"] is not None or group["effort"] is not None:
            raise CrossReviewError(EXIT_INVALID_INPUT,
                                   "%r: a group is <family> [model] [effort]" % token)
        elif token.startswith("-"):
            raise CrossReviewError(EXIT_INVALID_INPUT, "model looks like a command-line option")
        else:
            group["model"] = token
    if not groups:
        groups = [{"agent": OPPOSITE[host], "model": None, "effort": None}]
    reviewers = []
    for group in groups:
        agent = group["agent"]
        model, effort = DEFAULTS[agent]
        reviewers.append({"agent": agent,
                          "model": expand_model(agent, group["model"]) or model,
                          "effort": group["effort"] or effort,
                          "same_cli": agent == host})
    return reviewers


def _is_uuid(value) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


# Variables that would point git at another repository than the one under review.
_GIT_REDIRECT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR",
                      "GIT_CEILING_DIRECTORIES", "GIT_INDEX_FILE")


def _git_line(repo: Path, *args: str) -> Optional[str]:
    """Return the first stdout line of a git command in repo, or None on any failure."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_REDIRECT_VARS}
    try:
        proc = subprocess.run(["git", "-C", str(repo)] + list(args),
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=env, check=False)
    except OSError:
        return None
    lines = os.fsdecode(proc.stdout).splitlines()
    if proc.returncode != 0 or not lines or not lines[0].strip():
        return None
    return lines[0]


def _on_disk_path(path: Path) -> Optional[str]:
    """Return the path as the file system spells it (case on macOS), if available."""
    if not hasattr(fcntl, "F_GETPATH"):
        return None
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return None
    try:
        raw = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))
    except OSError:
        return None
    finally:
        os.close(fd)
    return os.fsdecode(raw.split(b"\0", 1)[0]) or None


def _find_dot_git(repo: Path) -> Optional[Path]:
    for directory in [repo] + list(repo.parents):
        candidate = directory / ".git"
        if os.path.lexists(candidate):
            return candidate
    return None


def _parse_dot_git(dot_git: Path):
    """Return (toplevel, common_dir) from a .git entry without running git, else None."""
    top = dot_git.parent
    if dot_git.is_dir():
        return top, dot_git.resolve()
    try:
        text = dot_git.read_text("utf-8").strip()
    except (OSError, ValueError):
        return None
    if not text.startswith("gitdir:"):
        return None
    git_dir = (top / text[len("gitdir:"):].strip()).resolve()
    common = git_dir
    try:
        pointer = (git_dir / "commondir").read_text("utf-8").strip()
    except FileNotFoundError:
        pointer = ""
    except (OSError, ValueError):
        return None
    if pointer:
        common = (git_dir / pointer).resolve()
    return top, common


def codex_untrusted_paths(repo: Path) -> list:
    """Paths whose Codex project config must not load.

    A trusted path, or a worktree of a trusted repository, would otherwise load
    .codex/config.toml from the reviewed repository. The set holds the resolved
    repo and its on-disk spelling, the worktree root, the Git common directory's
    parent (the main worktree root for a normal repository), and the common
    directory itself when it is not named .git (bare or separate layouts). Paths
    come from git and from parsing .git directly; a .git entry that yields no
    path at all fails closed.
    """
    repo = Path(repo).resolve()
    paths = [str(repo)]
    on_disk = _on_disk_path(repo)
    if on_disk:
        paths.append(on_disk)

    found = []
    top = _git_line(repo, "rev-parse", "--show-toplevel")
    common = _git_line(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common is None:
        # Git before 2.31 has no --path-format; a relative answer is relative to repo.
        common = _git_line(repo, "rev-parse", "--git-common-dir")
        common = str(repo / common) if common else None
    if top:
        found.append((Path(top).resolve(), None))
    if common:
        found.append((None, Path(common).resolve()))

    dot_git = _find_dot_git(repo)
    parsed = _parse_dot_git(dot_git) if dot_git is not None else None
    if parsed:
        found.append(parsed)
    if dot_git is not None and not found:
        raise CrossReviewError(
            EXIT_INVALID_INPUT,
            "cannot determine the Git layout of %s (%s is unreadable); refusing to run "
            "the Codex reviewer without marking it untrusted" % (repo, dot_git))

    for top_path, common_path in found:
        if top_path is not None:
            paths.append(str(top_path))
        if common_path is not None:
            paths.append(str(common_path.parent))
            if common_path.name != ".git":
                paths.append(str(common_path))
    return list(dict.fromkeys(paths))


def _codex_untrusted_override(paths) -> str:
    """Build the -c value that marks every path as an untrusted Codex project."""
    entries = []
    for path in paths:
        if any(ord(ch) < 0x20 or ch == "\x7f" or 0xD800 <= ord(ch) <= 0xDFFF
               for ch in path):
            raise CrossReviewError(EXIT_INVALID_INPUT,
                                   "repository path contains control characters "
                                   "or undecodable bytes")
        # json.dumps yields a valid TOML basic string for a path without control
        # characters; ensure_ascii=False keeps non-BMP characters out of surrogate escapes.
        entries.append('%s={trust_level="untrusted"}' % json.dumps(path, ensure_ascii=False))
    if not entries:
        raise CrossReviewError(EXIT_INVALID_INPUT, "no repository path to mark untrusted")
    return "projects={%s}" % ", ".join(entries)


TARGET_KINDS = ("range", "tree", "working-tree")


def _git_bytes(repo: Path, *args: str) -> bytes:
    """stdout of a git command in repo; a failure is invalid input for --target."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_REDIRECT_VARS}
    try:
        proc = subprocess.run(["git", "-C", str(repo)] + list(args),
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env, check=False)
    except OSError as exc:
        raise CrossReviewError(EXIT_INVALID_INPUT, "git unavailable for --target: %s" % exc)
    if proc.returncode != 0:
        detail = os.fsdecode(proc.stderr).strip().splitlines()
        raise CrossReviewError(EXIT_INVALID_INPUT, "git %s failed: %s" % (
            args[0], detail[-1] if detail else "no output"))
    return proc.stdout


def _commit(repo: Path, ref: str) -> str:
    if not ref or ref.startswith("-") or any(ord(ch) < 0x21 for ch in ref):
        raise CrossReviewError(EXIT_INVALID_INPUT, "invalid revision %r" % (ref,))
    return os.fsdecode(_git_bytes(repo, "rev-parse", "--verify", "--quiet",
                                  "--end-of-options", ref + "^{commit}")).strip()


def _paths(raw: bytes) -> list:
    return [os.fsdecode(item) for item in raw.split(b"\0") if item]


def is_standard_exclusion(path: str) -> bool:
    """True for paths the brief must never cover: env files and local overrides."""
    name = path.rsplit("/", 1)[-1]
    return name == ".env" or name.startswith(".env.") or ".local" in name


def parse_target(tokens) -> tuple:
    """Validate --target tokens into (kind, ref): range BASE..HEAD, tree REV, working-tree [BASE]."""
    tokens = list(tokens or [])
    if not tokens or tokens[0] not in TARGET_KINDS:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "--target must start with one of: %s" % ", ".join(TARGET_KINDS))
    kind = tokens[0]
    if kind == "working-tree":
        if len(tokens) > 2:
            raise CrossReviewError(EXIT_INVALID_INPUT, "--target working-tree takes at most one base")
        return kind, tokens[1] if len(tokens) == 2 else None
    if len(tokens) != 2:
        raise CrossReviewError(EXIT_INVALID_INPUT, "--target %s needs one revision" % kind)
    ref = tokens[1]
    if kind == "range" and (ref.count("..") != 1 or "..." in ref
                            or not all(ref.split(".."))):
        raise CrossReviewError(EXIT_INVALID_INPUT, "--target range needs BASE..HEAD")
    return kind, ref


def _excluded_by_user(path: str, exclude) -> bool:
    return any(path == item or path.startswith(item.rstrip("/") + "/") for item in exclude)


def compute_target(repo: Path, kind: str, ref: Optional[str], exclude=()) -> dict:
    """File list, standard exclusions, and fingerprint of a review target.

    range BASE..HEAD: committed changes between two commits, fingerprinted by both SHAs
    and a SHA-256 of the binary diff. tree REV: every tracked file at REV, fingerprinted
    by the tree SHA alone. working-tree [BASE]: tracked changes against BASE (HEAD when
    omitted), committed, staged, and unstaged alike, plus untracked files that gitignore
    keeps, fingerprinted by the base, HEAD, the diff hash, and a hash per untracked file.
    Untracked symlinks that leave the repository are excluded, and so is every path
    named in exclude (a file or a directory).
    """
    repo = Path(repo).resolve()
    info = {"kind": kind}
    untracked_hashes = {}
    if kind == "range":
        base_ref, head_ref = ref.split("..")
        base, head = _commit(repo, base_ref), _commit(repo, head_ref)
        files = _paths(_git_bytes(repo, "diff", "--name-only", "-z", base, head, "--"))
        diff = _git_bytes(repo, "diff", "--binary", base, head, "--")
        info.update(base=base, head=head, diff_sha256=hashlib.sha256(diff).hexdigest())
    elif kind == "tree":
        commit = _commit(repo, ref)
        tree = os.fsdecode(_git_bytes(repo, "rev-parse", commit + "^{tree}")).strip()
        files = _paths(_git_bytes(repo, "ls-tree", "-r", "-z", "--name-only", commit))
        info.update(commit=commit, tree=tree)
    else:
        head = _commit(repo, "HEAD")
        base = _commit(repo, ref) if ref else head
        files = _paths(_git_bytes(repo, "diff", "--name-only", "-z", base, "--"))
        diff = _git_bytes(repo, "diff", "--binary", base, "--")
        if ref:
            info["base"] = base
        info.update(head=head, diff_sha256=hashlib.sha256(diff).hexdigest())
        for path in _paths(_git_bytes(repo, "ls-files", "--others", "--exclude-standard",
                                      "-z")):
            full = repo / path
            if full.is_symlink() and repo not in full.resolve().parents:
                untracked_hashes[path] = None
                continue
            try:
                untracked_hashes[path] = hashlib.sha256(full.read_bytes()).hexdigest()
            except OSError:
                untracked_hashes[path] = None
            files.append(path)
    exclude = [item for item in (exclude or ()) if item]
    excluded = sorted(path for path in set(files)
                      if is_standard_exclusion(path) or _excluded_by_user(path, exclude))
    excluded += sorted(path for path, digest in untracked_hashes.items()
                       if digest is None and path not in excluded)
    in_scope = sorted(path for path in set(files) if path not in excluded)
    info["files"] = in_scope
    info["excluded"] = excluded
    info["untracked_sha256"] = {path: untracked_hashes[path] for path in in_scope
                                if untracked_hashes.get(path)}
    return info


def format_target(repo: Path, info: Mapping) -> str:
    """The brief section a --target run appends; the reviewer must not read excluded paths."""
    lines = ["", "## Review target (computed by the cross-review runner)", "",
             "Target: %s" % info["kind"], "Repository: %s" % Path(repo).resolve()]
    for key in ("base", "head", "commit", "tree", "diff_sha256"):
        if key in info:
            lines.append("%s: %s" % (key.replace("_", " ").capitalize(), info[key]))
    for path, digest in sorted(info.get("untracked_sha256", {}).items()):
        lines.append("Untracked %s sha256: %s" % (path, digest))
    lines += ["", "Files in scope (%d):" % len(info["files"])]
    lines += ["- %s" % path for path in info["files"]] or ["- none"]
    lines += ["", "Excluded paths (%d) - do not read them; each is a coverage gap:"
              % len(info["excluded"])]
    lines += ["- %s" % path for path in info["excluded"]] or ["- none"]
    return "\n".join(lines) + "\n"


def _fence(text: str) -> str:
    """A backtick fence longer than any backtick run inside text."""
    longest, run = 0, 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def _fenced(text: str, lang: str = "") -> list:
    fence = _fence(text)
    return [fence + lang, text.rstrip("\n"), fence]


def embed_material(repo: Path, info: Mapping) -> str:
    """The diff of the in-scope tracked files and the content of each in-scope untracked
    file, for a reviewer that cannot run Git. Over MAX_EMBED_BYTES is invalid input."""
    repo = Path(repo).resolve()
    untracked = sorted(info.get("untracked_sha256", {}))
    tracked = [path for path in info["files"] if path not in untracked]
    revs = []
    if info["kind"] == "range":
        revs = [info["base"], info["head"]]
    else:
        revs = [info.get("base") or info["head"]]
    diff = ""
    if tracked:
        diff = os.fsdecode(_git_bytes(
            repo, "diff", "--no-ext-diff", "--no-textconv", *revs, "--",
            *[":(literal)" + path for path in tracked]))
    lines = ["", "## Embedded material (added by the cross-cr runner)", "",
             "You cannot run Git here: this is the complete selected material of the target",
             "above. Git and test commands in the instructions yield to it.", "",
             "### Diff", ""]
    lines += _fenced(diff, "diff") if diff.strip() else ["No tracked changes in scope."]
    gaps = []
    for path in untracked:
        try:
            content = (repo / path).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            gaps.append(path)
            continue
        lines += ["", "### Untracked file: %s" % path, ""] + _fenced(content)
    if gaps:
        lines += ["", "Untracked files not embedded (binary or unreadable; coverage gaps):"]
        lines += ["- %s" % path for path in gaps]
    text = "\n".join(lines) + "\n"
    size = len(text.encode("utf-8"))
    if size > MAX_EMBED_BYTES:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "embedded material is %d bytes, over the %d-byte limit; narrow "
                               "the boundary with --exclude or a smaller --target"
                               % (size, MAX_EMBED_BYTES))
    return text


DOCUMENT_KINDS = ("spec", "plan")
_STATUS_RE = re.compile(r"^\**Status:?\**:?[ \t]*(\S.*?)[ \t]*$", re.M)


def compute_documents(paths: Mapping[str, Optional[str]]) -> dict:
    """{kind: {"path", "sha256"}} for the spec and plan files a review is checked against."""
    documents = {}
    for kind in DOCUMENT_KINDS:
        if not paths.get(kind):
            continue
        path = Path(paths[kind]).absolute()
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise CrossReviewError(EXIT_INVALID_INPUT, "cannot read --%s %s: %s"
                                   % (kind, path, exc.strerror or exc))
        documents[kind] = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}
        # The Status line as it is now, so the brief never carries a stale state.
        match = _STATUS_RE.search(data.decode("utf-8", "replace"))
        if match:
            documents[kind]["status"] = match.group(1)
    return documents


def format_documents(documents: Mapping) -> str:
    lines = ["", "## Requirement documents (hashed by the cross-review runner)", ""]
    for kind in DOCUMENT_KINDS:
        if kind in documents:
            lines.append("%s: %s, sha256 %s" % (kind.capitalize(), documents[kind]["path"],
                                                documents[kind]["sha256"]))
            if documents[kind].get("status"):
                lines.append("%s Status: %s (read at this run)"
                             % (kind.capitalize(), documents[kind]["status"]))
    return "\n".join(lines) + "\n"


def embed_documents(repo: Path, documents: Mapping) -> str:
    """Full content of each requirement document outside repo, for a reviewer whose file
    reads cannot leave the repository."""
    repo = Path(repo).resolve()
    lines = []
    for kind in DOCUMENT_KINDS:
        if kind not in documents:
            continue
        path = Path(documents[kind]["path"])
        if repo == path.resolve() or repo in path.resolve().parents:
            continue
        try:
            content = path.read_bytes().decode("utf-8", "replace")
        except OSError as exc:
            raise CrossReviewError(EXIT_INVALID_INPUT, "cannot read --%s %s: %s"
                                   % (kind, path, exc.strerror or exc))
        lines += ["", "### %s outside the repository: %s" % (kind.capitalize(), path), ""]
        lines += _fenced(content, "markdown")
    return "\n".join(lines) + "\n" if lines else ""


def _markdown_sections(text: str, names) -> list:
    """The level-2 sections of text with these headings, in the order given."""
    found = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            found.setdefault(current, [])
        if current is not None:
            found[current].append(line)
    return ["\n".join(found[name]).rstrip() for name in names if name in found]


AGY_TOOLS_LINE = ("Use only your file read and search tools. agy denies any command or "
                  "file write and then ends the turn without an answer.")


def standard_sections(mode: str, reviewer: str) -> str:
    """Reviewer instructions, result contract, and severity from the installed
    cr-request; the Intent, System, and Craft lenses for implementation mode."""
    refs = Path(CR_REQUEST_DIR) / "references"
    try:
        brief = (refs / "brief.md").read_text("utf-8")
        lenses = (refs / "lenses.md").read_text("utf-8") if mode == "implementation" else ""
    except OSError as exc:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "dependency unavailable: cr-request (%s)" % exc)
    parts = _markdown_sections(brief, ("Reviewer instructions", "Result contract", "Severity"))
    if len(parts) != 3:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "dependency unavailable: cr-request brief.md sections")
    # The closing-line rules after the contract block are for the host, not the reviewer.
    contract = parts[1].split("\n\n`Not checkable", 1)[0]
    parts[1] = contract
    if lenses:
        parts += _markdown_sections(lenses, ("Intent", "System", "Craft"))
    lines = ["", "# Standard sections (added by the cross-cr runner from cr-request)", "",
             "Review mode: %s" % mode, ""]
    lines.append("\n\n".join(parts))
    if reviewer == "antigravity":
        lines += ["", AGY_TOOLS_LINE]
    return "\n".join(lines) + "\n"


def _previous_documents(meta: Mapping) -> dict:
    """Document paths from a previous run header; anything malformed is ignored."""
    previous = meta.get("documents")
    if not isinstance(previous, dict):
        return {}
    paths = {}
    for kind in DOCUMENT_KINDS:
        entry = previous.get(kind)
        path = entry.get("path") if isinstance(entry, dict) else None
        if isinstance(path, str) and os.path.isabs(path):
            paths[kind] = path
    return paths


FOLLOWUP_SECTION = """
## Previous round

This is review round {round} of the same target. Below are the previous round's review
and the host's disposition of each finding. For every previous finding, state its status
on the current target: ADDRESSED or NOT ADDRESSED, with evidence; a partial fix is NOT
ADDRESSED. A finding the host rejected stays closed unless you bring evidence its ruling
did not have. Then review the current target for new findings as usual. A previous PASS
does not cover the current target.

### Previous review (round {previous_round})

{review}

### Host dispositions

{dispositions}
"""


def build_run_command(reviewer: str, repo: Path, run_dir: Path,
                      model: str, effort: str, session_id: str,
                      untrusted=None) -> list:
    """Build the argv for a fresh review run.

    Codex reads the brief from stdin ("-") and writes the final message to
    run_dir/review.md. Claude reads the brief from stdin, runs with cwd=repo,
    and uses the runner-generated session_id. Antigravity reads the brief from stdin,
    runs with cwd=repo, and reports its own conversation id, so session_id is unused.
    untrusted lists the paths forced to an untrusted Codex project; None computes them
    from repo.
    """
    _validate_common(reviewer, model, effort)
    if not Path(repo).is_dir():
        raise CrossReviewError(EXIT_INVALID_INPUT, "repo is not a directory: %s" % repo)

    if reviewer == "antigravity":
        return _agy_command(model, effort)
    if reviewer == "codex":
        if untrusted is None:
            untrusted = codex_untrusted_paths(repo)
        return (["codex", "exec", "--json"] + list(_CODEX_RUN_SANDBOX)
                + ["-m", model, "-c", 'model_reasoning_effort="%s"' % effort,
                   "-c", _codex_untrusted_override(untrusted),
                   "-C", str(repo), "-o", str(Path(run_dir) / "review.md"), "-"])

    if not _is_uuid(session_id):
        raise CrossReviewError(EXIT_INVALID_INPUT, "session_id must be a UUID")
    return (["claude", "-p", "--output-format", "json", "--model", model, "--effort", effort]
            + list(_CLAUDE_POLICY)
            + ["--session-id", session_id])


def build_resume_command(reviewer: str, repo: Path, run_dir: Path,
                         model: str, effort: str, session_id: str,
                         untrusted=None) -> list:
    """Build the argv for a follow-up in an existing reviewer session.

    The caller runs it with cwd=repo. Codex resume has no -s/-C flags and would
    inherit a permissive sandbox, so read-only is forced through -c sandbox_mode.
    Never uses --last: the session is always the explicit UUID. untrusted works as
    in build_run_command.
    """
    _validate_common(reviewer, model, effort)
    if not _is_uuid(session_id):
        raise CrossReviewError(EXIT_NO_SESSION, "session id is missing or not a UUID")

    if reviewer == "antigravity":
        return _agy_command(model, effort) + ["--conversation", session_id]
    if reviewer == "codex":
        if untrusted is None:
            untrusted = codex_untrusted_paths(repo)
        return (["codex", "exec", "resume", "--json", "-m", model,
                 "-c", 'model_reasoning_effort="%s"' % effort]
                + list(_CODEX_RESUME_SANDBOX)
                + ["-c", _codex_untrusted_override(untrusted)]
                + ["-o", str(Path(run_dir) / "review.md"), session_id, "-"])

    return (["claude", "-p", "--output-format", "json", "--model", model, "--effort", effort]
            + list(_CLAUDE_POLICY)
            + ["--resume", session_id])


def _agy_command(model: str, effort: str) -> list:
    # No -p: it takes the next token as the prompt, and the brief comes on stdin.
    return (["agy", "--output-format", "json", "--model", model, "--effort", effort]
            + list(_AGY_POLICY))


def _count(mapping, key) -> int:
    """Read a count already checked by _valid_counts; absent or null means 0."""
    value = mapping.get(key)
    return 0 if value is None else value


def _valid_counts(mapping, required, optional) -> bool:
    """True when every required count is present and every present count is valid.

    A valid count is a non-negative int. An optional count may be absent or null,
    but a present malformed value makes the whole record unknown instead of 0.
    """
    def ok(value):
        return type(value) is int and value >= 0

    return (isinstance(mapping, dict)
            and all(ok(mapping.get(key)) for key in required)
            and all(mapping.get(key) is None or ok(mapping[key]) for key in optional))


def _zero_tokens() -> dict:
    return {key: 0 for key in TOKEN_KEYS}


def parse_codex_events(log: str) -> dict:
    """Read the codex --json event stream mixed into run.log.

    Lines that are not JSON objects (stderr diagnostics, the runner header) are
    skipped. Only the first thread.started sets the session, so an id that shows up
    later cannot replace it; message text is JSON-escaped inside one line and never
    forms an event. Skills are the directory names of SKILL.md files that a shell
    command touched. tokens is None when no turn.completed carried usage, or when
    one of them lacked valid input/output counts or held a malformed optional count;
    usage_error then says why.
    """
    session, seen_thread, tokens, turns, skills = None, False, _zero_tokens(), 0, set()
    usage_error = None
    for line in (log or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "thread.started" and not seen_thread:
            seen_thread = True
            thread = event.get("thread_id")
            session = thread if _is_uuid(thread) else None
        elif kind == "turn.completed":
            usage = event.get("usage")
            # input and output are required; cache and reasoning counts may be absent.
            if not _valid_counts(usage, ("input_tokens", "output_tokens"),
                                 ("cached_input_tokens", "cache_write_input_tokens",
                                  "reasoning_output_tokens")):
                usage_error = "turn.completed with missing or invalid token counts"
                continue
            turns += 1
            for key, field in _CODEX_USAGE_FIELDS:
                tokens[key] += _count(usage, field)
        elif kind == "item.completed" and isinstance(event.get("item"), dict):
            item = event["item"]
            if item.get("type") == "command_execution":
                skills.update(_SKILL_PATH_RE.findall(str(item.get("command", ""))))
    return {"session": session,
            "tokens": tokens if turns and usage_error is None else None,
            "skills": sorted(skills), "usage_error": usage_error}


def parse_codex_session(log: str) -> Optional[str]:
    """Return the session id of the first thread.started event, else None."""
    return parse_codex_events(log)["session"]


def codex_cost(model: str, tokens: Mapping[str, int]) -> Optional[float]:
    """Approximate USD for a Codex run from PRICES; None for a model not in the table.

    input already includes cached tokens and output already includes reasoning
    tokens, so neither subset is added again.
    """
    price = PRICES.get(model)
    if price is None:
        return None
    input_price, cached_price, output_price = price
    uncached = max(tokens["input"] - tokens["cached_input"], 0)
    total = (uncached * input_price + tokens["cached_input"] * cached_price
             + tokens["output"] * output_price) / 1_000_000
    return round(total, 4)


def claude_cost(model: str, tokens: Mapping[str, int]) -> Optional[float]:
    """Approximate USD for a Claude run from CLAUDE_PRICES; None for an unknown model.

    input already includes cache hits and cache writes, so they are billed at their
    own prices and subtracted from the base-price input.
    """
    price = CLAUDE_PRICES.get(model)
    if price is None:
        return None
    input_price, write_price, hit_price, output_price = price
    base = max(tokens["input"] - tokens["cached_input"] - tokens["cache_write"], 0)
    total = (base * input_price + tokens["cache_write"] * write_price
             + tokens["cached_input"] * hit_price + tokens["output"] * output_price) / 1_000_000
    return round(total, 4)


def parse_claude_output(raw: str):
    """Split claude --output-format json into (review text, usage), or (None, None).

    usage is {"tokens": dict or None, "cost_usd": float or None, "session": str or
    None}; session is the reported session_id when it is a UUID. A failure while
    reading the metrics never costs the review text: usage then holds only Nones.
    """
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError):
        return None, None
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), str):
        return None, None
    try:
        usage = _claude_usage(payload)
    except Exception:  # metrics must never fail a review
        usage = {"tokens": None, "cost_usd": None, "session": None}
    return payload["result"], usage


def _claude_usage(payload: dict) -> dict:
    """Sum every model in modelUsage; cost is the CLI-reported total_cost_usd at list price."""
    tokens = None
    models = payload.get("modelUsage")
    if isinstance(models, dict) and models:
        tokens = _zero_tokens()
        for entry in models.values():
            # inputTokens and outputTokens are required; cache and thinking may be absent.
            if not _valid_counts(entry, ("inputTokens", "outputTokens"),
                                 ("cacheReadInputTokens", "cacheCreationInputTokens",
                                  "thinkingTokens")):
                tokens = None
                break
            cached = _count(entry, "cacheReadInputTokens")
            written = _count(entry, "cacheCreationInputTokens")
            tokens["input"] += _count(entry, "inputTokens") + cached + written
            tokens["cached_input"] += cached
            tokens["cache_write"] += written
            tokens["output"] += _count(entry, "outputTokens")
            tokens["reasoning"] += _count(entry, "thinkingTokens")
    cost = payload.get("total_cost_usd")
    # The range check also rejects NaN and Infinity, which json.loads accepts.
    if type(cost) not in (int, float) or not 0 <= cost < float("inf"):
        cost = None
    session = payload.get("session_id")
    return {"tokens": tokens, "cost_usd": None if cost is None else round(cost, 4),
            "session": session if _is_uuid(session) else None}


_AGY_USAGE_FIELDS = (
    ("input", "input_tokens"),
    ("cached_input", "cache_read_tokens"),
    ("output", "output_tokens"),
    ("reasoning", "thinking_tokens"),
)


def parse_antigravity_output(raw: str):
    """Split agy --output-format json into (review text, info), or (None, None).

    info is {"tokens", "cost_usd", "session", "status", "error", "denied"}; cost_usd is
    always None because agy reports no cost, session is the conversation_id when it is
    a UUID, and denied lists the display names of the tool calls agy refused. text is
    None unless status is SUCCESS with a non-empty response: a denied tool call ends
    the turn with SUCCESS and an empty response. A failure while reading the metrics
    never costs the review text.
    """
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    response = payload.get("response")
    status = payload.get("status")
    text = (response if status == "SUCCESS" and isinstance(response, str)
            and response.strip() else None)
    info = {"tokens": None, "cost_usd": None, "session": None,
            "status": status if isinstance(status, str) else None,
            "error": None, "denied": []}
    try:
        usage = payload.get("usage")
        # input and output are required; cache and thinking may be absent. output
        # already includes thinking tokens: total_tokens is input plus output.
        if _valid_counts(usage, ("input_tokens", "output_tokens"),
                         ("cache_read_tokens", "thinking_tokens")):
            info["tokens"] = _zero_tokens()
            for key, field in _AGY_USAGE_FIELDS:
                info["tokens"][key] = _count(usage, field)
        session = payload.get("conversation_id")
        info["session"] = session if _is_uuid(session) else None
        if payload.get("error") is not None:
            info["error"] = str(payload["error"])
        denied = payload.get("denied_actions")
        if isinstance(denied, list):
            info["denied"] = [
                str(item.get("display_name") or item.get("action"))
                if isinstance(item, dict) else str(item) for item in denied]
    except Exception:  # metrics must never fail a review
        pass
    return text, info


def _valid_total(total) -> bool:
    if not isinstance(total, dict):
        return False
    tokens, cost = total.get("tokens"), total.get("cost_usd")
    return (isinstance(tokens, dict)
            and all(type(tokens.get(key)) is int and tokens[key] >= 0 for key in TOKEN_KEYS)
            # The range check also rejects NaN and Infinity, which json.loads accepts.
            and (cost is None or (type(cost) in (int, float) and 0 <= cost < float("inf")))
            and type(total.get("runs")) is int and total["runs"] >= 1
            and type(total.get("complete")) is bool)


def _prior_total(previous):
    """The session_total of a parsed previous usage.json when it is valid, else None."""
    prior = previous.get("session_total") if isinstance(previous, dict) else None
    return prior if _valid_total(prior) else None


def _known(tokens, cost_usd, priced: bool) -> bool:
    """True when a run's figures are complete; an unpriced reviewer needs tokens only."""
    return tokens is not None and (cost_usd is not None or not priced)


def resume_usage(tokens, cost_usd, previous, session, expected_session,
                 reviewer: str = "claude-code"):
    """Split cumulative resume figures into (tokens, cost_usd, reason) of this run.

    claude -p --resume and agy --conversation report usage for the whole session, so
    this run is the reported figures minus the previous session_total. The result is
    (None, None, reason) when that difference cannot be trusted; reason is None when
    the reported figures themselves are missing. An unpriced reviewer's cost stays None.
    """
    cli, priced = REVIEWERS[reviewer]["cli"], REVIEWERS[reviewer]["priced"]
    if session is not None and session != expected_session:
        return None, None, "%s resumed into a different session" % cli
    prior = _prior_total(previous)
    # An incomplete total may hold zero placeholders for unknown tokens.
    if prior is None or (priced and prior["cost_usd"] is None) or not prior["complete"]:
        return None, None, "previous session total unavailable"
    if not _known(tokens, cost_usd, priced):
        return None, None, None
    run_tokens = {key: tokens[key] - prior["tokens"][key] for key in TOKEN_KEYS}
    run_cost = cost_usd - prior["cost_usd"] if priced else None
    if (run_cost is not None and run_cost < 0) or any(value < 0 for value in run_tokens.values()):
        return None, None, "%s reported totals below the previous session total" % cli
    return run_tokens, None if run_cost is None else round(run_cost, 4), None


def _resume_total(tokens, cost_usd, previous, priced: bool) -> dict:
    """session_total of a claude or agy resume: the CLI-reported cumulative figures."""
    prior = _prior_total(previous)
    return {"tokens": dict(tokens) if tokens is not None else _zero_tokens(),
            "cost_usd": cost_usd,
            "runs": prior["runs"] + 1 if prior is not None else 1,
            "complete": _known(tokens, cost_usd, priced)}


def _session_total(tokens, cost_usd, previous_run, previous, priced: bool = True) -> dict:
    complete = _known(tokens, cost_usd, priced)
    total_tokens = dict(tokens) if tokens is not None else _zero_tokens()
    total_cost, runs = cost_usd, 1
    if previous_run is not None:
        prior = previous.get("session_total") if isinstance(previous, dict) else None
        if _valid_total(prior):
            for key in TOKEN_KEYS:
                total_tokens[key] += prior["tokens"][key]
            if prior["cost_usd"] is not None:
                total_cost = (total_cost or 0.0) + prior["cost_usd"]
            runs += prior["runs"]
            complete = complete and prior["complete"]
        else:
            complete = False
    return {"tokens": total_tokens,
            "cost_usd": None if total_cost is None else round(total_cost, 4),
            "runs": runs, "complete": complete}


def _target_total(cost_usd, rounds_previous, round_no) -> dict:
    """Cumulative cost of every run of the review target, rounds and resumes alike.

    rounds_previous is the parsed usage.json of the run this one continues (a
    followup round or a resume), or None for the first round of a target.
    """
    prior = rounds_previous.get("target_total") if isinstance(rounds_previous, dict) else None
    valid = (isinstance(prior, dict) and type(prior.get("runs")) is int and prior["runs"] >= 1
             and type(prior.get("complete")) is bool
             and (prior.get("cost_usd") is None
                  or (type(prior["cost_usd"]) in (int, float)
                      and 0 <= prior["cost_usd"] < float("inf"))))
    if rounds_previous is None:
        return {"cost_usd": cost_usd, "runs": 1, "rounds": round_no,
                "complete": cost_usd is not None}
    if not valid:
        return {"cost_usd": cost_usd, "runs": 1, "rounds": round_no, "complete": False}
    total = prior["cost_usd"]
    if cost_usd is not None:
        total = (total or 0.0) + cost_usd
    return {"cost_usd": None if total is None else round(total, 4),
            "runs": prior["runs"] + 1, "rounds": round_no,
            "complete": prior["complete"] and cost_usd is not None}


def build_usage(reviewer: str, model: str, effort: str, tokens, cost_usd, skills,
                previous_run=None, previous=None, session=None,
                expected_session=None, round_no: int = 1,
                rounds_previous=None) -> dict:
    """Assemble the usage.json record of one run.

    cost_usd is the CLI-reported cost and is used for claude only; the codex cost
    comes from PRICES, and the antigravity cost is always unknown. previous is the
    parsed usage.json of previous_run, or None when it is missing or unreadable, which
    marks the session total incomplete. On a claude or antigravity resume tokens and
    cost_usd are the cumulative session figures the CLI reports; session and
    expected_session are the reported and the resumed session ids (see resume_usage).
    """
    priced = REVIEWERS[reviewer]["priced"]
    # Claude and agy report cumulative usage on resume; codex reports this run only.
    if reviewer != "codex" and previous_run is not None:
        session_total = _resume_total(tokens, cost_usd, previous, priced)
        tokens, cost_usd, _ = resume_usage(tokens, cost_usd, previous, session,
                                           expected_session, reviewer)
    else:
        session_total = None
    if reviewer == "codex":
        cost_usd = codex_cost(model, tokens) if tokens is not None else None
        basis = "price-table" if cost_usd is not None else "unknown"
        skills, note = sorted(skills), "detected from SKILL.md reads"
    elif reviewer == "antigravity":
        cost_usd, basis = None, "unknown"
        skills, note = [], "not detected"
    else:
        basis = "cli-list" if cost_usd is not None else "unknown"
        if cost_usd is None and tokens is not None:
            cost_usd = claude_cost(model, tokens)
            basis = "price-table" if cost_usd is not None else "unknown"
        skills, note = [], "disabled by policy"
    return {
        "schema_version": USAGE_SCHEMA_VERSION,
        "reviewer": reviewer,
        "model": model,
        "effort": effort,
        "skills": skills,
        "skills_note": note,
        "tokens": tokens,
        "cost_usd": cost_usd,
        "cost_basis": basis,
        "prices_as_of": PRICES_AS_OF if basis == "price-table" else None,
        "previous_run": None if previous_run is None else str(previous_run),
        "session_total": session_total or _session_total(tokens, cost_usd, previous_run,
                                                         previous, priced),
        "round": round_no,
        "target_total": _target_total(cost_usd, rounds_previous, round_no),
    }


def format_usage_line(usage: Mapping) -> str:
    """Multi-line ASCII summary for stdout; missing data reads as unknown.

    Separators are ASCII so a non-UTF-8 stdout prints them unchanged; the host's run
    report renders its own typography from usage.json.
    """
    lines = []
    reviewer = str(usage.get("reviewer"))
    model = str(usage.get("model"))
    effort = usage.get("effort")
    lines.append("Reviewer: %s | %s | effort %s" % (reviewer, model, effort))

    tokens = usage.get("tokens")
    if isinstance(tokens, dict):
        lines.append("Tokens: {:,d} in ({:,d} cached) | {:,d} out ({:,d} reasoning)".format(
            tokens["input"], tokens["cached_input"], tokens["output"], tokens["reasoning"]))
    else:
        lines.append("Tokens: unknown")

    cost = usage.get("cost_usd")
    if cost is None:
        lines.append("Cost: unknown")
    elif usage.get("cost_basis") == "price-table":
        lines.append("Cost: ~$%.2f (price table %s)" % (cost, usage.get("prices_as_of")))
    else:
        lines.append("Cost: ~$%.2f (Claude CLI list price)" % cost)

    total = usage.get("session_total")
    if usage.get("previous_run") and isinstance(total, dict):
        if total.get("cost_usd") is None:
            text = "Session: cost unknown over %d runs" % total.get("runs", 0)
        else:
            text = "Session: ~$%.2f over %d runs" % (total["cost_usd"], total.get("runs", 0))
        if not total.get("complete"):
            text += " (incomplete)"
        lines.append(text)
    target = usage.get("target_total")
    if isinstance(target, dict) and type(target.get("rounds")) is int and target["rounds"] > 1:
        if target.get("cost_usd") is None:
            text = "Target: cost unknown over %d rounds" % target["rounds"]
        else:
            text = "Target: ~$%.2f over %d rounds" % (target["cost_usd"], target["rounds"])
        if not target.get("complete"):
            text += " (incomplete)"
        lines.append(text)
    # model and effort may hold any non-option text; keep stdout printable in a C locale.
    return "\n".join(lines).encode("ascii", "replace").decode("ascii")


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _ensure_private_dir(path: Path) -> None:
    """Accept only a real directory owned by us with mode 0700."""
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise CrossReviewError(EXIT_INVALID_INPUT, "unsafe run root (not a real directory): %s" % path)
    if st.st_uid != os.getuid():
        raise CrossReviewError(EXIT_INVALID_INPUT, "unsafe run root (foreign owner): %s" % path)
    if stat.S_IMODE(st.st_mode) != 0o700:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "unsafe run root (mode %o, expected 700): %s"
                               % (stat.S_IMODE(st.st_mode), path))


def _runs_root() -> Path:
    root = Path(tempfile.gettempdir()).absolute() / "cross-review"
    try:
        os.mkdir(root, 0o700)
    except FileExistsError:
        pass  # An existing root is validated below, never repaired.
    else:
        # mkdir mode is filtered by umask; set it explicitly before verifying.
        os.chmod(root, 0o700)
    _ensure_private_dir(root)
    return root


def _create_run_dir() -> Path:
    root = _runs_root()
    base = _timestamp()
    for counter in range(1000):
        candidate = root / (base if counter == 0 else "%s-%d" % (base, counter))
        try:
            os.mkdir(candidate, 0o700)
        except FileExistsError:
            continue
        # mkdir mode is filtered by umask; set it explicitly and re-verify.
        os.chmod(candidate, 0o700)
        _ensure_private_dir(candidate)
        return candidate
    raise CrossReviewError(EXIT_INVALID_INPUT, "too many runs for timestamp %s" % base)


def _create_private_file(path: Path) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    return fd


def _read_brief(brief: Path) -> bytes:
    try:
        data = Path(brief).read_bytes()
    except OSError as exc:
        raise CrossReviewError(EXIT_INVALID_INPUT, "cannot read brief %s: %s" % (brief, exc))
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise CrossReviewError(EXIT_INVALID_INPUT, "brief is not valid UTF-8: %s" % brief)
    return data


def _cli_version(executable: str, env: Mapping[str, str]) -> str:
    try:
        proc = subprocess.run([executable, "--version"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              env=dict(env), check=False)
    except OSError:
        return "unknown"
    lines = proc.stdout.decode("utf-8", "replace").strip().splitlines()
    return lines[0].strip() if proc.returncode == 0 and lines else "unknown"


def _tighten(path: Path) -> None:
    """Re-check an artifact after the reviewer ran; the CLI may have replaced it."""
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
        raise CrossReviewError(EXIT_REVIEWER_FAILED, "unsafe artifact after run: %s" % path)
    if stat.S_IMODE(st.st_mode) != 0o600:
        os.chmod(path, 0o600)


def _log(log_fd: int, line: str) -> None:
    os.write(log_fd, ("cross-review: %s\n" % line).encode("utf-8"))


FOLLOW_UP_PREAMBLE = """\
This is a follow-up in the same cross-review session. The original constraints still apply:
- Stay read-only: inspect and report only; do not edit files, commit, or run commands that change state.
- Do not delegate: no other agents, CLIs, or reviewer skills.
- Keep the previous review target and requirements. If the requirements, base, or file set
  changed, say so instead of reusing the earlier verdict; that needs a fresh run.

Follow-up request:
"""


def _follow_up_brief(prompt: str) -> str:
    return FOLLOW_UP_PREAMBLE + prompt.rstrip("\n") + "\n"


def _read_private_file(path: Path, limit: int) -> bytes:
    """Read a run artifact only if it is a regular file we own (no symlinks)."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            raise OSError("not a regular file owned by the current user")
        return os.read(fd, limit)
    finally:
        os.close(fd)


def _load_run_header(run_dir: Path, code: int = EXIT_NO_SESSION, verb: str = "resume"):
    """Return the validated run.log header of a run; the agent name is normalized."""
    def unavailable(reason):
        return CrossReviewError(code, "cannot %s %s: %s" % (verb, run_dir, reason))

    try:
        _ensure_private_dir(run_dir)
    except FileNotFoundError:
        raise unavailable("run directory does not exist")
    except (CrossReviewError, OSError) as exc:
        raise unavailable(getattr(exc, "message", str(exc)))

    try:
        first = _read_private_file(run_dir / "run.log", 1 << 16).split(b"\n", 1)[0]
        meta = json.loads(first.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise unavailable("run.log header unreadable (%s)" % exc)
    if not isinstance(meta, dict):
        raise unavailable("run.log header is not a JSON object")
    version = meta.get("schema_version")
    if type(version) is not int or version != LOG_SCHEMA_VERSION:
        raise unavailable("unsupported schema_version %r" % (version,))
    for key in ("reviewer", "repo", "model", "effort"):
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            raise unavailable("header field %r is missing or invalid" % key)
    meta["reviewer"] = _LEGACY_AGENTS.get(meta["reviewer"], meta["reviewer"])
    if meta["reviewer"] not in REVIEWERS:
        raise unavailable("unknown reviewer %r" % meta["reviewer"])
    if meta.get("round") is not None and (type(meta["round"]) is not int or meta["round"] < 1):
        raise unavailable("header field 'round' is invalid")
    for key in ("model", "effort"):
        # An option-like value would be read by the CLI as a flag.
        if meta[key].startswith("-"):
            raise unavailable("header field %r looks like a command-line option" % key)
    if not os.path.isabs(meta["repo"]) or not Path(meta["repo"]).is_dir():
        raise unavailable("repo %r is not an existing absolute directory" % meta["repo"])
    return meta


def _previous_host_brief(run_dir: Path, meta: Mapping) -> bytes:
    """The host-written part of a previous run's brief, without the runner's sections."""
    size = meta.get("host_brief_bytes")
    if type(size) is not int or size < 1:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "the previous run records no host brief; pass --brief")
    try:
        data = _read_private_file(Path(run_dir) / "brief.md", 1 << 26)[:size]
        data.decode("utf-8")
    except (OSError, ValueError) as exc:
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "cannot read the previous brief.md: %s" % exc)
    return data


def _load_previous_run(run_dir: Path):
    """Return (metadata, session_id) of a finished run, or raise code 24."""
    def unavailable(reason):
        return CrossReviewError(EXIT_NO_SESSION,
                                "cannot resume %s: %s" % (run_dir, reason))

    meta = _load_run_header(run_dir)
    try:
        session = _read_private_file(run_dir / "session.txt", 4096).decode("utf-8").strip()
    except (OSError, ValueError) as exc:
        raise unavailable("session.txt unreadable (%s)" % exc)
    if not _is_uuid(session):
        raise unavailable("session.txt has no valid session id")
    return meta, session


def _read_usage(run_dir: Path) -> Optional[dict]:
    """Return the parsed usage.json of a run, or None when it is missing or invalid."""
    try:
        data = json.loads(_read_private_file(Path(run_dir) / USAGE_FILE, 1 << 16)
                          .decode("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _record_usage(run_dir: Path, log_fd: int, reviewer: str, model: str, effort: str,
                  tokens, cost_usd, skills, previous_run: Optional[Path],
                  note: Optional[str] = None, session: Optional[str] = None,
                  expected_session: Optional[str] = None, round_no: int = 1,
                  rounds_run: Optional[Path] = None,
                  exit_reason: Optional[str] = None) -> None:
    """Write usage.json. Metrics are optional: no failure here, including a failed
    diagnostic write, may change the review outcome."""
    log = {"run.log": log_fd}
    try:
        previous = _read_usage(previous_run) if previous_run is not None else None
        rounds_previous = None
        if rounds_run is not None:
            # An unreadable usage.json still marks the target total incomplete.
            rounds_previous = _read_usage(rounds_run) or {}
        usage = build_usage(reviewer, model, effort, tokens, cost_usd, skills,
                            previous_run=previous_run, previous=previous,
                            session=session, expected_session=expected_session,
                            round_no=round_no, rounds_previous=rounds_previous)
        if exit_reason:
            usage["exit_reason"] = exit_reason
        if reviewer != "codex" and previous_run is not None:
            note = resume_usage(tokens, cost_usd, previous, session,
                                expected_session, reviewer)[2] or note
        if not _known(usage["tokens"], usage["cost_usd"], REVIEWERS[reviewer]["priced"]):
            _try_log(log, "usage incomplete: %s"
                     % (note or "token counts or cost unavailable"))
        fd = _create_private_file(Path(run_dir) / USAGE_FILE)
        try:
            os.write(fd, (json.dumps(usage, indent=2) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except Exception as exc:  # metrics must never fail a review
        _try_log(log, "usage not recorded: %s" % exc)


def _settle_raw_output(run_dir: Path, review_fd: int, reviewer: str):
    """Move the claude or agy JSON answer into review.md; return (text, usage).

    A parsed answer: review.md gets it and the raw file is removed. Anything else:
    review.md gets the raw stdout for diagnosis, the raw file stays, and text is None.
    """
    raw_path = Path(run_dir) / RAW_OUTPUTS[reviewer]
    raw = _read_private_file(raw_path, 1 << 26).decode("utf-8", "replace")
    parse = parse_claude_output if reviewer == "claude-code" else parse_antigravity_output
    text, usage = parse(raw)
    os.write(review_fd, (raw if text is None else text).encode("utf-8"))
    if text is not None:
        os.unlink(raw_path)
    return text, usage


def _wait_reviewer(proc, reviewer: str, raw_path: Optional[Path]):
    """Wait for the reviewer; return (returncode, exit_reason).

    agy can write a complete answer and then never exit. Once its raw output parses as
    a successful answer and the process stays alive AGY_IDLE_SECONDS, it is stopped and
    exit_reason is "idle-after-answer".
    """
    if reviewer != "antigravity" or raw_path is None:
        return proc.wait(), None
    answered_at = None
    while True:
        try:
            return proc.wait(AGY_POLL_SECONDS), None
        except subprocess.TimeoutExpired:
            pass
        if answered_at is None:
            try:
                raw = raw_path.read_bytes().decode("utf-8", "replace")
            except OSError:
                continue
            text, info = parse_antigravity_output(raw)
            if text is not None and info and info["status"] == "SUCCESS":
                answered_at = time.monotonic()
        elif time.monotonic() - answered_at >= AGY_IDLE_SECONDS:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            return proc.returncode, "idle-after-answer"


def _require_cli(reviewer: str) -> str:
    cli = REVIEWERS[reviewer]["cli"]
    executable = shutil.which(cli)
    if executable is None:
        raise CrossReviewError(EXIT_MISSING_CLI, "%s CLI not found on PATH" % cli)
    return executable


def _execute(reviewer: str, repo: Path, model: str, effort: str, brief_data: bytes,
             env: Mapping[str, str], build, session_id: Optional[str],
             extra_header: Optional[dict] = None,
             previous_run: Optional[Path] = None, pass_env=(), round_no: int = 1,
             rounds_run: Optional[Path] = None) -> Path:
    """Create a run directory, spawn the reviewer, and settle its artifacts.

    build(run_dir) returns the argv. session_id is what session.txt records unless
    Codex prints a newer id or agy reports its conversation id. Unexpected OSError: environment (run root) -> 2,
    runtime after the run directory exists -> 22.
    """
    executable = _require_cli(reviewer)
    child_env = reviewer_environment(env, reviewer, pass_env)
    try:
        run_dir = _create_run_dir()
    except OSError as exc:
        raise CrossReviewError(EXIT_INVALID_INPUT, "cannot create run directory: %s" % exc)
    paths = {name: run_dir / name for name in ARTIFACTS}
    fds = {}
    proc = None
    raw_name = RAW_OUTPUTS.get(reviewer)
    raw_settled = False
    try:
        for name in ARTIFACTS:
            fds[name] = _create_private_file(paths[name])
        if raw_name is not None:
            fds[raw_name] = _create_private_file(run_dir / raw_name)
        os.write(fds["brief.md"], brief_data)
        header = {
            "schema_version": LOG_SCHEMA_VERSION,
            "reviewer": reviewer,
            "mode": (extra_header or {}).get("mode", "unspecified"),
            "repo": str(repo),
            "model": model,
            "effort": effort,
            "round": round_no,
            "pass_env": list(pass_env),
            "cli_version": _cli_version(executable, child_env),
        }
        header.update(extra_header or {})
        os.write(fds["run.log"], (json.dumps(header) + "\n").encode("utf-8"))

        argv = build(run_dir)
        stdout_fd = fds["run.log"] if raw_name is None else fds[raw_name]
        with open(paths["brief.md"], "rb") as stdin:
            try:
                proc = subprocess.Popen(argv, stdin=stdin, stdout=stdout_fd,
                                        stderr=fds["run.log"], cwd=str(repo),
                                        env=child_env, shell=False, umask=0o077)
            except (FileNotFoundError, PermissionError) as exc:
                _log(fds["run.log"], "spawn failed: %s" % exc)
                raise CrossReviewError(EXIT_MISSING_CLI,
                                       "%s CLI could not be started: %s" % (reviewer, exc),
                                       run_dir)
            returncode, exit_reason = _wait_reviewer(
                proc, reviewer, run_dir / raw_name if raw_name else None)
        _log(fds["run.log"], "exit status %d" % returncode)
        if exit_reason:
            _log(fds["run.log"], "exit_reason: %s (no exit %ss after a complete answer)"
                 % (exit_reason, AGY_IDLE_SECONDS))

        tokens, cost_usd, skills, usage_note, reported_session = None, None, [], None, None
        if reviewer == "codex":
            log_text = paths["run.log"].read_text("utf-8", "replace")
            try:
                events = parse_codex_events(log_text)
            except Exception as exc:  # metrics must never fail a review
                events = {"session": None, "tokens": None, "skills": [],
                          "usage_error": "event parse failed: %s" % exc}
            session_id = events["session"] or session_id
            tokens, skills, usage_note = events["tokens"], events["skills"], events["usage_error"]
        raw_text, raw_usage, expected_session = None, None, session_id
        if raw_name is not None:
            raw_settled = True
            raw_text, raw_usage = _settle_raw_output(run_dir, fds["review.md"], reviewer)
            if raw_usage is not None:
                tokens, cost_usd = raw_usage["tokens"], raw_usage["cost_usd"]
                reported_session = raw_usage.get("session")
        if reviewer == "antigravity" and raw_usage is not None:
            # agy names its own conversation; on resume it silently starts a new one
            # when the id is unknown, which the check after _record_usage reports.
            session_id = reported_session or session_id
            if raw_usage["status"] != "SUCCESS":
                _log(fds["run.log"], "agy status %s" % json.dumps(raw_usage["status"]))
            if raw_usage["error"]:
                _log(fds["run.log"], "agy error: %s" % json.dumps(raw_usage["error"]))
            for action in raw_usage["denied"]:
                _log(fds["run.log"], "agy denied: %s" % json.dumps(action))
        if session_id:
            os.write(fds["session.txt"], (session_id + "\n").encode("utf-8"))
        else:
            _log(fds["run.log"], "session id not found; resume unavailable")

        for name in ARTIFACTS + tuple(RAW_OUTPUTS.values()):
            if os.path.lexists(run_dir / name):
                try:
                    _tighten(run_dir / name)
                except CrossReviewError as exc:
                    # Logged so run.log alone explains the exit code after a clean CLI status.
                    _log(fds["run.log"], exc.message)
                    raise

        _record_usage(run_dir, fds["run.log"], reviewer, model, effort, tokens, cost_usd,
                      skills, previous_run, usage_note, session=reported_session,
                      expected_session=expected_session, round_no=round_no,
                      rounds_run=rounds_run, exit_reason=exit_reason)

        if returncode != 0 and not exit_reason:
            raise CrossReviewError(EXIT_REVIEWER_FAILED,
                                   "%s exited with status %d" % (reviewer, returncode), run_dir)
        if reviewer == "antigravity":
            if raw_usage is not None and raw_usage["status"] != "SUCCESS":
                raise CrossReviewError(EXIT_REVIEWER_FAILED,
                                       "agy reported status %s" % raw_usage["status"], run_dir)
            if (previous_run is not None and reported_session is not None
                    and reported_session != expected_session):
                _log(fds["run.log"], "agy started conversation %s instead of resuming %s"
                     % (reported_session, expected_session))
                raise CrossReviewError(EXIT_NO_SESSION,
                                       "agy did not resume conversation %s" % expected_session,
                                       run_dir)
            if raw_text is None:
                _log(fds["run.log"], "agy output is not JSON with a non-empty response")
                raise CrossReviewError(EXIT_EMPTY_RESULT,
                                       "antigravity returned no response%s"
                                       % (" (a tool call was denied)"
                                          if raw_usage and raw_usage["denied"] else ""),
                                       run_dir)
        if reviewer == "claude-code" and raw_text is None:
            _log(fds["run.log"], "claude output is not JSON with a result")
            raise CrossReviewError(EXIT_EMPTY_RESULT,
                                   "claude returned no JSON result", run_dir)
        try:
            review = paths["review.md"].read_text("utf-8", "replace")
        except FileNotFoundError:
            review = ""
        if not review.strip():
            raise CrossReviewError(EXIT_EMPTY_RESULT, "%s returned an empty review" % reviewer,
                                   run_dir)
        if exit_reason:
            raise CrossReviewError(EXIT_IDLE_AFTER_ANSWER,
                                   "agy answered but did not exit; stopped after %ss idle; "
                                   "review.md holds the complete answer" % AGY_IDLE_SECONDS,
                                   run_dir)
        return run_dir
    except (KeyboardInterrupt, _Terminated):
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if raw_name in fds and not raw_settled:
            try:
                _settle_raw_output(run_dir, fds["review.md"], reviewer)
            except OSError:
                pass
        _try_log(fds, "interrupted; partial artifacts kept")
        raise CrossReviewError(EXIT_INTERRUPTED, "interrupted", run_dir)
    except CrossReviewError as exc:
        exc.run_dir = exc.run_dir or run_dir
        raise
    except OSError as exc:
        _try_log(fds, "runtime error: %s" % exc)
        raise CrossReviewError(EXIT_REVIEWER_FAILED, "runtime error: %s" % exc, run_dir)
    finally:
        for fd in fds.values():
            os.close(fd)


def _try_log(fds: dict, line: str) -> None:
    if "run.log" in fds:
        try:
            _log(fds["run.log"], line)
        except OSError:
            pass


def run_review(reviewer: Optional[str], repo: Path, brief: Path, model: Optional[str],
               effort: Optional[str], env: Mapping[str, str], target=None,
               followup: Optional[Path] = None, dispositions: Optional[Path] = None,
               pass_env=(), documents: Optional[Mapping[str, Optional[str]]] = None,
               mode: Optional[str] = None, exclude=()) -> Path:
    """Run one review and return the absolute run directory.

    target holds --target tokens; followup is the run directory of the previous round,
    whose review.md and the host's dispositions file are appended to the brief. A
    followup round reuses that run's agent, and its model and effort when the agent is
    unchanged, unless new values are given, and rehashes its spec and plan paths unless
    documents names new ones. Without a new brief, target, or mode, a followup round
    takes the host part of the previous brief, its target, and its mode, and the runner
    rebuilds every section it adds from the current files. mode appends the cr-request
    standard sections; a Claude or Antigravity reviewer gets the target's diff, its
    untracked files, and requirement documents outside repo embedded. Raises
    CrossReviewError with an exit code; run_dir is attached once it exists.
    """
    ensure_not_nested(env)
    pass_env = validate_pass_env(pass_env)
    previous_meta, round_no = None, 1
    if (followup is None) != (dispositions is None):
        raise CrossReviewError(EXIT_INVALID_INPUT,
                               "--followup and --dispositions go together")
    if followup is not None:
        followup = Path(followup).absolute()
        previous_meta = _load_run_header(followup, EXIT_INVALID_INPUT, "follow up on")
        round_no = (previous_meta.get("round") or 1) + 1
        if reviewer is None:
            reviewer = previous_meta["reviewer"]
        if reviewer == previous_meta["reviewer"]:
            model = previous_meta["model"] if model is None else model
            effort = previous_meta["effort"] if effort is None else effort
        previous_target = previous_meta.get("target")
        if not target and isinstance(previous_target, dict):
            if previous_target.get("kind") in TARGET_KINDS:
                target = [previous_target["kind"]]
                if isinstance(previous_target.get("ref"), str):
                    target.append(previous_target["ref"])
        if mode is None and previous_meta.get("mode") in MODES:
            mode = previous_meta["mode"]
        if not exclude and isinstance(previous_meta.get("exclude"), list):
            exclude = [item for item in previous_meta["exclude"] if isinstance(item, str)]
    if reviewer is None:
        raise CrossReviewError(EXIT_INVALID_INPUT, "--agent is required")
    reviewer = FAMILIES.get(reviewer, reviewer)
    _require_agent(reviewer)
    if mode is not None and mode not in MODES:
        raise CrossReviewError(EXIT_INVALID_INPUT, "mode must be one of: %s" % ", ".join(MODES))
    default_model, default_effort = DEFAULTS[reviewer]
    model = default_model if model is None else expand_model(reviewer, model)
    effort = default_effort if effort is None else effort
    repo = Path(repo).resolve()
    session_id = str(uuid.uuid4()) if reviewer == "claude-code" else None
    # Validate everything (including argv) before touching the filesystem: inputs,
    # then the CLI lookup, then the Codex trust paths, and only then the run directory.
    build_run_command(reviewer, repo, Path("/"), model, effort, session_id or "",
                      untrusted=[str(repo)])
    kind_ref = parse_target(target) if target else None
    if brief is not None:
        brief_data = _read_brief(brief)
    elif followup is not None:
        brief_data = _previous_host_brief(followup, previous_meta)
    else:
        raise CrossReviewError(EXIT_INVALID_INPUT, "--brief is required without --followup")
    extra = {"host_brief_bytes": len(brief_data)}
    if mode is not None:
        extra["mode"] = mode
    exclude = [item for item in (exclude or ()) if item]
    if exclude:
        extra["exclude"] = exclude
    embed = reviewer in EMBED_REVIEWERS
    material = ""
    if kind_ref is not None:
        info = compute_target(repo, *kind_ref, exclude=exclude)
        brief_data += format_target(repo, info).encode("utf-8")
        if embed and info["kind"] != "tree":
            material = embed_material(repo, info)
        extra["target"] = {key: value for key, value in info.items()
                           if key not in ("files", "excluded", "untracked_sha256")}
        extra["target"]["ref"] = kind_ref[1]
        extra["target"]["fingerprint"] = hashlib.sha256(
            json.dumps(info, sort_keys=True).encode("utf-8")).hexdigest()
    document_paths = dict(_previous_documents(previous_meta or {}))
    document_paths.update({kind: path for kind, path in (documents or {}).items() if path})
    if document_paths:
        extra["documents"] = compute_documents(document_paths)
        brief_data += format_documents(extra["documents"]).encode("utf-8")
        if embed:
            brief_data += embed_documents(repo, extra["documents"]).encode("utf-8")
    brief_data += material.encode("utf-8")
    if mode is not None:
        brief_data += standard_sections(mode, reviewer).encode("utf-8")
    if followup is not None:
        try:
            review = _read_private_file(followup / "review.md", 1 << 24).decode("utf-8")
        except (OSError, ValueError) as exc:
            raise CrossReviewError(EXIT_INVALID_INPUT,
                                   "cannot read the previous review.md: %s" % exc)
        if not review.strip():
            raise CrossReviewError(EXIT_INVALID_INPUT, "the previous review.md is empty")
        disposition_text = _read_brief(dispositions).decode("utf-8")
        if not disposition_text.strip():
            raise CrossReviewError(EXIT_INVALID_INPUT, "the dispositions file is empty")
        brief_data += FOLLOWUP_SECTION.format(
            round=round_no, previous_round=round_no - 1, review=review.rstrip("\n"),
            dispositions=disposition_text.rstrip("\n")).encode("utf-8")
        extra["followup_of"] = str(followup)
        if ((extra.get("target") or extra.get("documents"))
                and extra.get("target") == previous_meta.get("target")
                and extra.get("documents") == previous_meta.get("documents")):
            # The runner cannot read verdicts; the host decides whether the round is worth it.
            print("cross-review: target and documents unchanged since round %d"
                  % (round_no - 1), file=sys.stderr)
    _require_cli(reviewer)
    untrusted = codex_untrusted_paths(repo) if reviewer == "codex" else None
    build_run_command(reviewer, repo, Path("/"), model, effort, session_id or "",
                      untrusted=untrusted)
    return _execute(
        reviewer, repo, model, effort, brief_data, env,
        lambda run_dir: build_run_command(reviewer, repo, run_dir, model, effort, session_id,
                                          untrusted=untrusted),
        session_id, extra, pass_env=pass_env, round_no=round_no, rounds_run=followup)


def resume_review(run_dir: Path, prompt: str, env: Mapping[str, str],
                  pass_env=()) -> Path:
    """Send a follow-up to the session of a previous run; return the new run directory.

    Reviewer, repo, model, and effort come from the validated run.log header and the
    session from session.txt. The previous run directory is only read.
    """
    ensure_not_nested(env)
    pass_env = validate_pass_env(pass_env)
    if not isinstance(prompt, str) or not prompt.strip():
        raise CrossReviewError(EXIT_INVALID_INPUT, "prompt must be non-empty")
    previous = Path(run_dir).absolute()
    meta, session = _load_previous_run(previous)
    reviewer, model, effort = meta["reviewer"], meta["model"], meta["effort"]
    repo = Path(meta["repo"])
    try:
        build_resume_command(reviewer, repo, Path("/"), model, effort, session,
                             untrusted=[str(repo.resolve())])
    except CrossReviewError as exc:
        raise CrossReviewError(EXIT_NO_SESSION, "cannot resume %s: %s" % (previous, exc.message))
    brief_data = _follow_up_brief(prompt).encode("utf-8")
    _require_cli(reviewer)
    untrusted = codex_untrusted_paths(repo) if reviewer == "codex" else None
    build_resume_command(reviewer, repo, Path("/"), model, effort, session,
                         untrusted=untrusted)
    return _execute(
        reviewer, repo, model, effort, brief_data, env,
        lambda new_dir: build_resume_command(reviewer, repo, new_dir, model, effort, session,
                                             untrusted=untrusted),
        session, {"resumed_from": str(previous)}, previous_run=previous,
        pass_env=pass_env, round_no=meta.get("round") or 1, rounds_run=previous)


def _print_run(run_dir: Path) -> None:
    print("run_dir: %s" % run_dir)
    for name in ARTIFACTS:
        print("%s: %s" % (name, run_dir / name))
    usage = _read_usage(run_dir)
    line = "usage: unknown"
    if usage is not None:
        print("%s: %s" % (USAGE_FILE, run_dir / USAGE_FILE))
        try:
            line = format_usage_line(usage)
        except Exception:  # the summary must never fail a run
            pass
    print(line)
    sys.stdout.flush()


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CrossReviewError(EXIT_INVALID_INPUT, message)


def main(argv=None) -> int:
    env = os.environ
    # SIGTERM stops the reviewer and keeps partial artifacts, like Ctrl-C.
    try:
        previous_sigterm = signal.signal(signal.SIGTERM, _raise_terminated)
    except ValueError:  # not the main thread; keep the default handler
        return _main(argv, env)
    try:
        return _main(argv, env)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)


def _main(argv, env) -> int:
    try:
        # The loop guard runs before argument parsing, CLI lookup, metadata, and run-dir.
        ensure_not_nested(env)
        parser = _Parser(prog="cross_review.py")
        sub = parser.add_subparsers(dest="command", required=True)
        run = sub.add_parser("run", help="start a fresh review")
        # --reviewer and the value "claude" are the names used before 1.55.0.
        run.add_argument("--agent", "--reviewer", dest="agent",
                         choices=sorted(set(REVIEWERS) | set(FAMILIES)))
        run.add_argument("--repo", required=True, type=Path)
        run.add_argument("--brief", type=Path)
        run.add_argument("--mode", choices=MODES)
        run.add_argument("--exclude", action="append", default=[], metavar="PATH")
        run.add_argument("--model")
        run.add_argument("--effort", choices=EFFORTS)
        run.add_argument("--target", nargs="+", metavar="KIND")
        run.add_argument("--followup", type=Path, metavar="PREVIOUS_RUN_DIR")
        run.add_argument("--dispositions", type=Path)
        run.add_argument("--spec", metavar="PATH")
        run.add_argument("--plan", metavar="PATH")
        run.add_argument("--pass-env", action="append", default=[], metavar="NAME")
        resolve = sub.add_parser("resolve", help="list the reviewers of argument groups")
        resolve.add_argument("--host", required=True, choices=sorted(OPPOSITE))
        resolve.add_argument("groups", nargs="*", metavar="TOKEN")
        resume = sub.add_parser("resume", help="ask a follow-up in the same session")
        resume.add_argument("--run-dir", required=True, type=Path)
        resume.add_argument("--prompt", required=True)
        resume.add_argument("--pass-env", action="append", default=[], metavar="NAME")
        args = parser.parse_args(argv)
        if args.command == "resolve":
            for reviewer in resolve_reviewers(args.groups, args.host):
                print(json.dumps(reviewer))
            return EXIT_OK
        if args.command == "run":
            run_dir = run_review(FAMILIES.get(args.agent, args.agent), args.repo, args.brief,
                                 args.model, args.effort, env, target=args.target,
                                 followup=args.followup, dispositions=args.dispositions,
                                 pass_env=args.pass_env,
                                 documents={"spec": args.spec, "plan": args.plan},
                                 mode=args.mode, exclude=args.exclude)
        else:
            run_dir = resume_review(args.run_dir, args.prompt, env, pass_env=args.pass_env)
    except CrossReviewError as exc:
        if exc.run_dir is not None:
            _print_run(exc.run_dir)
        print("cross-review: %s" % exc.message, file=sys.stderr)
        return exc.code
    except OSError as exc:
        # Backstop: no traceback for unexpected runtime I/O failures.
        print("cross-review: runtime error: %s" % exc, file=sys.stderr)
        return EXIT_REVIEWER_FAILED
    except (KeyboardInterrupt, _Terminated):
        print("cross-review: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    _print_run(run_dir)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
