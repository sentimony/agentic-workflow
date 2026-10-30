"""Standalone unit tests for cross_review command adapters and loop guard."""

import hashlib
import io
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cross_review as cr  # noqa: E402

SESSION = "11111111-1111-4111-8111-111111111111"
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cross_review.py")
ARTIFACTS = ("brief.md", "review.md", "session.txt", "run.log")


def expected_claude(model="claude-opus-5-5", effort="medium"):
    # Literal list on purpose: never derive expectations from production constants.
    return [
        "claude", "-p", "--output-format", "json", "--model", model, "--effort", effort,
        "--permission-mode", "default", "--tools", "Read,Grep,Glob",
        "--allowedTools", "Read,Grep,Glob", "--disallowedTools",
        "Write,Edit,NotebookEdit,Bash,Agent,Skill,mcp__*",
        "--strict-mcp-config", "--disable-slash-commands", "--safe-mode",
        "--restricted", "--setting-sources", "",
        "--session-id", SESSION,
    ]


def expected_agy(model="gemini-4-argon", effort="medium"):
    return [
        "agy", "--output-format", "json", "--model", model, "--effort", effort,
        "--disable-slash-commands", "--print-timeout", "0",
    ]


def trust_token(*paths):
    # Hand-written TOML; the test paths contain no quote or backslash.
    return "projects={%s}" % ", ".join('"%s"={trust_level="untrusted"}' % p for p in paths)


def expected_codex(repo, run, model="gpt-6.1-sol", effort="low", trust=None):
    return [
        "codex", "exec", "--json", "-s", "read-only", "-m", model,
        "-c", 'model_reasoning_effort="%s"' % effort,
        "-c", trust or trust_token(Path(repo).resolve()),
        "-C", str(repo), "-o", str(run / "review.md"), "-",
    ]


class GuardTests(unittest.TestCase):
    def test_depth_blocks(self):
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.ensure_not_nested({"CROSS_REVIEW_DEPTH": "1"})
        self.assertEqual(caught.exception.code, 20)

    def test_empty_depth_also_blocks(self):
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.ensure_not_nested({"CROSS_REVIEW_DEPTH": ""})
        self.assertEqual(caught.exception.code, 20)

    def test_absent_depth_passes(self):
        self.assertIsNone(cr.ensure_not_nested({"PATH": "/usr/bin"}))

    def test_child_inherits_depth_without_mutating_parent(self):
        parent = {"PATH": "/usr/bin", "TASK_SENTINEL": "present"}
        cr.ensure_not_nested(parent)
        child = cr.reviewer_environment(parent)
        self.assertEqual(child, {"PATH": "/usr/bin", "CROSS_REVIEW_DEPTH": "1"})
        self.assertNotIn("CROSS_REVIEW_DEPTH", parent)

    def test_child_environment_is_an_allowlist(self):
        parent = {"HOME": "/h", "PATH": "/b", "LANG": "C", "LC_ALL": "C", "TMPDIR": "/t",
                  "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli",
                  "AWS_SECRET_ACCESS_KEY": "s", "GITHUB_TOKEN": "t", "SNYK_TOKEN": "t",
                  "OPENAI_API_KEY": "o", "CODEX_HOME": "/c",
                  "ANTHROPIC_API_KEY": "a", "CLAUDE_CONFIG_DIR": "/cc",
                  "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_OAUTH_TOKEN": "x",
                  "AGY_ACCOUNT": "g", "GEMINI_API_KEY": "k", "ANTIGRAVITY_CLI": "1",
                  "GOOGLE_APPLICATION_CREDENTIALS": "/adc"}
        base = {"HOME": "/h", "PATH": "/b", "LANG": "C", "LC_ALL": "C", "TMPDIR": "/t",
                "CROSS_REVIEW_DEPTH": "1"}
        self.assertEqual(cr.reviewer_environment(parent, "codex"),
                         dict(base, OPENAI_API_KEY="o", CODEX_HOME="/c"))
        self.assertEqual(cr.reviewer_environment(parent, "claude-code"),
                         dict(base, ANTHROPIC_API_KEY="a", CLAUDE_CONFIG_DIR="/cc",
                              CLAUDE_CODE_USE_BEDROCK="1", CLAUDE_CODE_OAUTH_TOKEN="x"))
        self.assertEqual(cr.reviewer_environment(parent, "antigravity"),
                         dict(base, AGY_ACCOUNT="g", GEMINI_API_KEY="k"))

    def test_pass_env_adds_named_variables_only(self):
        parent = {"PATH": "/b", "AWS_PROFILE": "p", "AWS_SECRET_ACCESS_KEY": "s"}
        child = cr.reviewer_environment(parent, "claude-code", ["AWS_PROFILE", "MISSING"])
        self.assertEqual(child, {"PATH": "/b", "AWS_PROFILE": "p", "CROSS_REVIEW_DEPTH": "1"})

    def test_pass_env_rejects_non_names(self):
        for name in ("", "A=B", "-x", "A B", "1A"):
            with self.subTest(name=name):
                with self.assertRaises(cr.CrossReviewError) as caught:
                    cr.reviewer_environment({}, "codex", [name])
                self.assertEqual(caught.exception.code, 2)


class ConstantsTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(cr.DEFAULTS, {"codex": ("gpt-6.1-sol", "low"),
                                       "claude-code": ("claude-opus-5-5", "medium"),
                                       "antigravity": ("gemini-4-argon", "medium")})

    def test_exit_codes(self):
        self.assertEqual(
            (cr.EXIT_OK, cr.EXIT_INVALID_INPUT, cr.EXIT_NESTED, cr.EXIT_MISSING_CLI,
             cr.EXIT_REVIEWER_FAILED, cr.EXIT_EMPTY_RESULT, cr.EXIT_NO_SESSION,
             cr.EXIT_INTERRUPTED),
            (0, 2, 20, 21, 22, 23, 24, 130),
        )

    def test_error_carries_code_and_message(self):
        err = cr.CrossReviewError(23, "empty")
        self.assertEqual((err.code, err.message), (23, "empty"))


class ArgvTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.repo = base / "my repo"
        self.repo.mkdir()
        self.run = base / "run dir"

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, reviewer, model, effort, repo=None):
        repo = repo or self.repo
        return cr.build_run_command(reviewer, repo, self.run, model, effort, SESSION,
                                    untrusted=[str(repo.resolve())])

    def test_claude_run_security_argv(self):
        self.assertEqual(self.build("claude-code", "claude-opus-5-5", "medium"),
                         expected_claude())

    def test_claude_override_changes_only_model_and_effort(self):
        self.assertEqual(self.build("claude-code", "claude-sonnet-x", "high"),
                         expected_claude("claude-sonnet-x", "high"))

    def test_codex_run_argv(self):
        self.assertEqual(self.build("codex", "gpt-6.1-sol", "low"),
                         expected_codex(self.repo, self.run))

    def test_codex_override_changes_only_model_and_effort(self):
        self.assertEqual(self.build("codex", "gpt-other", "high"),
                         expected_codex(self.repo, self.run, "gpt-other", "high"))

    def test_antigravity_run_argv(self):
        self.assertEqual(self.build("antigravity", "gemini-4-argon", "medium"),
                         expected_agy())

    def test_antigravity_override_changes_only_model_and_effort(self):
        self.assertEqual(self.build("antigravity", "gemini-3.1-pro", "high"),
                         expected_agy("gemini-3.1-pro", "high"))

    def test_antigravity_run_needs_no_session(self):
        for session in ("", None, "not-a-uuid"):
            with self.subTest(session=session):
                self.assertEqual(cr.build_run_command("antigravity", self.repo, self.run,
                                                      "gemini-4-argon", "medium", session),
                                 expected_agy())

    def test_paths_with_spaces_stay_single_tokens(self):
        argv = self.build("codex", "gpt-6.1-sol", "low")
        self.assertIn(str(self.repo), argv)
        self.assertIn(str(self.run / "review.md"), argv)

    def test_shell_metacharacters_are_literal(self):
        repo = self.repo.parent / "r; rm -rf $HOME `x` | & >out"
        repo.mkdir()
        argv = self.build("codex", "m;$(id)", "high", repo=repo)
        self.assertEqual(argv, expected_codex(repo, self.run, "m;$(id)", "high"))
        self.assertTrue(all(isinstance(token, str) for token in argv))

    def test_returns_fresh_list(self):
        first = self.build("claude-code", "claude-opus-5-5", "medium")
        first.append("--dangerously-skip-permissions")
        self.assertEqual(self.build("claude-code", "claude-opus-5-5", "medium"),
                         expected_claude())

    def assertInvalid(self, *args, **kwargs):
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.build_run_command(*args, **kwargs)
        self.assertEqual(caught.exception.code, 2)

    def test_effort_outside_the_fixed_set_is_invalid(self):
        for effort in ("e|x", "auto", "minimal", "ultra", 'low"', "LOW"):
            with self.subTest(effort=effort):
                for reviewer in ("codex", "claude-code", "antigravity"):
                    self.assertInvalid(reviewer, self.repo, self.run, "m", effort, SESSION)

    def test_every_documented_effort_is_accepted(self):
        for effort in ("low", "medium", "high", "xhigh", "max"):
            with self.subTest(effort=effort):
                self.assertEqual(self.build("claude-code", "claude-opus-5-5", effort),
                                 expected_claude(effort=effort))

    def test_invalid_reviewer(self):
        for reviewer in ("gemini", "", "Codex"):
            self.assertInvalid(reviewer, self.repo, self.run, "m", "low", SESSION)

    def test_empty_model_or_effort(self):
        for reviewer in ("codex", "claude-code", "antigravity"):
            self.assertInvalid(reviewer, self.repo, self.run, "", "low", SESSION)
            self.assertInvalid(reviewer, self.repo, self.run, "m", "", SESSION)
            self.assertInvalid(reviewer, self.repo, self.run, "  ", "low", SESSION)

    def test_codex_effort_cannot_escape_toml_string(self):
        self.assertInvalid("codex", self.repo, self.run, "m", 'low" x="y', SESSION)

    def test_missing_repo(self):
        missing = self.repo.parent / "absent repo"
        for reviewer in ("codex", "claude-code", "antigravity"):
            self.assertInvalid(reviewer, missing, self.run, "m", "low", SESSION)

    def test_claude_requires_uuid_session(self):
        self.assertInvalid("claude-code", self.repo, self.run, "m", "low", "not-a-uuid")

    def test_option_like_model_or_effort(self):
        for reviewer in ("codex", "claude-code", "antigravity"):
            self.assertInvalid(reviewer, self.repo, self.run,
                               "--dangerously-skip-permissions", "low", SESSION)
            self.assertInvalid(reviewer, self.repo, self.run, "m", "-x", SESSION)

    def test_codex_trust_override_is_exact_literal(self):
        argv = cr.build_run_command("codex", self.repo, self.run, "m", "low", SESSION,
                                    untrusted=["/a b", "/c"])
        i = argv.index("-C")
        self.assertEqual(argv[i - 2:i], [
            "-c", 'projects={"/a b"={trust_level="untrusted"}, '
                  '"/c"={trust_level="untrusted"}}'])

    def test_codex_trust_path_with_quote_is_escaped(self):
        argv = cr.build_run_command("codex", self.repo, self.run, "m", "low", SESSION,
                                    untrusted=['/r "x" \\y'])
        self.assertIn('projects={"/r \\"x\\" \\\\y"={trust_level="untrusted"}}', argv)

    def test_codex_trust_path_with_non_bmp_character_stays_raw(self):
        argv = cr.build_run_command("codex", self.repo, self.run, "m", "low", SESSION,
                                    untrusted=["/r \U0001f600 \u0436"])
        self.assertIn(trust_token("/r \U0001f600 \u0436"), argv)

    def test_codex_trust_path_with_control_character_is_rejected(self):
        for bad in ("/r\nx", "/r\tx", "/r\x7fx", "/r\x00x"):
            with self.subTest(path=bad):
                self.assertInvalid("codex", self.repo, self.run, "m", "low", SESSION,
                                   untrusted=[bad])
                with self.assertRaises(cr.CrossReviewError) as caught:
                    cr.build_resume_command("codex", self.repo, self.run, "m", "low",
                                            SESSION, untrusted=[bad])
                self.assertEqual(caught.exception.code, 2)

    def test_codex_default_computes_trust_paths_for_run_and_resume(self):
        with mock.patch.object(cr, "codex_untrusted_paths",
                               return_value=["/x", "/y"]) as helper:
            run = cr.build_run_command("codex", self.repo, self.run, "m", "low", SESSION)
            resume = cr.build_resume_command("codex", self.repo, self.run, "m", "low",
                                             SESSION)
        self.assertEqual(helper.call_count, 2)
        for argv in (run, resume):
            self.assertIn(trust_token("/x", "/y"), argv)


class SafetyMutantTests(unittest.TestCase):
    """Mutate the production policy constants and prove the literal argv tests notice.

    Each case patches a production constant with one safety token removed and checks
    that the builders' output no longer equals the literal expected argv, which is
    exactly the comparison the argv tests make.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.run = self.repo / "run"

    def tearDown(self):
        self._tmp.cleanup()

    def claude_outputs(self):
        return (cr.build_run_command("claude-code", self.repo, self.run, "claude-opus-5-5",
                                     "medium", SESSION),
                cr.build_resume_command("claude-code", self.repo, self.run, "claude-opus-5-5",
                                        "medium", SESSION))

    def codex_outputs(self):
        trust = [str(self.repo.resolve())]
        return (cr.build_run_command("codex", self.repo, self.run, "gpt-6.1-sol", "low",
                                     SESSION, untrusted=trust),
                cr.build_resume_command("codex", self.repo, self.run, "gpt-6.1-sol", "low",
                                        SESSION, untrusted=trust))

    def test_unmutated_policy_matches_literals(self):
        self.assertEqual(self.claude_outputs(),
                         (expected_claude(), expected_claude_resume(SESSION)))
        self.assertEqual(self.codex_outputs(),
                         (expected_codex(self.repo, self.run),
                          expected_codex_resume(self.run, SESSION, repo=self.repo)))

    def test_claude_policy_mutants_break_literal_equality(self):
        policy = list(cr._CLAUDE_POLICY)

        def without(flag, pair):
            i = policy.index(flag)
            return tuple(policy[:i] + policy[i + (2 if pair else 1):])

        deny = policy.index("--disallowedTools") + 1
        weak_deny = list(policy)
        weak_deny[deny] = weak_deny[deny].replace(",mcp__*", "")
        mutants = {
            "--tools": without("--tools", True),
            "--allowedTools": without("--allowedTools", True),
            "--disallowedTools": without("--disallowedTools", True),
            "--permission-mode": without("--permission-mode", True),
            "--strict-mcp-config": without("--strict-mcp-config", False),
            "--disable-slash-commands": without("--disable-slash-commands", False),
            "--safe-mode": without("--safe-mode", False),
            "--restricted": without("--restricted", False),
            "--setting-sources": without("--setting-sources", True),
            "deny pattern": tuple(weak_deny),
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name), mock.patch.object(cr, "_CLAUDE_POLICY", mutant):
                run, resume = self.claude_outputs()
                self.assertNotEqual(run, expected_claude())
                self.assertNotEqual(resume, expected_claude_resume(SESSION))

    def test_agy_policy_mutants_break_literal_equality(self):
        def outputs():
            return (cr.build_run_command("antigravity", self.repo, self.run,
                                         "gemini-4-argon", "medium", None),
                    cr.build_resume_command("antigravity", self.repo, self.run,
                                            "gemini-4-argon", "medium", SESSION))

        self.assertEqual(outputs(), (expected_agy(), expected_agy_resume(SESSION)))
        policy = list(cr._AGY_POLICY)
        timeout = policy.index("--print-timeout")
        mutants = {
            "--disable-slash-commands": tuple(p for p in policy
                                              if p != "--disable-slash-commands"),
            "--print-timeout": tuple(policy[:timeout] + policy[timeout + 2:]),
            "skip permissions": tuple(policy) + ("--dangerously-skip-permissions",),
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name), mock.patch.object(cr, "_AGY_POLICY", mutant):
                run, resume = outputs()
                self.assertNotEqual(run, expected_agy())
                self.assertNotEqual(resume, expected_agy_resume(SESSION))

    def test_codex_sandbox_mutants_break_literal_equality(self):
        with mock.patch.object(cr, "_CODEX_RUN_SANDBOX", ()):
            self.assertNotEqual(self.codex_outputs()[0], expected_codex(self.repo, self.run))
        with mock.patch.object(cr, "_CODEX_RESUME_SANDBOX", ()):
            self.assertNotEqual(self.codex_outputs()[1],
                                expected_codex_resume(self.run, SESSION, repo=self.repo))

    def test_codex_trust_mutants_break_literal_equality(self):
        expected = (expected_codex(self.repo, self.run),
                    expected_codex_resume(self.run, SESSION, repo=self.repo))
        trusted = 'projects={%s={trust_level="trusted"}}'
        for name, mutant in {
                "no override": lambda paths: None,
                "trusted": lambda paths: trusted % json.dumps(paths[0])}.items():
            with self.subTest(mutant=name), \
                    mock.patch.object(cr, "_codex_untrusted_override", mutant):
                run, resume = self.codex_outputs()
                self.assertNotEqual(run, expected[0])
                self.assertNotEqual(resume, expected[1])


class SessionParserTests(unittest.TestCase):
    def test_parses_thread_started(self):
        log = json.dumps({"type": "thread.started", "thread_id": PROBE_THREAD}) + "\n"
        self.assertEqual(cr.parse_codex_session(log), PROBE_THREAD)

    def test_text_header_is_not_a_session(self):
        self.assertIsNone(cr.parse_codex_session("session id: %s\n" % PROBE_THREAD))

    def test_absent_returns_none(self):
        self.assertIsNone(cr.parse_codex_session("no metadata here\n"))
        self.assertIsNone(cr.parse_codex_session(""))

    def test_decoys_after_the_first_event_are_ignored(self):
        self.assertEqual(cr.parse_codex_session(PROBE_CODEX_LOG), PROBE_THREAD)

    def test_runner_header_is_skipped(self):
        log = json.dumps({"schema_version": 1, "thread_id": PROBE_THREAD}) + "\n"
        self.assertIsNone(cr.parse_codex_session(log))


# Real shapes captured on 2026-10-04 (codex-cli 0.160.0, Claude Code 2.1.289).
PROBE_THREAD = "01a10896-8bf2-7772-96bf-d48579639203"
PROBE_CODEX_TOKENS = {"input": 48668, "cached_input": 45056, "cache_write": 0,
                      "output": 213, "reasoning": 41}
PROBE_CLAUDE_TOKENS = {"input": 2648, "cached_input": 531, "cache_write": 2115,
                       "output": 4, "reasoning": 0}


def codex_turn(input_tokens, cached, output, reasoning, cache_write=0):
    return json.dumps({"type": "turn.completed", "usage": {
        "input_tokens": input_tokens, "cached_input_tokens": cached,
        "cache_write_input_tokens": cache_write, "output_tokens": output,
        "reasoning_output_tokens": reasoning}})


PROBE_CODEX_LOG = "\n".join([
    json.dumps({"schema_version": 1, "reviewer": "codex"}),
    "Reading prompt from stdin...",
    json.dumps({"type": "thread.started", "thread_id": PROBE_THREAD}),
    json.dumps({"type": "turn.started"}),
    json.dumps({"type": "item.completed", "item": {
        "id": "item_2", "type": "command_execution",
        "command": "/bin/zsh -lc 'cat demo/skills/sample/SKILL.md'",
        "exit_code": 0, "status": "completed"}}),
    json.dumps({"type": "item.completed", "item": {
        "id": "item_3", "type": "agent_message",
        "text": "see /x/skills/decoy/SKILL.md and session 0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5c"}}),
    codex_turn(48668, 45056, 213, 41),
    json.dumps({"type": "thread.started", "thread_id": "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5c"}),
]) + "\n"

PROBE_CLAUDE_OUTPUT = json.dumps({
    "type": "result", "subtype": "success", "is_error": False,
    "result": "Target reviewed: fixture\nCoverage: complete\n",
    "total_cost_usd": 0.0171142,
    "modelUsage": {"claude-opus-5-5": {
        "inputTokens": 2, "outputTokens": 4, "cacheReadInputTokens": 531,
        "cacheCreationInputTokens": 2115, "thinkingTokens": 0, "costUSD": 0.0171142}},
})


# Real shape captured on 2026-10-11 (agy 1.3.3); the denied and error shapes too.
PROBE_AGY_SESSION = "034d0304-33c4-4356-9161-b3673e78bcea"
PROBE_AGY_OUTPUT = json.dumps({
    "conversation_id": PROBE_AGY_SESSION, "status": "SUCCESS", "response": "PONG\n",
    "duration_seconds": 1.602803, "num_turns": 1,
    "usage": {"input_tokens": 11886, "output_tokens": 2, "thinking_tokens": 0,
              "cache_read_tokens": 0, "total_tokens": 11888}})
PROBE_AGY_TOKENS = {"input": 11886, "cached_input": 0, "cache_write": 0,
                    "output": 2, "reasoning": 0}


class AntigravityParserTests(unittest.TestCase):
    def test_probe_output(self):
        text, info = cr.parse_antigravity_output(PROBE_AGY_OUTPUT)
        self.assertEqual(text, "PONG\n")
        self.assertEqual(info, {"tokens": PROBE_AGY_TOKENS, "cost_usd": None,
                                "session": PROBE_AGY_SESSION, "status": "SUCCESS",
                                "error": None, "denied": []})

    def test_denied_action_has_no_text(self):
        raw = json.dumps({"conversation_id": PROBE_AGY_SESSION, "status": "SUCCESS",
                          "response": "", "usage": {"input_tokens": 5, "output_tokens": 1},
                          "denied_actions": [{"action": "command",
                                              "display_name": "git show HEAD"},
                                             {"action": "write_file"}]})
        text, info = cr.parse_antigravity_output(raw)
        self.assertIsNone(text)
        self.assertEqual(info["denied"], ["git show HEAD", "write_file"])
        self.assertEqual(info["tokens"]["input"], 5)

    def test_error_status_has_no_text(self):
        raw = json.dumps({"status": "ERROR", "error": "unknown model",
                          "conversation_id": "", "response": "partial"})
        text, info = cr.parse_antigravity_output(raw)
        self.assertIsNone(text)
        self.assertEqual((info["status"], info["error"], info["session"], info["tokens"]),
                         ("ERROR", "unknown model", None, None))

    def test_malformed_usage_keeps_the_text(self):
        for usage in ({"input_tokens": -1, "output_tokens": 1},
                      {"input_tokens": 1}, {"input_tokens": 1, "output_tokens": 1,
                                            "thinking_tokens": "x"}, "nope"):
            with self.subTest(usage=usage):
                raw = json.dumps({"status": "SUCCESS", "response": "ok", "usage": usage})
                text, info = cr.parse_antigravity_output(raw)
                self.assertEqual((text, info["tokens"]), ("ok", None))

    def test_not_a_json_object(self):
        for raw in ("", "not json", "[]", "null"):
            with self.subTest(raw=raw):
                self.assertEqual(cr.parse_antigravity_output(raw), (None, None))


CLAUDE_RUN1_USAGE = {"session_total": {
    "tokens": {"input": 9691, "cached_input": 7530, "cache_write": 2157, "output": 467,
               "reasoning": 0},
    "cost_usd": 0.0281, "runs": 1, "complete": True}}
CLAUDE_RESUME_REPORTED = {"input": 21256, "cached_input": 18385, "cache_write": 5020,
                          "output": 740, "reasoning": 49}


class UsageTests(unittest.TestCase):
    def test_prices_are_the_published_table(self):
        self.assertEqual(cr.PRICES_AS_OF, "2026-10-10")
        self.assertEqual(cr.PRICES, {
            "gpt-6.1-sol": (2.00, 0.10, 10.00),
            "gpt-6-sol": (2.00, 0.20, 10.00),
            "gpt-6-astra": (10.00, 1.00, 50.00),
            "gpt-6-luna": (0.10, 0.01, 0.50),
            "gpt-5.6-sol": (4.00, 0.40, 20.00),
            "gpt-5.6-terra": (2.00, 0.20, 12.00),
            "gpt-5.6-luna": (0.20, 0.02, 1.20),
            "gpt-5.5": (5.00, 0.50, 30.00),
            "gpt-5.3-codex": (1.75, 0.175, 14.00),
        })
        self.assertEqual(cr.CLAUDE_PRICES, {
            "claude-fable-5-1": (10.00, 12.50, 0.25, 50.00),
            "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
            "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
            "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
        })

    def test_claude_price_table_is_the_fallback_without_cli_cost(self):
        tokens = {"input": 1_000_000, "cached_input": 600_000, "cache_write": 100_000,
                  "output": 10_000, "reasoning": 0}
        usage = cr.build_usage("claude-code", "claude-opus-5-5", "medium", tokens, None, [])
        # 300K base * 4 + 100K write * 5 + 600K hit * 0.20 + 10K out * 20, per 1M.
        self.assertEqual((usage["cost_usd"], usage["cost_basis"], usage["prices_as_of"]),
                         (1.2 + 0.5 + 0.12 + 0.2, "price-table", "2026-10-10"))
        cli = cr.build_usage("claude-code", "claude-opus-5-5", "medium", tokens, 3.0, [])
        self.assertEqual((cli["cost_usd"], cli["cost_basis"]), (3.0, "cli-list"))
        unknown = cr.build_usage("claude-code", "claude-new", "medium", tokens, None, [])
        self.assertEqual((unknown["cost_usd"], unknown["cost_basis"]), (None, "unknown"))
        self.assertIn("Cost: unknown", cr.format_usage_line(unknown))

    def test_codex_events_give_session_tokens_and_skills(self):
        events = cr.parse_codex_events(PROBE_CODEX_LOG)
        self.assertEqual(events, {"session": PROBE_THREAD, "tokens": PROBE_CODEX_TOKENS,
                                  "skills": ["sample"], "usage_error": None})

    def test_codex_turn_without_core_counts_makes_tokens_unknown(self):
        for usage in ({}, {"input_tokens": 10}, {"input_tokens": "10", "output_tokens": 1}):
            with self.subTest(usage=usage):
                log = "\n".join([codex_turn(100, 40, 10, 5),
                                 json.dumps({"type": "turn.completed", "usage": usage})])
                events = cr.parse_codex_events(log)
                self.assertIsNone(events["tokens"])
                self.assertEqual(events["usage_error"],
                                 "turn.completed with missing or invalid token counts")

    def test_codex_invalid_optional_count_makes_tokens_unknown(self):
        for extra in ({"cached_input_tokens": "45056"}, {"reasoning_output_tokens": -1},
                      {"cache_write_input_tokens": 1.5}):
            with self.subTest(extra=extra):
                usage = dict({"input_tokens": 10, "output_tokens": 1}, **extra)
                events = cr.parse_codex_events(
                    json.dumps({"type": "turn.completed", "usage": usage}))
                self.assertIsNone(events["tokens"])
                self.assertEqual(events["usage_error"],
                                 "turn.completed with missing or invalid token counts")

    def test_codex_absent_or_null_optional_counts_are_zero(self):
        usage = {"input_tokens": 10, "output_tokens": 1, "cached_input_tokens": None}
        self.assertEqual(
            cr.parse_codex_events(json.dumps({"type": "turn.completed", "usage": usage}))["tokens"],
            {"input": 10, "cached_input": 0, "cache_write": 0, "output": 1, "reasoning": 0})

    def test_first_thread_started_wins_even_when_invalid(self):
        log = "\n".join([json.dumps({"type": "thread.started", "thread_id": "not-a-uuid"}),
                         json.dumps({"type": "thread.started", "thread_id": PROBE_THREAD})])
        self.assertIsNone(cr.parse_codex_events(log)["session"])

    def test_codex_turns_are_summed_and_absent_turns_give_none(self):
        log = "\n".join([codex_turn(100, 40, 10, 5), "not json", codex_turn(50, 0, 5, 0, 7)])
        self.assertEqual(cr.parse_codex_events(log)["tokens"],
                         {"input": 150, "cached_input": 40, "cache_write": 7,
                          "output": 15, "reasoning": 5})
        events = cr.parse_codex_events("progress only\n")
        self.assertIsNone(events["tokens"])
        self.assertIsNone(events["usage_error"])

    def test_parse_codex_session_reads_the_event_stream(self):
        self.assertEqual(cr.parse_codex_session(PROBE_CODEX_LOG), PROBE_THREAD)
        self.assertIsNone(cr.parse_codex_session("session id: %s\n" % PROBE_THREAD))

    def test_codex_cost(self):
        # (3612 * 2.00 + 45056 * 0.10 + 213 * 10.00) / 1e6 = 0.0138596
        self.assertEqual(cr.codex_cost("gpt-6.1-sol", PROBE_CODEX_TOKENS), 0.0139)
        self.assertIsNone(cr.codex_cost("gpt-unknown", PROBE_CODEX_TOKENS))

    def test_codex_cost_clamps_cached_above_input(self):
        # Uncached input clamps to 0: (0 * 2.00 + 2000 * 0.10 + 1000 * 10.00) / 1e6 = 0.0102
        tokens = {"input": 1000, "cached_input": 2000, "cache_write": 0,
                  "output": 1000, "reasoning": 0}
        self.assertEqual(cr.codex_cost("gpt-6.1-sol", tokens), 0.0102)

    def test_claude_output_sums_every_model(self):
        raw = json.dumps({"result": "ok", "total_cost_usd": 0.02, "modelUsage": {
            "claude-opus-5-5": {"inputTokens": 2, "outputTokens": 4,
                                "cacheReadInputTokens": 531,
                                "cacheCreationInputTokens": 2115, "thinkingTokens": 0},
            "claude-haiku-4-5-20251001": {"inputTokens": 10, "outputTokens": 3,
                                          "cacheReadInputTokens": 0,
                                          "cacheCreationInputTokens": 0,
                                          "thinkingTokens": 1}}})
        text, usage = cr.parse_claude_output(raw)
        self.assertEqual(text, "ok")
        self.assertEqual(usage["tokens"], {"input": 2658, "cached_input": 531,
                                           "cache_write": 2115, "output": 7,
                                           "reasoning": 1})

    def test_claude_output(self):
        text, usage = cr.parse_claude_output(PROBE_CLAUDE_OUTPUT)
        self.assertEqual(text, "Target reviewed: fixture\nCoverage: complete\n")
        self.assertEqual(usage, {"tokens": PROBE_CLAUDE_TOKENS, "cost_usd": 0.0171,
                                 "session": None})

    def test_claude_output_without_result_or_json(self):
        for raw in ("", "plain text", "[]", json.dumps({"type": "result"}),
                    json.dumps({"result": 5})):
            with self.subTest(raw=raw):
                self.assertEqual(cr.parse_claude_output(raw), (None, None))

    def test_claude_model_usage_without_core_counts_makes_tokens_unknown(self):
        raw = json.dumps({"result": "ok", "total_cost_usd": 0.5,
                          "modelUsage": {"claude-opus-5-5": {"inputTokens": 3}}})
        self.assertEqual(cr.parse_claude_output(raw),
                         ("ok", {"tokens": None, "cost_usd": 0.5, "session": None}))

    def test_claude_invalid_optional_count_makes_tokens_unknown(self):
        for extra in ({"cacheReadInputTokens": "531"}, {"thinkingTokens": -1}):
            with self.subTest(extra=extra):
                entry = dict({"inputTokens": 2, "outputTokens": 4}, **extra)
                raw = json.dumps({"result": "ok", "total_cost_usd": 0.5,
                                  "modelUsage": {"claude-opus-5-5": entry}})
                self.assertEqual(cr.parse_claude_output(raw),
                                 ("ok", {"tokens": None, "cost_usd": 0.5, "session": None}))

    def test_claude_non_finite_cost_is_unknown(self):
        for cost in ("NaN", "Infinity"):
            with self.subTest(cost=cost):
                raw = '{"result": "ok", "total_cost_usd": %s}' % cost
                self.assertEqual(cr.parse_claude_output(raw)[1]["cost_usd"], None)

    def test_parsers_survive_deeply_nested_json(self):
        deep = "[" * 100000 + "]" * 100000
        self.assertIsNone(cr.parse_codex_events("{\"a\": %s}\n" % deep)["tokens"])
        self.assertEqual(cr.parse_claude_output('{"result": %s}' % deep), (None, None))

    def test_claude_usage_failure_keeps_the_review_text(self):
        with mock.patch.object(cr, "_claude_usage", side_effect=KeyError("boom")):
            self.assertEqual(cr.parse_claude_output(PROBE_CLAUDE_OUTPUT),
                             ("Target reviewed: fixture\nCoverage: complete\n",
                              {"tokens": None, "cost_usd": None, "session": None}))

    def test_claude_output_without_model_usage(self):
        text, usage = cr.parse_claude_output(json.dumps({"result": "ok"}))
        self.assertEqual((text, usage), ("ok", {"tokens": None, "cost_usd": None,
                                                "session": None}))

    def test_build_usage_codex(self):
        usage = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None,
                               ["sample"])
        self.assertEqual(usage, {
            "schema_version": 1, "reviewer": "codex", "model": "gpt-6.1-sol",
            "effort": "low", "skills": ["sample"],
            "skills_note": "detected from SKILL.md reads",
            "tokens": PROBE_CODEX_TOKENS, "cost_usd": 0.0139, "cost_basis": "price-table",
            "prices_as_of": "2026-10-10", "previous_run": None,
            "session_total": {"tokens": PROBE_CODEX_TOKENS, "cost_usd": 0.0139,
                              "runs": 1, "complete": True},
            "round": 1,
            "target_total": {"cost_usd": 0.0139, "runs": 1, "rounds": 1, "complete": True}})

    def test_build_usage_claude(self):
        usage = cr.build_usage("claude-code", "claude-opus-5-5", "medium", PROBE_CLAUDE_TOKENS,
                               0.0171, ["ignored"])
        self.assertEqual(usage["skills"], [])
        self.assertEqual(usage["skills_note"], "disabled by policy")
        self.assertEqual((usage["cost_usd"], usage["cost_basis"], usage["prices_as_of"]),
                         (0.0171, "cli-list", None))

    def test_build_usage_unknown_model_and_missing_tokens(self):
        usage = cr.build_usage("codex", "gpt-unknown", "low", PROBE_CODEX_TOKENS, None, [])
        self.assertEqual((usage["cost_usd"], usage["cost_basis"], usage["prices_as_of"]),
                         (None, "unknown", None))
        self.assertFalse(usage["session_total"]["complete"])
        usage = cr.build_usage("codex", "gpt-6.1-sol", "low", None, None, [])
        self.assertEqual((usage["tokens"], usage["cost_usd"]), (None, None))

    def test_session_total_adds_the_previous_run(self):
        first = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None, [])
        second = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None, [],
                                previous_run=Path("/tmp/cross-review/prev"), previous=first)
        self.assertEqual(second["previous_run"], "/tmp/cross-review/prev")
        self.assertEqual(second["session_total"], {
            "tokens": {k: 2 * v for k, v in PROBE_CODEX_TOKENS.items()},
            "cost_usd": 0.0278, "runs": 2, "complete": True})

    def test_session_total_without_readable_previous_is_incomplete(self):
        for previous in (None, {"session_total": {"tokens": {}, "runs": 1}}, []):
            with self.subTest(previous=previous):
                usage = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS,
                                       None, [], previous_run=Path("/p"), previous=previous)
                self.assertEqual(usage["session_total"]["runs"], 1)
                self.assertFalse(usage["session_total"]["complete"])

    def test_claude_output_exposes_a_valid_session_id(self):
        for value, expected in ((SESSION, SESSION), ("not-a-uuid", None), (7, None)):
            with self.subTest(value=value):
                raw = json.dumps({"result": "ok", "session_id": value})
                self.assertEqual(cr.parse_claude_output(raw)[1]["session"], expected)

    def claude_resume(self, reported, cost, previous, session=None):
        return cr.build_usage("claude-code", "claude-opus-5-5", "medium", reported, cost, [],
                              previous_run=Path("/p"), previous=previous,
                              session=session, expected_session=SESSION)

    def test_claude_resume_derives_this_run_from_cumulative_totals(self):
        # Live figures from 2026-10-05: claude -p --resume reports session totals.
        usage = self.claude_resume(CLAUDE_RESUME_REPORTED, 0.0414, CLAUDE_RUN1_USAGE,
                                   session=SESSION)
        self.assertEqual(usage["tokens"], {"input": 11565, "cached_input": 10855,
                                           "cache_write": 2863, "output": 273,
                                           "reasoning": 49})
        self.assertEqual(usage["cost_usd"], 0.0133)
        self.assertEqual(usage["cost_basis"], "cli-list")
        self.assertEqual(usage["session_total"], {
            "tokens": CLAUDE_RESUME_REPORTED, "cost_usd": 0.0414, "runs": 2,
            "complete": True})
        # session_id absent from the output is accepted too.
        self.assertEqual(self.claude_resume(CLAUDE_RESUME_REPORTED, 0.0414,
                                            CLAUDE_RUN1_USAGE)["cost_usd"], 0.0133)

    def test_claude_resume_without_previous_total(self):
        no_cost = {"session_total": dict(CLAUDE_RUN1_USAGE["session_total"], cost_usd=None)}
        for previous in (None, {"session_total": {"tokens": {}, "runs": 1}}, no_cost):
            with self.subTest(previous=previous):
                usage = self.claude_resume(CLAUDE_RESUME_REPORTED, 0.0414, previous)
                self.assertEqual((usage["tokens"], usage["cost_usd"]), (None, None))
                self.assertEqual(usage["session_total"]["tokens"], CLAUDE_RESUME_REPORTED)
                self.assertEqual(usage["session_total"]["cost_usd"], 0.0414)
                self.assertTrue(usage["session_total"]["complete"])
                self.assertEqual(cr.resume_usage(
                    CLAUDE_RESUME_REPORTED, 0.0414, previous, None, SESSION),
                    (None, None, "previous session total unavailable"))
                runs = 2 if previous is no_cost else 1
                self.assertEqual(usage["session_total"]["runs"], runs)

    def test_claude_resume_rejects_an_incomplete_previous_total(self):
        incomplete = {"session_total": {"tokens": {key: 0 for key in cr.TOKEN_KEYS},
                                        "cost_usd": 0.03, "runs": 1, "complete": False}}
        self.assertEqual(cr.resume_usage(CLAUDE_RESUME_REPORTED, 0.0414, incomplete,
                                         None, SESSION),
                         (None, None, "previous session total unavailable"))

    def test_claude_resume_below_previous_total(self):
        reported = dict(CLAUDE_RESUME_REPORTED, output=400)
        usage = self.claude_resume(reported, 0.0414, CLAUDE_RUN1_USAGE)
        self.assertEqual((usage["tokens"], usage["cost_usd"]), (None, None))
        self.assertEqual(usage["session_total"]["tokens"], reported)
        self.assertEqual(usage["session_total"]["runs"], 2)
        self.assertEqual(cr.resume_usage(reported, 0.0414, CLAUDE_RUN1_USAGE,
                                         None, SESSION)[2],
                         "claude reported totals below the previous session total")
        self.assertEqual(cr.resume_usage(CLAUDE_RESUME_REPORTED, 0.02,
                                         CLAUDE_RUN1_USAGE, None, SESSION)[2],
                         "claude reported totals below the previous session total")

    def test_claude_resume_into_a_different_session(self):
        usage = self.claude_resume(CLAUDE_RESUME_REPORTED, 0.0414, CLAUDE_RUN1_USAGE,
                                   session=NEW_SESSION)
        self.assertEqual((usage["tokens"], usage["cost_usd"]), (None, None))
        self.assertEqual(usage["session_total"]["tokens"], CLAUDE_RESUME_REPORTED)
        self.assertEqual(cr.resume_usage(CLAUDE_RESUME_REPORTED, 0.0414,
                                         CLAUDE_RUN1_USAGE, NEW_SESSION, SESSION)[2],
                         "claude resumed into a different session")

    def test_antigravity_usage_has_tokens_and_unknown_cost(self):
        usage = cr.build_usage("antigravity", "gemini-3.8-flash", "high",
                               PROBE_AGY_TOKENS, None, ["ignored"])
        self.assertEqual((usage["tokens"], usage["cost_usd"], usage["cost_basis"],
                          usage["prices_as_of"], usage["skills"], usage["skills_note"]),
                         (PROBE_AGY_TOKENS, None, "unknown", None, [], "not detected"))
        self.assertEqual(usage["session_total"], {"tokens": PROBE_AGY_TOKENS,
                                                  "cost_usd": None, "runs": 1,
                                                  "complete": True})
        line = cr.format_usage_line(usage)
        self.assertIn("Reviewer: antigravity | gemini-3.8-flash | effort high", line)
        self.assertIn("Tokens: 11,886 in (0 cached) | 2 out (0 reasoning)", line)
        self.assertIn("Cost: unknown", line)

    def test_antigravity_resume_subtracts_tokens_only(self):
        first = cr.build_usage("antigravity", "gemini-3.8-flash", "high",
                               PROBE_AGY_TOKENS, None, [])
        reported = dict(PROBE_AGY_TOKENS, input=20000, output=50, reasoning=10)
        second = cr.build_usage("antigravity", "gemini-3.8-flash", "high", reported,
                                None, [], previous_run=Path("/p"), previous=first,
                                session=PROBE_AGY_SESSION,
                                expected_session=PROBE_AGY_SESSION)
        self.assertEqual(second["tokens"], {"input": 8114, "cached_input": 0,
                                            "cache_write": 0, "output": 48,
                                            "reasoning": 10})
        self.assertIsNone(second["cost_usd"])
        self.assertEqual(second["session_total"], {"tokens": reported, "cost_usd": None,
                                                   "runs": 2, "complete": True})
        self.assertIn("Session: cost unknown over 2 runs",
                      cr.format_usage_line(second))
        self.assertNotIn("incomplete", cr.format_usage_line(second).split("Session")[1])
        self.assertEqual(cr.resume_usage(reported, None, first, NEW_SESSION,
                                         PROBE_AGY_SESSION, "antigravity")[2],
                         "agy resumed into a different session")
        self.assertEqual(cr.resume_usage(PROBE_AGY_TOKENS, None, second, None,
                                         PROBE_AGY_SESSION, "antigravity")[2],
                         "agy reported totals below the previous session total")

    def test_codex_resume_ignores_claude_session_arguments(self):
        first = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None, [])
        second = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None, [],
                                previous_run=Path("/p"), previous=first,
                                session=NEW_SESSION, expected_session=SESSION)
        self.assertEqual(second["tokens"], PROBE_CODEX_TOKENS)
        self.assertEqual(second["session_total"]["runs"], 2)

    def test_session_total_rejects_a_non_finite_previous_cost(self):
        first = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None, [])
        # json.loads accepts Infinity, 1e999, and NaN in a corrupt usage.json.
        for raw in ("Infinity", "1e999", "NaN"):
            with self.subTest(raw=raw):
                previous = json.loads(json.dumps(first).replace(
                    '"runs": 1', '"runs": 1, "cost_usd": %s' % raw))
                self.assertNotEqual(previous["session_total"]["cost_usd"], 0.0139)
                usage = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS,
                                       None, [], previous_run=Path("/p"), previous=previous)
                self.assertEqual(usage["session_total"], {
                    "tokens": PROBE_CODEX_TOKENS, "cost_usd": 0.0139, "runs": 1,
                    "complete": False})

    def test_format_usage_line(self):
        codex = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None,
                               ["sample"])
        # Plain ASCII separators, so a non-UTF-8 stdout prints no question marks.
        expected_codex = ("Reviewer: codex | gpt-6.1-sol | effort low\n"
                          "Tokens: 48,668 in (45,056 cached) | 213 out (41 reasoning)\n"
                          "Cost: ~$0.01 (price table 2026-10-10)")
        self.assertEqual(cr.format_usage_line(codex), expected_codex)
        claude = cr.build_usage("claude-code", "claude-opus-5-5", "medium", None, None, [])
        expected_claude = ("Reviewer: claude-code | claude-opus-5-5 | effort medium\n"
                           "Tokens: unknown\n"
                           "Cost: unknown")
        self.assertEqual(cr.format_usage_line(claude), expected_claude)
        resumed = cr.build_usage("claude-code", "claude-opus-5-5", "medium",
                                 PROBE_CLAUDE_TOKENS, 0.0171, [], previous_run=Path("/p"),
                                 previous=None)
        # Claude resume reports cumulative totals; without a previous total this run is unknown.
        line = cr.format_usage_line(resumed)
        self.assertTrue("Session: ~$0.02 over 1 runs" in line, line)
        self.assertEqual(line, line.encode("ascii").decode("ascii"))
        unicode_model = cr.build_usage("codex", "gpt-\u00fc", "low", None, None, [])
        line = cr.format_usage_line(unicode_model)
        self.assertTrue(line.startswith("Reviewer: codex | gpt-? | effort low"), line)
        line.encode("ascii")

    def test_target_total_accumulates_rounds(self):
        first = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None, [])
        second = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None, [],
                                round_no=2, rounds_previous=first)
        self.assertEqual(second["target_total"],
                         {"cost_usd": 0.0278, "runs": 2, "rounds": 2, "complete": True})
        self.assertIn("Target: ~$0.03 over 2 rounds", cr.format_usage_line(second))
        lost = cr.build_usage("codex", "gpt-6.1-sol", "low", PROBE_CODEX_TOKENS, None, [],
                              round_no=3, rounds_previous={})
        self.assertEqual(lost["target_total"],
                         {"cost_usd": 0.0139, "runs": 1, "rounds": 3, "complete": False})
        self.assertIn("Target: ~$0.01 over 3 rounds (incomplete)",
                      cr.format_usage_line(lost))


# Fake reviewer sources. Each runs as a real child process via sys.executable;
# argv[1] is the expected cwd, argv[2] the -o path (Codex only).
FAKE_CLAUDE = (
    "import json,os,sys; "
    "assert os.environ['CROSS_REVIEW_DEPTH']=='1', 'depth'; "
    "assert 'TASK_SENTINEL' not in os.environ, 'env'; "
    "assert os.path.realpath(os.getcwd())==os.path.realpath(sys.argv[1]), 'cwd'; "
    "assert sys.stdin.read()=='fixture brief', 'stdin'; "
    "sys.stderr.write('claude diagnostics\\n'); "
    "sys.stdout.write(json.dumps({'type': 'result', 'is_error': False, "
    "'result': 'Target reviewed: fixture\\nCoverage: complete\\n', "
    "'total_cost_usd': 0.0171142, 'modelUsage': {'claude-opus-5-5': {"
    "'inputTokens': 2, 'outputTokens': 4, 'cacheReadInputTokens': 531, "
    "'cacheCreationInputTokens': 2115, 'thinkingTokens': 0}}}))"
)

FAKE_CODEX = (
    "import json,os,sys; "
    "assert os.environ['CROSS_REVIEW_DEPTH']=='1', 'depth'; "
    "assert os.path.realpath(os.getcwd())==os.path.realpath(sys.argv[1]), 'cwd'; "
    "assert sys.stdin.read()=='fixture brief', 'stdin'; "
    "sys.stderr.write('progress: thinking\\n'); "
    "print(json.dumps({'type': 'thread.started', 'thread_id': '" + SESSION + "'})); "
    "print(json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution', "
    "'command': 'cat skills/sample/SKILL.md'}})); "
    "print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 48668, "
    "'cached_input_tokens': 45056, 'cache_write_input_tokens': 0, 'output_tokens': 213, "
    "'reasoning_output_tokens': 41}})); "
    "open(sys.argv[2],'w').write('Target reviewed: fixture\\nCoverage: complete\\n')"
)


def fake_builder(source, argv_extra=None):
    """Replace only the command builder; subprocess stays real."""
    def build(reviewer, repo, run_dir, model, effort, session_id, untrusted=None):
        extra = [str(repo)]
        if reviewer == "codex":
            extra.append(str(Path(run_dir) / "review.md"))
        return [sys.executable, "-c", source] + extra + list(argv_extra or [])
    return build


def tree_snapshot(root):
    snap = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            st = os.lstat(path)
            snap[os.path.relpath(path, root)] = (st.st_mode, st.st_size, st.st_mtime_ns)
    return snap


class RunnerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.tmpdir = base / "tmp root"
        self.tmpdir.mkdir()
        self.repo = base / "target repo"
        self.repo.mkdir()
        (self.repo / "file.txt").write_text("content\n")
        self.brief = base / "brief input.md"
        self.brief.write_text("fixture brief", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if k != "CROSS_REVIEW_DEPTH"}
        self.env["TASK_SENTINEL"] = "present"
        # The Antigravity preflight reads HOME: never the real ~/.gemini settings.
        self.home = base / "home"
        self.home.mkdir()
        self.env["HOME"] = str(self.home)
        # Isolate from a parent CROSS_REVIEW_DEPTH: restored when the test ends.
        env_patch = mock.patch.dict(os.environ, clear=False)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        os.environ.pop("CROSS_REVIEW_DEPTH", None)
        patches = [
            mock.patch.object(tempfile, "tempdir", str(self.tmpdir)),
            # Fake reviewers read these test-only variables; TASK_SENTINEL stays out.
            mock.patch.object(cr, "ENV_ALLOWLIST", cr.ENV_ALLOWLIST + (
                "FAKE_RECORD", "FAKE_NEW_SESSION", "FAKE_CLAUDE_USAGE",
                "FAKE_CLAUDE_SESSION", "FAKE_AGY_USAGE", "FAKE_AGY_SESSION",
                "FAKE_AGY_MODE")),
            mock.patch.object(cr.shutil, "which", return_value=sys.executable),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self._tmp.cleanup()

    @property
    def root(self):
        return self.tmpdir / "cross-review"

    def run_dirs(self):
        return sorted(self.root.iterdir()) if self.root.exists() else []

    def run_fake(self, reviewer, source, **kwargs):
        with mock.patch.object(cr, "build_run_command", fake_builder(source)):
            return cr.run_review(reviewer, self.repo, self.brief, None, None,
                                 kwargs.get("env", self.env))

    def run_fake_error(self, reviewer, source):
        with self.assertRaises(cr.CrossReviewError) as caught:
            self.run_fake(reviewer, source)
        return caught.exception


class MainTests(RunnerTestCase):
    def call_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cr.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_missing_cli_returns_21_without_spawn(self):
        with mock.patch.object(cr.shutil, "which", return_value=None), \
                mock.patch.object(cr.subprocess, "Popen") as popen, \
                mock.patch.object(cr.subprocess, "run") as run:
            code, _, err = self.call_main(["run", "--agent", "codex", "--repo",
                                           str(self.repo), "--brief", str(self.brief)])
        self.assertEqual(code, 21)
        popen.assert_not_called()
        run.assert_not_called()
        self.assertEqual(self.run_dirs(), [])
        self.assertIn("codex", err)

    def test_main_success_prints_absolute_paths(self):
        with mock.patch.dict(os.environ, {"TASK_SENTINEL": "present"}), \
                mock.patch.object(cr, "build_run_command", fake_builder(FAKE_CLAUDE)):
            os.environ.pop("CROSS_REVIEW_DEPTH", None)
            code, out, _ = self.call_main(["run", "--agent", "claude-code", "--repo",
                                           str(self.repo), "--brief", str(self.brief)])
        self.assertEqual(code, 0)
        [run_dir] = self.run_dirs()
        self.assertIn(str(run_dir), out)
        for name in ARTIFACTS:
            self.assertIn(str(run_dir / name), out)
        lines = out.splitlines()
        # Last lines are the multi-line report (Reviewer, Tokens, Cost, [Session]).
        report_start = len(lines) - 3
        for i in range(report_start, len(lines)):
            self.assertIn(": ", lines[i], lines[i])
        self.assertTrue(lines[report_start].startswith(
            "Reviewer: claude-code | claude-opus-5-5 | effort medium"),
                        lines[report_start])
        self.assertIn(str(run_dir / "usage.json"), out)
        for line in lines[:report_start]:
            self.assertTrue(os.path.isabs(line.split(": ", 1)[1]), line)

    def test_legacy_reviewer_flag_and_claude_value_run_claude_code(self):
        with mock.patch.dict(os.environ, {}), \
                mock.patch.object(cr, "build_run_command", fake_builder(FAKE_CLAUDE)):
            os.environ.pop("CROSS_REVIEW_DEPTH", None)
            code, out, _ = self.call_main(["run", "--reviewer", "claude", "--repo",
                                           str(self.repo), "--brief", str(self.brief)])
        self.assertEqual(code, 0)
        self.assertIn("Reviewer: claude-code | claude-opus-5-5", out)

    def test_print_run_unreadable_usage_prints_unknown(self):
        import contextlib
        import io
        bad = '{"tokens": {"input": Infinity, "cached_input": 0, "cache_write": 0, ' \
              '"output": 0, "reasoning": 0}, "cost_usd": Infinity}'
        for content in (None, "{not json", bad, "[]", '{"tokens": 5, "cost_usd": "x"}'):
            run_dir = Path(tempfile.mkdtemp(dir=self._tmp.name))
            for name in ARTIFACTS:
                (run_dir / name).write_text("x")
            if content is not None:
                (run_dir / "usage.json").write_text(content)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cr._print_run(run_dir)
            out = buf.getvalue()
            self.assertEqual(out.splitlines()[-1], "usage: unknown")
            if content in (None, "{not json"):
                self.assertNotIn("usage.json", out)

    def test_invalid_input_returns_2(self):
        bad = self.brief.parent / "bad.md"
        bad.write_bytes(b"\xff\xfe broken")
        control = self.brief.parent / "repo\nname"
        control.mkdir()
        cases = [
            ["--agent", "codex", "--repo", str(control), "--brief", str(self.brief)],
            ["--agent", "codex", "--repo", str(self.repo), "--brief", str(bad)],
            ["--agent", "codex", "--repo", str(self.repo), "--brief", "/nonexistent/b.md"],
            ["--agent", "codex", "--repo", "/nonexistent/repo", "--brief", str(self.brief)],
            ["--agent", "bard", "--repo", str(self.repo), "--brief", str(self.brief)],
            ["--agent", "codex", "--repo", str(self.repo), "--brief", str(self.brief),
             "--model", ""],
            ["--agent", "codex", "--repo", str(self.repo), "--brief", str(self.brief),
             "--model=--dangerously-bypass-approvals-and-sandbox"],
            ["--agent", "claude-code", "--repo", str(self.repo), "--brief", str(self.brief),
             "--model=--dangerously-skip-permissions"],
            ["--agent", "codex", "--repo", str(self.repo), "--brief", str(self.brief),
             "--effort=-x"],
        ]
        for args in cases:
            with self.subTest(args=args), \
                    mock.patch.object(cr.subprocess, "Popen") as popen:
                code, _, _ = self.call_main(["run"] + args)
                self.assertEqual(code, 2)
                popen.assert_not_called()
        self.assertEqual(self.run_dirs(), [])


class GuardSubprocessTests(RunnerTestCase):
    def test_actual_main_with_depth_exits_20_before_cli_and_run_dir(self):
        env = dict(self.env, CROSS_REVIEW_DEPTH="", TMPDIR=str(self.tmpdir),
                   PATH="/nonexistent")
        proc = subprocess.run(
            [sys.executable, SCRIPT, "run", "--agent", "codex", "--repo",
             str(self.repo), "--brief", str(self.brief)],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 20, proc.stderr)
        self.assertIn("already the cross-reviewer", proc.stderr)
        self.assertFalse(self.root.exists())

    def test_nested_child_run_is_refused(self):
        # The fake reviewer tries to delegate again through the real script.
        nested = (
            "import json,subprocess,sys; "
            "sys.stdin.read(); "
            "r = subprocess.run([sys.executable, %r, 'run', '--agent', 'codex', "
            "'--repo', sys.argv[1], '--brief', %r], stdin=subprocess.DEVNULL, "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
            "print(json.dumps({'result': 'nested-exit=%%d' %% r.returncode}))"
        ) % (SCRIPT, str(self.brief))
        run_dir = self.run_fake("claude-code", nested)
        self.assertEqual((run_dir / "review.md").read_text().strip(), "nested-exit=20")
        self.assertEqual(self.run_dirs(), [run_dir])


class RunReviewTests(RunnerTestCase):
    def test_claude_artifacts(self):
        before = tree_snapshot(self.repo)
        run_dir = self.run_fake("claude-code", FAKE_CLAUDE)
        self.assertEqual(tree_snapshot(self.repo), before)
        self.assertTrue(run_dir.is_absolute())
        self.assertEqual(run_dir.parent, self.root)
        self.assertEqual((run_dir / "brief.md").read_text(), "fixture brief")
        self.assertEqual((run_dir / "review.md").read_text(),
                         "Target reviewed: fixture\nCoverage: complete\n")
        self.assertFalse((run_dir / "claude-output.json").exists())
        usage = json.loads((run_dir / "usage.json").read_text())
        self.assertEqual(usage["tokens"], PROBE_CLAUDE_TOKENS)
        self.assertEqual((usage["cost_usd"], usage["cost_basis"]), (0.0171, "cli-list"))
        self.assertEqual((usage["skills"], usage["skills_note"]), ([], "disabled by policy"))
        session = (run_dir / "session.txt").read_text().strip()
        self.assertRegex(session, cr._UUID_RE.pattern)
        log = (run_dir / "run.log").read_text()
        self.assertIn("claude diagnostics", log)
        self.assertNotIn("Target reviewed", log)

    def test_claude_session_id_is_passed_to_builder(self):
        seen = {}
        inner = fake_builder(FAKE_CLAUDE)

        def spy(reviewer, repo, run_dir, model, effort, session_id, untrusted=None):
            seen["session"] = session_id
            seen["model"], seen["effort"] = model, effort
            return inner(reviewer, repo, run_dir, model, effort, session_id, untrusted)

        with mock.patch.object(cr, "build_run_command", spy):
            run_dir = cr.run_review("claude-code", self.repo, self.brief, None, None, self.env)
        self.assertEqual((run_dir / "session.txt").read_text().strip(), seen["session"])
        self.assertEqual((seen["model"], seen["effort"]), cr.DEFAULTS["claude-code"])

    def test_codex_final_answer_comes_from_output_file(self):
        run_dir = self.run_fake("codex", FAKE_CODEX)
        self.assertEqual((run_dir / "review.md").read_text(),
                         "Target reviewed: fixture\nCoverage: complete\n")
        self.assertEqual((run_dir / "session.txt").read_text().strip(), SESSION)
        log = (run_dir / "run.log").read_text()
        self.assertIn("progress: thinking", log)
        self.assertIn('"type": "thread.started"', log)

    def test_codex_without_session_leaves_session_empty(self):
        source = FAKE_CODEX.replace("thread.started", "thread.other")
        run_dir = self.run_fake("codex", source)
        self.assertEqual((run_dir / "session.txt").read_text(), "")
        self.assertIn("session id not found", (run_dir / "run.log").read_text())

    def test_codex_usage_json(self):
        run_dir = self.run_fake("codex", FAKE_CODEX)
        usage = json.loads((run_dir / "usage.json").read_text())
        self.assertEqual(usage, {
            "schema_version": 1, "reviewer": "codex", "model": "gpt-6.1-sol",
            "effort": "low", "skills": ["sample"],
            "skills_note": "detected from SKILL.md reads",
            "tokens": PROBE_CODEX_TOKENS, "cost_usd": 0.0139, "cost_basis": "price-table",
            "prices_as_of": "2026-10-10", "previous_run": None,
            "session_total": {"tokens": PROBE_CODEX_TOKENS, "cost_usd": 0.0139,
                              "runs": 1, "complete": True},
            "round": 1,
            "target_total": {"cost_usd": 0.0139, "runs": 1, "rounds": 1, "complete": True}})
        self.assertNotIn("fixture brief", (run_dir / "usage.json").read_text())

    def test_usage_failure_keeps_exit_zero_and_is_logged(self):
        with mock.patch.object(cr, "build_usage", side_effect=TypeError("boom")):
            run_dir = self.run_fake("codex", FAKE_CODEX)
        self.assertFalse((run_dir / "usage.json").exists())
        self.assertIn("cross-review: usage not recorded: boom",
                      (run_dir / "run.log").read_text())

    def test_usage_failure_with_failing_log_keeps_exit_zero(self):
        real_log = cr._log

        def log(fd, line):
            if line.startswith("usage"):
                raise OSError("disk full")
            real_log(fd, line)

        with mock.patch.object(cr, "build_usage", side_effect=OverflowError("big")), \
                mock.patch.object(cr, "_log", side_effect=log):
            run_dir = self.run_fake("codex", FAKE_CODEX)
        self.assertEqual((run_dir / "review.md").read_text(),
                         "Target reviewed: fixture\nCoverage: complete\n")

    def test_codex_event_parse_failure_keeps_exit_zero(self):
        with mock.patch.object(cr, "parse_codex_events", side_effect=RuntimeError("boom")):
            run_dir = self.run_fake("codex", FAKE_CODEX)
        self.assertEqual((run_dir / "review.md").read_text(),
                         "Target reviewed: fixture\nCoverage: complete\n")
        self.assertIsNone(json.loads((run_dir / "usage.json").read_text())["tokens"])
        self.assertIn("cross-review: usage incomplete: event parse failed: boom",
                      (run_dir / "run.log").read_text())

    def test_invalid_codex_usage_is_unknown_and_logged(self):
        source = FAKE_CODEX.replace("'input_tokens': 48668, ", "")
        run_dir = self.run_fake("codex", source)
        usage = json.loads((run_dir / "usage.json").read_text())
        self.assertEqual((usage["tokens"], usage["cost_usd"]), (None, None))
        self.assertIn("cross-review: usage incomplete: turn.completed with missing or "
                      "invalid token counts", (run_dir / "run.log").read_text())

    def test_log_header_is_first_json_line(self):
        run_dir = self.run_fake("codex", FAKE_CODEX)
        first, rest = (run_dir / "run.log").read_text().split("\n", 1)
        header = json.loads(first)
        self.assertEqual(header["schema_version"], 1)
        self.assertEqual(header["reviewer"], "codex")
        self.assertEqual(header["mode"], "unspecified")
        self.assertEqual(header["repo"], str(self.repo.resolve()))
        self.assertEqual((header["model"], header["effort"]), cr.DEFAULTS["codex"])
        self.assertTrue(header["cli_version"].startswith("Python"))
        self.assertNotIn("TASK_SENTINEL", first)
        self.assertNotIn("env", header)
        self.assertIn("progress: thinking", rest)

    def test_nonzero_exit_with_partial_result_is_22(self):
        source = "import sys; sys.stdin.read(); print('partial finding'); sys.exit(7)"
        err = self.run_fake_error("claude-code", source)
        self.assertEqual(err.code, 22)
        self.assertIn("7", err.message)
        self.assertEqual((err.run_dir / "review.md").read_text(), "partial finding\n")

    def test_empty_or_whitespace_result_is_23(self):
        for body in ("", "print('   ')"):
            with self.subTest(body=body):
                err = self.run_fake_error("claude-code", "import sys; sys.stdin.read()\n" + body)
                self.assertEqual(err.code, 23)
                self.assertTrue((err.run_dir / "run.log").exists())

    def test_codex_missing_output_is_23(self):
        source = "import sys; sys.stdin.read(); print('progress only')"
        err = self.run_fake_error("codex", source)
        self.assertEqual(err.code, 23)

    def test_cli_disappearing_after_which_is_21(self):
        def gone(*args, **kwargs):
            return [str(self.repo.parent / "vanished-cli")]
        with mock.patch.object(cr, "build_run_command", gone):
            with self.assertRaises(cr.CrossReviewError) as caught:
                cr.run_review("codex", self.repo, self.brief, None, None, self.env)
        self.assertEqual(caught.exception.code, 21)

    def test_claude_plain_text_with_exit_zero_is_23_and_kept(self):
        err = self.run_fake_error("claude-code", "import sys; sys.stdin.read(); print('not json')")
        self.assertEqual(err.code, 23)
        self.assertEqual((err.run_dir / "review.md").read_text(), "not json\n")
        self.assertTrue((err.run_dir / "claude-output.json").exists())
        self.assertEqual(
            stat.S_IMODE(os.lstat(err.run_dir / "claude-output.json").st_mode), 0o600)
        self.assertIn("claude output is not JSON with a result",
                      (err.run_dir / "run.log").read_text())

    def test_claude_blank_result_is_23(self):
        source = ("import json,sys; sys.stdin.read(); "
                  "sys.stdout.write(json.dumps({'result': '   '}))")
        err = self.run_fake_error("claude-code", source)
        self.assertEqual(err.code, 23)
        self.assertFalse((err.run_dir / "claude-output.json").exists())

    def test_claude_json_result_with_nonzero_exit_is_22(self):
        source = ("import json,sys; sys.stdin.read(); "
                  "sys.stdout.write(json.dumps({'result': 'partial'})); sys.exit(7)")
        err = self.run_fake_error("claude-code", source)
        self.assertEqual(err.code, 22)
        self.assertEqual((err.run_dir / "review.md").read_text(), "partial")

    def test_unicode_brief(self):
        text = "Огляд плану: перевір усе \u2713 \U0001f600"
        self.brief.write_text(text, encoding="utf-8")
        source = ("import json,sys; data = sys.stdin.buffer.read().decode('utf-8'); "
                  "sys.stdout.write(json.dumps({'result': 'echo:' + data}))")
        run_dir = self.run_fake("claude-code", source)
        self.assertEqual((run_dir / "brief.md").read_text(encoding="utf-8"), text)
        self.assertEqual((run_dir / "review.md").read_text(encoding="utf-8"), "echo:" + text)

    def test_popen_has_no_shell_or_timeout_and_uses_child_env(self):
        real_popen = subprocess.Popen
        with mock.patch.object(cr.subprocess, "Popen", side_effect=real_popen) as popen:
            self.run_fake("claude-code", FAKE_CLAUDE)
        # The first Popen is the --version probe; the review spawn is the last one.
        calls = [c for c in popen.call_args_list if c.args[0][-1:] != ["--version"]]
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertIsInstance(args[0] if args else kwargs["args"], list)
        self.assertFalse(kwargs.get("shell", False))
        self.assertNotIn("timeout", kwargs)
        self.assertEqual(kwargs["cwd"], str(self.repo.resolve()))
        self.assertEqual(kwargs["env"]["CROSS_REVIEW_DEPTH"], "1")
        self.assertEqual(kwargs["umask"], 0o077)
        self.assertNotIn("capture_output", kwargs)


class RunDirSafetyTests(RunnerTestCase):
    def permissive(self):
        old = os.umask(0)
        self.addCleanup(os.umask, old)

    def test_modes_and_owner_under_permissive_umask(self):
        self.permissive()
        run_dir = self.run_fake("codex", FAKE_CODEX)
        for path, mode in [(self.root, 0o700), (run_dir, 0o700)] + \
                [(run_dir / n, 0o600) for n in ARTIFACTS + ("usage.json",)]:
            with self.subTest(path=path.name):
                st = os.lstat(path)
                self.assertEqual(stat.S_IMODE(st.st_mode), mode)
                self.assertEqual(st.st_uid, os.getuid())

    def test_codex_output_replaced_with_loose_mode_is_tightened(self):
        self.permissive()
        source = FAKE_CODEX.replace(
            "open(sys.argv[2],'w').write(",
            "os.unlink(sys.argv[2]); os.umask(0); "
            "os.close(os.open(sys.argv[2], os.O_WRONLY|os.O_CREAT, 0o666)); "
            "open(sys.argv[2],'w').write(")
        run_dir = self.run_fake("codex", source)
        self.assertEqual(stat.S_IMODE(os.lstat(run_dir / "review.md").st_mode), 0o600)

    def test_replaced_artifact_is_logged_and_fails(self):
        source = FAKE_CODEX.replace(
            "open(sys.argv[2],'w').write(",
            "os.unlink(sys.argv[2]); os.symlink('/dev/null', sys.argv[2]); (lambda *a: None)(")
        err = self.run_fake_error("codex", source)
        self.assertEqual(err.code, cr.EXIT_REVIEWER_FAILED)
        log = (err.run_dir / "run.log").read_text()
        self.assertIn("cross-review: exit status 0\n", log)
        self.assertIn("cross-review: unsafe artifact after run: ", log)

    def test_new_root_gets_0700_even_under_strict_umask(self):
        old = os.umask(0o277)
        self.addCleanup(os.umask, old)
        run_dir = self.run_fake("claude-code", FAKE_CLAUDE)
        self.assertEqual(stat.S_IMODE(os.lstat(self.root).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.lstat(run_dir).st_mode), 0o700)

    def test_existing_loose_root_is_not_repaired(self):
        self.root.mkdir()
        os.chmod(self.root, 0o750)
        self.assertEqual(self.run_fake_error("claude-code", FAKE_CLAUDE).code, 2)
        self.assertEqual(stat.S_IMODE(os.lstat(self.root).st_mode), 0o750)

    def test_symlinked_root_is_rejected(self):
        target = self.tmpdir / "elsewhere"
        target.mkdir(mode=0o700)
        self.root.symlink_to(target)
        err = self.run_fake_error("claude-code", FAKE_CLAUDE)
        self.assertEqual(err.code, 2)
        self.assertEqual(list(target.iterdir()), [])

    def test_group_accessible_root_is_rejected(self):
        self.root.mkdir()
        os.chmod(self.root, 0o755)
        err = self.run_fake_error("claude-code", FAKE_CLAUDE)
        self.assertEqual(err.code, 2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_same_second_runs_do_not_collide(self):
        with mock.patch.object(cr, "_timestamp", return_value="20261003-120000"):
            first = self.run_fake("claude-code", FAKE_CLAUDE)
            first_review = (first / "review.md").read_text()
            second = self.run_fake("claude-code", FAKE_CLAUDE)
            third = self.run_fake("claude-code", FAKE_CLAUDE)
        self.assertEqual(first.name, "20261003-120000")
        self.assertEqual(second.name, "20261003-120000-1")
        self.assertEqual(third.name, "20261003-120000-2")
        self.assertEqual((first / "review.md").read_text(), first_review)


class InterruptTests(RunnerTestCase):
    def interrupt(self, sig):
        pid_file = self.tmpdir / "child.pid"
        wrapper = (
            "import sys, tempfile; "
            "sys.path.insert(0, %r); import cross_review as cr; "
            "tempfile.tempdir = %r; "
            "src = \"import os,sys,time; sys.stdin.read(); open(%r,'w').write(str(os.getpid())); "
            "sys.stdout.write('partial'); sys.stdout.flush(); "
            "sys.stderr.write('ready\\\\n'); sys.stderr.flush(); time.sleep(60)\"; "
            "cr.shutil.which = lambda name: sys.executable; "
            "cr.build_run_command = lambda *a, **k: [sys.executable, '-c', src]; "
            "sys.exit(cr.main(['run', '--agent', 'claude-code', '--repo', %r, "
            "'--brief', %r]))"
        ) % (os.path.dirname(SCRIPT), str(self.tmpdir), str(pid_file), str(self.repo),
             str(self.brief))
        proc = subprocess.Popen([sys.executable, "-c", wrapper], env=self.env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        deadline = time.time() + 20
        log = None
        while time.time() < deadline:
            logs = list(self.root.glob("*/run.log")) if self.root.exists() else []
            if logs and "ready" in logs[0].read_text():
                log = logs[0]
                break
            time.sleep(0.05)
        self.assertIsNotNone(log, "fake reviewer never became ready")
        child = int(pid_file.read_text())
        proc.send_signal(sig)
        out, err = proc.communicate(timeout=20)
        self.assertEqual(proc.returncode, 130, err)
        self.assertNotIn("Traceback", err)
        self.assertIn(str(log.parent), out)
        self.assertEqual((log.parent / "review.md").read_text(), "partial")
        self.assertIn("interrupted", log.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_sigint_keeps_partial_artifacts_and_stops_reviewer(self):
        self.interrupt(signal.SIGINT)

    def test_sigterm_keeps_partial_artifacts_and_stops_reviewer(self):
        self.interrupt(signal.SIGTERM)


NEW_SESSION = "22222222-2222-4222-8222-222222222222"

# A fake `codex`/`claude`/`agy` executable placed on PATH. It records argv, cwd, stdin
# and depth, then answers like the real CLI: Codex writes the -o file and prints
# JSONL events on stdout, Claude and agy print the --output-format json result on stdout.
FAKE_CLI = r"""
import json, os, sys, uuid
name = os.path.basename(sys.argv[0])
data = sys.stdin.read()
record = {"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": data,
          "depth": os.environ.get("CROSS_REVIEW_DEPTH")}
path = os.path.join(os.environ["FAKE_RECORD"], "%s-%s.json" % (name, uuid.uuid4()))
with open(path, "w") as fh:
    json.dump(record, fh)
answer = "Target reviewed: fixture\nFollow-up handled\n"
if name == "codex":
    sys.stdout.write("progress line\n")
    new = os.environ.get("FAKE_NEW_SESSION", "")
    if new:
        sys.stdout.write(json.dumps({"type": "thread.started", "thread_id": new}) + "\n")
    sys.stdout.write(json.dumps({"type": "turn.completed", "usage": {
        "input_tokens": 1000, "cached_input_tokens": 400, "cache_write_input_tokens": 0,
        "output_tokens": 100, "reasoning_output_tokens": 20}}) + "\n")
    out = sys.argv[sys.argv.index("-o") + 1]
    with open(out, "w") as fh:
        fh.write(answer)
elif name == "agy":
    # FAKE_AGY_USAGE "input,output" sets the reported (cumulative on resume) tokens;
    # FAKE_AGY_MODE is "denied", "error" (exit 1), "error0" (ERROR with exit 0), or
    # "hang" (a complete answer, then no exit).
    inp, outp = os.environ.get("FAKE_AGY_USAGE", "10,5").split(",")
    mode = os.environ.get("FAKE_AGY_MODE", "")
    session = os.environ.get("FAKE_AGY_SESSION") or (
        sys.argv[sys.argv.index("--conversation") + 1] if "--conversation" in sys.argv
        else os.environ.get("FAKE_NEW_SESSION") or str(uuid.uuid4()))
    if mode.startswith("error"):
        sys.stdout.write(json.dumps({"status": "ERROR", "error": "model not found",
                                     "conversation_id": ""}))
        sys.exit(1 if mode == "error" else 0)
    result = {"conversation_id": session, "status": "SUCCESS", "response": answer,
              "usage": {"input_tokens": int(inp), "output_tokens": int(outp),
                        "thinking_tokens": 0, "cache_read_tokens": 0}}
    if mode == "denied":
        result["response"] = ""
        result["denied_actions"] = [{"action": "command", "display_name": "git show"}]
        sys.stderr.write("jetski: no output produced\n")
    sys.stdout.write(json.dumps(result))
    if mode == "hang":
        # agy finished its answer but the process does not exit.
        sys.stdout.flush()
        import time
        time.sleep(60)
else:
    # FAKE_CLAUDE_USAGE "cost,input,output" sets the reported (cumulative on resume) figures;
    # an input of "-" omits modelUsage.
    cost, inp, outp = os.environ.get("FAKE_CLAUDE_USAGE", "0.01,10,5").split(",")
    flag = "--resume" if "--resume" in sys.argv else "--session-id"
    session = os.environ.get("FAKE_CLAUDE_SESSION") or sys.argv[sys.argv.index(flag) + 1]
    result = {"type": "result", "result": answer, "session_id": session,
              "total_cost_usd": float(cost)}
    if inp != "-":
        result["modelUsage"] = {"claude-opus-5-5": {"inputTokens": int(inp),
                                                    "outputTokens": int(outp)}}
    sys.stdout.write(json.dumps(result))
"""


def expected_claude_resume(session, model="claude-opus-5-5", effort="medium"):
    # Literal duplicate of the Task 2 policy with --resume instead of --session-id.
    return [
        "claude", "-p", "--output-format", "json", "--model", model, "--effort", effort,
        "--permission-mode", "default", "--tools", "Read,Grep,Glob",
        "--allowedTools", "Read,Grep,Glob", "--disallowedTools",
        "Write,Edit,NotebookEdit,Bash,Agent,Skill,mcp__*",
        "--strict-mcp-config", "--disable-slash-commands", "--safe-mode",
        "--restricted", "--setting-sources", "",
        "--resume", session,
    ]


def expected_agy_resume(session, model="gemini-4-argon", effort="medium"):
    return expected_agy(model, effort) + ["--conversation", session]


def expected_codex_resume(run, session, model="gpt-6.1-sol", effort="low", repo=None):
    return [
        "codex", "exec", "resume", "--json", "-m", model,
        "-c", 'model_reasoning_effort="%s"' % effort,
        "-c", 'sandbox_mode="read-only"',
        "-c", trust_token(Path(repo).resolve()),
        "-o", str(run / "review.md"), session, "-",
    ]


def dir_digest(path):
    out = {}
    for child in sorted(Path(path).iterdir()):
        st = os.lstat(child)
        out[child.name] = (stat.S_IMODE(st.st_mode),
                           hashlib.sha256(child.read_bytes()).hexdigest())
    return out


def git(*args):
    subprocess.run(["git"] + list(args), check=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


HAS_GIT = shutil.which("git") is not None


def make_main_repo(path):
    path.mkdir()
    git("-C", str(path), "init", "-q")
    git("-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t",
        "commit", "-q", "--allow-empty", "-m", "x")
    return path


def make_bare_worktree(base, main):
    """Clone main as base/'bare store.git' and add the worktree base/'bare wt'."""
    bare, worktree = base / "bare store.git", base / "bare wt"
    git("clone", "-q", "--bare", str(main), str(bare))
    git("-C", str(bare), "worktree", "add", "-q", "--detach", str(worktree))
    return bare, worktree


@unittest.skipUnless(HAS_GIT, "git is not installed")
class UntrustedPathTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.main = make_main_repo(self.base / "main repo")

    def no_git(self):
        return mock.patch.object(cr, "_git_line", return_value=None)

    def linked(self, name="linked wt"):
        worktree = self.base / name
        git("-C", str(self.main), "worktree", "add", "-q", "--detach", str(worktree))
        return worktree

    def test_bare_worktree_adds_common_dir_and_its_parent(self):
        bare, worktree = make_bare_worktree(self.base, self.main)
        expected = [str(worktree), str(self.base), str(bare)]
        self.assertEqual(cr.codex_untrusted_paths(worktree), expected)
        with self.no_git():
            self.assertEqual(cr.codex_untrusted_paths(worktree), expected)

    def test_separate_git_dir_adds_common_dir_parent(self):
        store = self.base / "store" / "sep.git"
        store.parent.mkdir()
        repo = self.base / "sep repo"
        git("init", "-q", "--separate-git-dir", str(store), str(repo))
        expected = [str(repo), str(store.parent), str(store)]
        self.assertEqual(cr.codex_untrusted_paths(repo), expected)
        with self.no_git():
            self.assertEqual(cr.codex_untrusted_paths(repo), expected)

    def test_fallback_without_git_finds_main_root(self):
        worktree = self.linked()
        sub = self.main / "sub"
        sub.mkdir()
        with self.no_git():
            self.assertEqual(cr.codex_untrusted_paths(worktree),
                             [str(worktree), str(self.main)])
            self.assertEqual(cr.codex_untrusted_paths(sub), [str(sub), str(self.main)])

    def test_git_redirect_variables_are_ignored(self):
        other = make_main_repo(self.base / "other repo")
        worktree = self.linked()
        redirect = {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other),
                    "GIT_COMMON_DIR": str(other / ".git"),
                    "GIT_CEILING_DIRECTORIES": str(self.base),
                    "GIT_INDEX_FILE": str(other / ".git" / "index")}
        with mock.patch.dict(os.environ, redirect):
            self.assertEqual(cr.codex_untrusted_paths(worktree),
                             [str(worktree), str(self.main)])

    def test_unreadable_git_layout_fails_closed(self):
        broken = self.base / "broken"
        broken.mkdir()
        (broken / ".git").write_text("not a gitdir pointer\n")
        with self.no_git(), self.assertRaises(cr.CrossReviewError) as caught:
            cr.codex_untrusted_paths(broken)
        self.assertEqual(caught.exception.code, 2)

    def test_on_disk_spelling_is_added(self):
        cased = self.base / "CaseDir"
        cased.mkdir()
        lower = self.base / "casedir"
        if not lower.exists() or not hasattr(cr.fcntl, "F_GETPATH"):
            self.skipTest("needs a case-insensitive file system with F_GETPATH")
        self.assertEqual(cr.codex_untrusted_paths(lower), [str(lower), str(cased)])

    def tearDown(self):
        self._tmp.cleanup()

    def test_plain_repo(self):
        self.assertEqual(cr.codex_untrusted_paths(self.main), [str(self.main)])

    def test_subdirectory_adds_toplevel(self):
        sub = self.main / "sub dir"
        sub.mkdir()
        self.assertEqual(cr.codex_untrusted_paths(sub), [str(sub), str(self.main)])

    def test_linked_worktree_adds_main_root(self):
        worktree = self.base / "linked wt"
        git("-C", str(self.main), "worktree", "add", "-q", "--detach", str(worktree))
        self.assertEqual(cr.codex_untrusted_paths(worktree),
                         [str(worktree), str(self.main)])
        argv = cr.build_run_command("codex", worktree, self.base / "run", "m", "low", SESSION)
        self.assertIn(trust_token(worktree, self.main), argv)

    def test_non_git_directory(self):
        plain = self.base / "plain"
        plain.mkdir()
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.base)}):
            self.assertEqual(cr.codex_untrusted_paths(plain), [str(plain)])

    def test_old_git_without_path_format_still_finds_main_root(self):
        worktree = self.base / "old wt"
        git("-C", str(self.main), "worktree", "add", "-q", "--detach", str(worktree))
        real_run = subprocess.run

        def old_git(argv, *args, **kwargs):
            if "--path-format=absolute" in argv:
                return subprocess.CompletedProcess(argv, 129, b"", b"")
            return real_run(argv, *args, **kwargs)

        with mock.patch.object(cr.subprocess, "run", side_effect=old_git):
            self.assertEqual(cr.codex_untrusted_paths(worktree),
                             [str(worktree), str(self.main)])
            self.assertEqual(cr.codex_untrusted_paths(self.main), [str(self.main)])

    def test_missing_git_falls_back_to_repo(self):
        with mock.patch.object(cr.subprocess, "run", side_effect=FileNotFoundError("git")):
            self.assertEqual(cr.codex_untrusted_paths(self.main), [str(self.main)])


class ResumeArgvTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo dir"
        self.repo.mkdir()
        self.run = Path(self._tmp.name) / "new run"

    def tearDown(self):
        self._tmp.cleanup()

    def test_claude_resume_argv(self):
        self.assertEqual(
            cr.build_resume_command("claude-code", self.repo, self.run, "claude-opus-5-5",
                                    "medium", SESSION),
            expected_claude_resume(SESSION))

    def test_codex_resume_argv(self):
        argv = cr.build_resume_command("codex", self.repo, self.run, "gpt-6.1-sol",
                                       "low", SESSION, untrusted=[str(self.repo.resolve())])
        self.assertEqual(argv, expected_codex_resume(self.run, SESSION, repo=self.repo))
        for banned in ("-s", "-C", "--last", "--session-id"):
            self.assertNotIn(banned, argv)

    def test_antigravity_resume_argv(self):
        self.assertEqual(
            cr.build_resume_command("antigravity", self.repo, self.run, "gemini-4-argon",
                                    "medium", SESSION),
            expected_agy_resume(SESSION))

    def test_overrides_change_only_model_and_effort(self):
        self.assertEqual(
            cr.build_resume_command("claude-code", self.repo, self.run, "m2", "high", SESSION),
            expected_claude_resume(SESSION, "m2", "high"))
        self.assertEqual(
            cr.build_resume_command("codex", self.repo, self.run, "m3", "xhigh", SESSION,
                                    untrusted=[str(self.repo.resolve())]),
            expected_codex_resume(self.run, SESSION, "m3", "xhigh", repo=self.repo))

    def test_invalid_session_or_reviewer(self):
        for reviewer, session, code in [("claude-code", "nope", 24), ("codex", "", 24),
                                        ("antigravity", "", 24), ("gemini", SESSION, 2)]:
            with self.subTest(reviewer=reviewer, session=session):
                with self.assertRaises(cr.CrossReviewError) as caught:
                    cr.build_resume_command(reviewer, self.repo, self.run, "m", "low", session)
                self.assertEqual(caught.exception.code, code)


class ResumeTests(RunnerTestCase):
    def setUp(self):
        super().setUp()
        base = Path(self._tmp.name)
        self.bin = base / "fake bin"
        self.bin.mkdir()
        for name in ("codex", "claude", "agy"):
            path = self.bin / name
            path.write_text("#!%s\n%s" % (sys.executable, FAKE_CLI))
            path.chmod(0o755)
        self.record = base / "record"
        self.record.mkdir()
        self.env["PATH"] = "%s%s%s" % (self.bin, os.pathsep, self.env.get("PATH", ""))
        self.env["FAKE_RECORD"] = str(self.record)
        self.env["FAKE_NEW_SESSION"] = SESSION
        self.elsewhere = base / "elsewhere"
        self.elsewhere.mkdir()

    def records(self):
        out = []
        for path in sorted(self.record.iterdir(), key=lambda p: p.stat().st_mtime_ns):
            out.append(json.loads(path.read_text()))
        return out

    def original(self, reviewer):
        """Create an authentic original run through the real builder and fake CLI."""
        run_dir = cr.run_review(reviewer, self.repo, self.brief, None, None, self.env)
        for path in self.record.iterdir():
            path.unlink()
        return run_dir

    def resume(self, run_dir, prompt="Re-check the second finding.", env=None):
        cwd = os.getcwd()
        os.chdir(self.elsewhere)
        try:
            return cr.resume_review(run_dir, prompt, env or self.env)
        finally:
            os.chdir(cwd)

    def test_resume_session_total_adds_the_original(self):
        original = self.original("codex")
        new_dir = self.resume(original)
        usage = json.loads((new_dir / "usage.json").read_text())
        self.assertEqual(usage["previous_run"], str(original))
        # Each fake codex turn: (600 * 2.00 + 400 * 0.10 + 100 * 10.00) / 1e6 = 0.00224
        self.assertEqual(usage["cost_usd"], 0.0022)
        self.assertEqual(usage["session_total"], {
            "tokens": {"input": 2000, "cached_input": 800, "cache_write": 0,
                       "output": 200, "reasoning": 40},
            "cost_usd": 0.0044, "runs": 2, "complete": True})

    def test_resume_without_previous_usage_is_incomplete(self):
        original = self.original("codex")
        (original / "usage.json").unlink()
        new_dir = self.resume(original)
        total = json.loads((new_dir / "usage.json").read_text())["session_total"]
        self.assertEqual((total["runs"], total["complete"]), (1, False))

    def test_chained_resume_accumulates_three_runs(self):
        first = self.original("codex")
        second = self.resume(first)
        third = self.resume(second)
        total = json.loads((third / "usage.json").read_text())["session_total"]
        self.assertEqual(total["runs"], 3)
        self.assertTrue(total["complete"])
        # Sums the stored rounded per-run values: 0.0022 + 0.0044, not 3 * 0.00224.
        self.assertEqual(total["cost_usd"], round(3 * 0.0022, 4))
        self.assertEqual(total["tokens"]["input"], 3000)

    def claude_usage(self, run_dir):
        return json.loads((run_dir / "usage.json").read_text())

    def test_claude_resume_usage_from_cumulative_totals(self):
        # Original reports 0.03 and 100/20; the resume reports the cumulative 0.04 and
        # 250/50, so this run is 0.01 and 150/30.
        self.env["FAKE_CLAUDE_USAGE"] = "0.03,100,20"
        original = self.original("claude-code")
        self.env["FAKE_CLAUDE_USAGE"] = "0.04,250,50"
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), \
                redirect_stdout(out), redirect_stderr(err):
            code = cr.main(["resume", "--run-dir", str(original), "--prompt", "Re-check."])
        self.assertEqual(code, 0, err.getvalue())
        new_dir = [d for d in self.run_dirs() if d != original][0]
        usage = self.claude_usage(new_dir)
        self.assertEqual(usage["tokens"], {"input": 150, "cached_input": 0,
                                           "cache_write": 0, "output": 30,
                                           "reasoning": 0})
        self.assertEqual(usage["cost_usd"], 0.01)
        self.assertEqual(usage["session_total"], {
            "tokens": {"input": 250, "cached_input": 0, "cache_write": 0,
                       "output": 50, "reasoning": 0},
            "cost_usd": 0.04, "runs": 2, "complete": True})
        output = out.getvalue().strip()
        self.assertIn("$0.01", output)  # Cost line
        self.assertIn("$0.04 over 2 runs", output)  # Session line
        self.assertNotIn("incomplete", output)
        self.assertNotIn("usage incomplete", (new_dir / "run.log").read_text())

    def test_claude_resume_without_previous_usage_logs_the_reason(self):
        original = self.original("claude-code")
        (original / "usage.json").unlink()
        new_dir = self.resume(original)
        usage = self.claude_usage(new_dir)
        self.assertEqual((usage["tokens"], usage["cost_usd"]), (None, None))
        self.assertEqual((usage["session_total"]["runs"], usage["session_total"]["complete"],
                          usage["session_total"]["cost_usd"]), (1, True, 0.01))
        self.assertIn("usage incomplete: previous session total unavailable",
                      (new_dir / "run.log").read_text())

    def test_claude_resume_after_incomplete_previous_total_logs_the_reason(self):
        # The first run has no token counts, so its session_total holds zero placeholders.
        self.env["FAKE_CLAUDE_USAGE"] = "0.03,-,-"
        original = self.original("claude-code")
        self.assertFalse(self.claude_usage(original)["session_total"]["complete"])
        self.env["FAKE_CLAUDE_USAGE"] = "0.04,250,50"
        new_dir = self.resume(original)
        usage = self.claude_usage(new_dir)
        self.assertEqual((usage["tokens"], usage["cost_usd"]), (None, None))
        self.assertEqual(usage["session_total"], {
            "tokens": {"input": 250, "cached_input": 0, "cache_write": 0,
                       "output": 50, "reasoning": 0},
            "cost_usd": 0.04, "runs": 2, "complete": True})
        self.assertIn("usage incomplete: previous session total unavailable",
                      (new_dir / "run.log").read_text())

    def test_claude_resume_into_another_session_logs_the_reason(self):
        original = self.original("claude-code")
        self.env["FAKE_CLAUDE_SESSION"] = NEW_SESSION
        new_dir = self.resume(original)
        usage = self.claude_usage(new_dir)
        self.assertEqual((usage["tokens"], usage["cost_usd"]), (None, None))
        self.assertIn("usage incomplete: claude resumed into a different session",
                      (new_dir / "run.log").read_text())

    def test_claude_chained_resume_takes_the_last_reported_total(self):
        self.env["FAKE_CLAUDE_USAGE"] = "0.03,100,20"
        first = self.original("claude-code")
        self.env["FAKE_CLAUDE_USAGE"] = "0.04,250,50"
        second = self.resume(first)
        self.env["FAKE_CLAUDE_USAGE"] = "0.07,400,90"
        third = self.resume(second)
        usage = self.claude_usage(third)
        self.assertEqual(usage["session_total"], {
            "tokens": {"input": 400, "cached_input": 0, "cache_write": 0,
                       "output": 90, "reasoning": 0},
            "cost_usd": 0.07, "runs": 3, "complete": True})
        self.assertEqual(usage["cost_usd"], 0.03)
        self.assertEqual((usage["tokens"]["input"], usage["tokens"]["output"]), (150, 40))

    def test_antigravity_run_and_resume_through_the_real_builders(self):
        self.env.pop("FAKE_NEW_SESSION")
        self.env["FAKE_AGY_USAGE"] = "100,20"
        original = cr.run_review("antigravity", self.repo, self.brief, None, None, self.env)
        [record] = self.records()
        self.assertEqual(record["argv"], expected_agy()[1:])
        self.assertEqual((record["stdin"], record["depth"]), ("fixture brief", "1"))
        self.assertEqual(os.path.realpath(record["cwd"]), os.path.realpath(self.repo))
        session = (original / "session.txt").read_text().strip()
        self.assertTrue(cr._is_uuid(session))
        self.assertFalse((original / "agy-output.json").exists())
        self.assertEqual((original / "review.md").read_text(),
                         "Target reviewed: fixture\nFollow-up handled\n")
        first = self.claude_usage(original)
        self.assertEqual(first["session_total"]["complete"], True)
        self.assertNotIn("usage incomplete", (original / "run.log").read_text())
        for path in self.record.iterdir():
            path.unlink()

        self.env["FAKE_AGY_USAGE"] = "250,50"
        new_dir = self.resume(original)
        [record] = self.records()
        self.assertEqual(record["argv"], expected_agy_resume(session)[1:])
        self.assertEqual((new_dir / "session.txt").read_text().strip(), session)
        usage = self.claude_usage(new_dir)
        self.assertEqual((usage["tokens"]["input"], usage["tokens"]["output"]), (150, 30))
        self.assertEqual(usage["session_total"]["runs"], 2)
        self.assertTrue(usage["session_total"]["complete"])
        self.assertNotIn("usage incomplete", (new_dir / "run.log").read_text())

    def test_antigravity_resume_into_a_new_conversation_exits_24(self):
        original = self.original("antigravity")
        self.env["FAKE_AGY_SESSION"] = NEW_SESSION
        with self.assertRaises(cr.CrossReviewError) as caught:
            self.resume(original)
        self.assertEqual(caught.exception.code, 24)
        new_dir = caught.exception.run_dir
        log = (new_dir / "run.log").read_text()
        self.assertIn("agy started conversation %s instead of resuming %s"
                      % (NEW_SESSION, SESSION), log)
        self.assertIn("usage incomplete: agy resumed into a different session", log)
        self.assertEqual((new_dir / "session.txt").read_text().strip(), NEW_SESSION)

    def test_antigravity_denied_tool_call_exits_23_and_keeps_the_raw_output(self):
        self.env["FAKE_AGY_MODE"] = "denied"
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.run_review("antigravity", self.repo, self.brief, None, None, self.env)
        self.assertEqual(caught.exception.code, 23)
        self.assertIn("denied", caught.exception.message)
        run_dir = caught.exception.run_dir
        log = (run_dir / "run.log").read_text()
        self.assertIn('agy denied: "git show"', log)
        self.assertIn("jetski: no output produced", log)
        self.assertTrue((run_dir / "agy-output.json").exists())
        self.assertIn("denied_actions", (run_dir / "review.md").read_text())

    def test_antigravity_error_status_exits_22(self):
        for mode in ("error", "error0"):
            with self.subTest(mode=mode):
                self.env["FAKE_AGY_MODE"] = mode
                with self.assertRaises(cr.CrossReviewError) as caught:
                    cr.run_review("antigravity", self.repo, self.brief, None, None,
                                  self.env)
                self.assertEqual(caught.exception.code, 22)
                log = (caught.exception.run_dir / "run.log").read_text()
                self.assertIn('agy error: "model not found"', log)
                self.assertIn('agy status "ERROR"', log)

    def test_resume_with_relative_run_dir_stores_absolute_previous_run(self):
        original = self.original("codex")
        cwd = os.getcwd()
        os.chdir(original.parent)
        self.addCleanup(os.chdir, cwd)
        new_dir = cr.resume_review(Path(original.name), "Re-check.", self.env)
        usage = json.loads((new_dir / "usage.json").read_text())
        self.assertTrue(os.path.isabs(usage["previous_run"]), usage["previous_run"])
        self.assertEqual(Path(usage["previous_run"]).resolve(), original.resolve())

    def resume_error(self, run_dir, **kwargs):
        with mock.patch.object(cr.subprocess, "Popen") as popen:
            with self.assertRaises(cr.CrossReviewError) as caught:
                self.resume(run_dir, **kwargs)
        popen.assert_not_called()
        return caught.exception

    def test_codex_resume_round_trip(self):
        original = self.original("codex")
        before = dir_digest(original)
        self.env["FAKE_NEW_SESSION"] = NEW_SESSION
        new_dir = self.resume(original)
        self.assertEqual(dir_digest(original), before)
        self.assertNotEqual(new_dir, original)
        self.assertEqual(new_dir.parent, original.parent)
        [rec] = self.records()
        self.assertEqual(rec["argv"],
                         expected_codex_resume(new_dir, SESSION, repo=self.repo)[1:])
        self.assertEqual(os.path.realpath(rec["cwd"]), os.path.realpath(self.repo))
        self.assertEqual(rec["depth"], "1")
        self.assertIn("Re-check the second finding.", rec["stdin"])
        self.assertIn("read-only", rec["stdin"])
        self.assertNotIn("fixture brief", rec["stdin"])
        self.assertEqual((new_dir / "brief.md").read_text(), rec["stdin"])
        self.assertEqual((new_dir / "review.md").read_text(),
                         "Target reviewed: fixture\nFollow-up handled\n")
        self.assertEqual((new_dir / "session.txt").read_text().strip(), NEW_SESSION)
        header = json.loads((new_dir / "run.log").read_text().split("\n", 1)[0])
        self.assertEqual(header["reviewer"], "codex")
        self.assertEqual(header["repo"], str(self.repo.resolve()))
        self.assertEqual(header["resumed_from"], str(original))
        for name in ARTIFACTS:
            self.assertEqual(stat.S_IMODE(os.lstat(new_dir / name).st_mode), 0o600)

    def layout_round_trip(self, repo, trust):
        run_dir = cr.run_review("codex", repo, self.brief, None, None, self.env)
        [rec] = self.records()
        self.assertEqual(rec["argv"], expected_codex(repo, run_dir, trust=trust)[1:])
        new_dir = self.resume(run_dir)
        rec = self.records()[-1]
        expected = expected_codex_resume(new_dir, SESSION, repo=repo)[1:]
        expected[expected.index(trust_token(repo))] = trust
        self.assertEqual(rec["argv"], expected)

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_linked_worktree_run_and_resume_mark_main_root_untrusted(self):
        base = Path(self._tmp.name).resolve()
        main = make_main_repo(base / "main repo")
        worktree = base / "linked wt"
        git("-C", str(main), "worktree", "add", "-q", "--detach", str(worktree))
        self.layout_round_trip(worktree, trust_token(worktree, main))

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_bare_worktree_run_and_resume_mark_common_dir_untrusted(self):
        base = Path(self._tmp.name).resolve()
        bare, worktree = make_bare_worktree(base, make_main_repo(base / "main repo"))
        self.layout_round_trip(worktree, trust_token(worktree, base, bare))

    def test_path_set_failure_is_2_before_run_dir(self):
        with mock.patch.object(cr, "codex_untrusted_paths",
                               side_effect=cr.CrossReviewError(2, "layout")), \
                mock.patch.object(cr.subprocess, "Popen") as popen:
            with self.assertRaises(cr.CrossReviewError) as caught:
                cr.run_review("codex", self.repo, self.brief, None, None, self.env)
        self.assertEqual(caught.exception.code, 2)
        self.assertIsNone(caught.exception.run_dir)
        popen.assert_not_called()
        self.assertEqual(self.run_dirs(), [])

    def test_codex_run_through_real_builder_forces_repo_untrusted(self):
        run_dir = cr.run_review("codex", self.repo, self.brief, None, None, self.env)
        [rec] = self.records()
        self.assertEqual(rec["argv"], expected_codex(self.repo.resolve(), run_dir)[1:])

    def test_codex_resume_without_new_id_keeps_original(self):
        original = self.original("codex")
        self.env["FAKE_NEW_SESSION"] = ""
        new_dir = self.resume(original)
        self.assertEqual((new_dir / "session.txt").read_text().strip(), SESSION)

    def test_claude_resume_round_trip(self):
        original = self.original("claude-code")
        session = (original / "session.txt").read_text().strip()
        before = dir_digest(original)
        new_dir = self.resume(original)
        self.assertEqual(dir_digest(original), before)
        [rec] = self.records()
        self.assertEqual(rec["argv"], expected_claude_resume(session)[1:])
        self.assertNotIn("--session-id", rec["argv"])
        self.assertEqual(os.path.realpath(rec["cwd"]), os.path.realpath(self.repo))
        self.assertEqual((new_dir / "session.txt").read_text().strip(), session)

    def test_chained_resume_uses_new_run_metadata(self):
        original = self.original("codex")
        self.env["FAKE_NEW_SESSION"] = NEW_SESSION
        second = self.resume(original)
        third = self.resume(second, prompt="One more question.")
        self.assertEqual(len({original, second, third}), 3)
        rec = self.records()[-1]
        self.assertIn(NEW_SESSION, rec["argv"])

    def test_resume_keeps_model_and_effort_from_header(self):
        run_dir = cr.run_review("codex", self.repo, self.brief, "gpt-x", "high", self.env)
        new_dir = self.resume(run_dir)
        rec = self.records()[-1]
        self.assertEqual(rec["argv"], expected_codex_resume(new_dir, SESSION, "gpt-x",
                                                            "high", repo=self.repo)[1:])

    def test_depth_wins_before_metadata(self):
        env = dict(self.env, CROSS_REVIEW_DEPTH="")
        err = self.resume_error(self.tmpdir / "does-not-exist", env=env)
        self.assertEqual(err.code, 20)

    def test_actual_main_resume_with_depth_exits_20(self):
        env = dict(self.env, CROSS_REVIEW_DEPTH="1", TMPDIR=str(self.tmpdir))
        proc = subprocess.run([sys.executable, SCRIPT, "resume", "--run-dir",
                               "/nonexistent", "--prompt", "x"], env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 20, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def corrupt(self, mutate):
        original = self.original("codex")
        mutate(original)
        return self.resume_error(original)

    def test_bad_session_is_24_without_spawn(self):
        cases = {
            "missing": lambda d: (d / "session.txt").unlink(),
            "empty": lambda d: (d / "session.txt").write_text(""),
            "invalid": lambda d: (d / "session.txt").write_text("not-a-uuid\n"),
            "symlink": lambda d: ((d / "session.txt").unlink(),
                                  (d / "session.txt").symlink_to(self.brief)),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.corrupt(mutate).code, 24)

    def test_bad_header_is_24_without_spawn(self):
        def rewrite_header(transform):
            def mutate(d):
                log = d / "run.log"
                first, rest = log.read_text().split("\n", 1)
                log.write_text(transform(first) + "\n" + rest)
            return mutate

        def with_field(key, value):
            def transform(first):
                data = json.loads(first)
                if value is KeyError:
                    del data[key]
                else:
                    data[key] = value
                return json.dumps(data)
            return transform

        cases = {
            "not json": rewrite_header(lambda first: "progress line"),
            "array": rewrite_header(lambda first: "[1, 2]"),
            "unknown schema": rewrite_header(with_field("schema_version", 99)),
            "no schema": rewrite_header(with_field("schema_version", KeyError)),
            "bad reviewer": rewrite_header(with_field("reviewer", "gemini")),
            "relative repo": rewrite_header(with_field("repo", "relative/path")),
            "missing repo": rewrite_header(with_field("repo", "/nonexistent/repo")),
            "empty model": rewrite_header(with_field("model", "")),
            "effort type": rewrite_header(with_field("effort", 3)),
            "option-like model": rewrite_header(with_field("model", "--dangerously-skip-permissions")),
            "option-like effort": rewrite_header(with_field("effort", "-x")),
            "no log": lambda d: (d / "run.log").unlink(),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.corrupt(mutate).code, 24)

    def test_unsafe_or_missing_run_dir_is_24(self):
        original = self.original("codex")
        link = self.tmpdir / "linked run"
        link.symlink_to(original)
        loose = self.original("codex")
        os.chmod(loose, 0o755)
        for run_dir in (self.tmpdir / "absent", link, self.brief, loose):
            with self.subTest(run_dir=run_dir.name):
                self.assertEqual(self.resume_error(run_dir).code, 24)

    def test_empty_prompt_is_2(self):
        original = self.original("codex")
        for prompt in ("", "   \n"):
            with self.subTest(prompt=prompt):
                self.assertEqual(self.resume_error(original, prompt=prompt).code, 2)

    def test_main_resume_prints_new_run(self):
        original = self.original("codex")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), \
                redirect_stdout(out), redirect_stderr(err):
            code = cr.main(["resume", "--run-dir", str(original), "--prompt", "again"])
        self.assertEqual(code, 0, err.getvalue())
        new_dir = [d for d in self.run_dirs() if d != original][0]
        self.assertIn("run_dir: %s" % new_dir, out.getvalue())


class UnexpectedOSErrorTests(RunnerTestCase):
    def call_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cr.main(argv)
        return code, out.getvalue(), err.getvalue()

    def run_args(self):
        return ["run", "--agent", "claude-code", "--repo", str(self.repo),
                "--brief", str(self.brief)]

    def test_root_creation_failure_is_2(self):
        disk_full = OSError(28, "No space left on device")
        with mock.patch.object(cr.os, "mkdir", side_effect=disk_full), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CROSS_REVIEW_DEPTH", None)
            code, _, err = self.call_main(self.run_args())
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn("No space left", err)

    def test_artifact_write_failure_is_22(self):
        real_write = os.write

        def failing(fd, data):
            if data.startswith(b"fixture"):
                raise OSError(5, "Input/output error")
            return real_write(fd, data)

        os.environ.pop("CROSS_REVIEW_DEPTH", None)
        with mock.patch.object(cr.os, "write", side_effect=failing), \
                mock.patch.object(cr, "build_run_command", fake_builder(FAKE_CLAUDE)):
            code, out, err = self.call_main(self.run_args())
        self.assertEqual(code, 22)
        self.assertNotIn("Traceback", err)
        self.assertIn("run_dir:", out)

    def test_spawn_os_error_is_22(self):
        os.environ.pop("CROSS_REVIEW_DEPTH", None)
        real_popen = subprocess.Popen

        def popen(argv, *args, **kwargs):
            if argv[-1:] == ["--version"]:
                return real_popen(argv, *args, **kwargs)
            raise OSError(11, "Resource temporarily unavailable")

        with mock.patch.object(cr.subprocess, "Popen", side_effect=popen), \
                mock.patch.object(cr, "build_run_command", fake_builder(FAKE_CLAUDE)):
            code, out, err = self.call_main(self.run_args())
        self.assertEqual(code, 22)
        self.assertNotIn("Traceback", err)
        run_dir = Path(out.splitlines()[0].split(": ", 1)[1])
        self.assertIn("Resource temporarily unavailable", (run_dir / "run.log").read_text())


@unittest.skipUnless(HAS_GIT, "git is not installed")
class TargetTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve() / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        (self.repo / ".gitignore").write_text("ignored.txt\n")
        (self.repo / "a.py").write_text("a\n")
        (self.repo / ".env").write_text("SECRET=1\n")
        self.commit("base")
        self.base = self.rev("HEAD")
        (self.repo / "a.py").write_text("a2\n")
        (self.repo / "config.local.toml").write_text("x\n")
        self.git("add", "-A")
        self.commit("head")

    def git(self, *args):
        git("-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t", *args)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def rev(self, ref):
        return subprocess.run(["git", "-C", str(self.repo), "rev-parse", ref], check=True,
                              stdout=subprocess.PIPE, text=True).stdout.strip()

    def test_parse_target(self):
        self.assertEqual(cr.parse_target(["working-tree"]), ("working-tree", None))
        self.assertEqual(cr.parse_target(["working-tree", "abc"]), ("working-tree", "abc"))
        self.assertEqual(cr.parse_target(["tree", "HEAD"]), ("tree", "HEAD"))
        self.assertEqual(cr.parse_target(["range", "a..b"]), ("range", "a..b"))
        for bad in ([], ["all"], ["tree"], ["working-tree", "a", "b"], ["range", "a...b"],
                    ["range", "a"], ["range", "..b"], ["tree", "a", "b"]):
            with self.subTest(bad=bad):
                with self.assertRaises(cr.CrossReviewError) as caught:
                    cr.parse_target(bad)
                self.assertEqual(caught.exception.code, 2)

    def test_range_lists_changed_files_and_excludes_local_overrides(self):
        info = cr.compute_target(self.repo, "range", self.base + "..HEAD")
        self.assertEqual(info["files"], ["a.py"])
        self.assertEqual(info["excluded"], ["config.local.toml"])
        self.assertEqual((info["base"], info["head"]), (self.base, self.rev("HEAD")))
        self.assertEqual(len(info["diff_sha256"]), 64)

    def test_tree_is_fingerprinted_by_tree_sha(self):
        info = cr.compute_target(self.repo, "tree", "HEAD")
        self.assertEqual(info["tree"], self.rev("HEAD^{tree}"))
        self.assertEqual(info["files"], [".gitignore", "a.py"])
        self.assertEqual(info["excluded"], [".env", "config.local.toml"])
        self.assertNotIn("diff_sha256", info)

    def test_working_tree_adds_untracked_and_skips_gitignored(self):
        (self.repo / "a.py").write_text("a3\n")
        (self.repo / "new.py").write_text("n\n")
        (self.repo / "ignored.txt").write_text("i\n")
        (self.repo / ".env.local").write_text("S=1\n")
        outside = Path(self._tmp.name) / "outside.txt"
        outside.write_text("o\n")
        os.symlink(outside, self.repo / "link.txt")
        info = cr.compute_target(self.repo, "working-tree", None)
        self.assertEqual(info["files"], ["a.py", "new.py"])
        self.assertEqual(info["excluded"], [".env.local", "link.txt"])
        self.assertEqual(info["untracked_sha256"],
                         {"new.py": hashlib.sha256(b"n\n").hexdigest()})
        text = cr.format_target(self.repo, info)
        self.assertIn("Files in scope (2):\n- a.py\n- new.py", text)
        self.assertIn("do not read them", text)
        self.assertIn("- link.txt", text)

    def test_working_tree_from_base_covers_commits_and_uncommitted_changes(self):
        (self.repo / "b.py").write_text("b\n")
        self.commit("later")
        (self.repo / "a.py").write_text("a3\n")
        (self.repo / "new.py").write_text("n\n")
        info = cr.compute_target(self.repo, "working-tree", self.base)
        self.assertEqual(info["files"], ["a.py", "b.py", "new.py"])
        self.assertEqual((info["base"], info["head"]), (self.base, self.rev("HEAD")))
        diff = subprocess.run(["git", "-C", str(self.repo), "diff", "--binary", self.base, "--"],
                              check=True, stdout=subprocess.PIPE).stdout
        self.assertEqual(info["diff_sha256"], hashlib.sha256(diff).hexdigest())
        self.assertIn("Base: %s" % self.base, cr.format_target(self.repo, info))
        head_only = cr.compute_target(self.repo, "working-tree", None)
        self.assertNotIn("base", head_only)
        self.assertEqual(head_only["files"], ["a.py", "new.py"])

    def test_bad_revision_is_invalid_input(self):
        for kind, ref in (("tree", "nope"), ("range", "nope..HEAD"), ("tree", "-x"),
                          ("working-tree", "nope")):
            with self.subTest(ref=ref):
                with self.assertRaises(cr.CrossReviewError) as caught:
                    cr.compute_target(self.repo, kind, ref)
                self.assertEqual(caught.exception.code, 2)


class FollowupTests(RunnerTestCase):
    def setUp(self):
        super().setUp()
        base = Path(self._tmp.name)
        self.bin = base / "fake bin"
        self.bin.mkdir()
        for name in ("codex", "claude", "agy"):
            path = self.bin / name
            path.write_text("#!%s\n%s" % (sys.executable, FAKE_CLI))
            path.chmod(0o755)
        self.record = base / "record"
        self.record.mkdir()
        self.env["PATH"] = "%s%s%s" % (self.bin, os.pathsep, self.env.get("PATH", ""))
        self.env["FAKE_RECORD"] = str(self.record)
        self.env["FAKE_NEW_SESSION"] = SESSION
        self.dispositions = base / "dispositions.md"
        self.dispositions.write_text("F1: accepted, fixed in a.py\n", encoding="utf-8")

    def last_stdin(self):
        paths = sorted(self.record.iterdir(), key=lambda p: p.stat().st_mtime_ns)
        return json.loads(paths[-1].read_text())

    def test_followup_round_carries_previous_review_and_dispositions(self):
        first = cr.run_review("codex", self.repo, self.brief, "gpt-6-astra", "high", self.env)
        second = cr.run_review(None, self.repo, self.brief, None, None, self.env,
                               followup=first, dispositions=self.dispositions)
        record = self.last_stdin()
        self.assertTrue(record["stdin"].startswith("fixture brief"))
        self.assertIn("This is review round 2 of the same target", record["stdin"])
        self.assertIn("Target reviewed: fixture", record["stdin"])
        self.assertIn("F1: accepted, fixed in a.py", record["stdin"])
        self.assertIn("ADDRESSED or NOT ADDRESSED", record["stdin"])
        # A fresh session, not a resume, with the first round's agent, model, and effort.
        self.assertNotIn("resume", record["argv"])
        self.assertIn("gpt-6-astra", record["argv"])
        self.assertIn('model_reasoning_effort="high"', record["argv"])
        header = json.loads((second / "run.log").read_text().splitlines()[0])
        self.assertEqual((header["round"], header["followup_of"]), (2, str(first)))
        usage = json.loads((second / "usage.json").read_text())
        self.assertEqual(usage["round"], 2)
        self.assertEqual(usage["target_total"]["rounds"], 2)
        self.assertEqual(usage["target_total"]["runs"], 2)
        self.assertTrue(usage["target_total"]["complete"])

    def test_followup_with_another_agent_uses_its_defaults(self):
        first = cr.run_review("codex", self.repo, self.brief, "gpt-6-astra", "high", self.env)
        cr.run_review("claude-code", self.repo, self.brief, None, None, self.env,
                      followup=first, dispositions=self.dispositions)
        argv = self.last_stdin()["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "claude-opus-5-5")
        self.assertEqual(argv[argv.index("--effort") + 1], "medium")

    def test_followup_needs_dispositions_and_a_readable_previous_run(self):
        first = cr.run_review("codex", self.repo, self.brief, None, None, self.env)
        empty = Path(self._tmp.name) / "empty.md"
        empty.write_text(" \n")
        cases = [
            dict(followup=first, dispositions=None),
            dict(followup=None, dispositions=self.dispositions),
            dict(followup=Path(self._tmp.name) / "missing", dispositions=self.dispositions),
            dict(followup=first, dispositions=empty),
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(cr.CrossReviewError) as caught:
                    cr.run_review(None, self.repo, self.brief, None, None, self.env, **kwargs)
                self.assertEqual(caught.exception.code, 2)

    def test_documents_are_hashed_and_rehashed_on_followup(self):
        plan = Path(self._tmp.name) / "plan.md"
        plan.write_text("plan v1\n")
        first = cr.run_review("codex", self.repo, self.brief, None, None, self.env,
                              documents={"plan": str(plan), "spec": None})
        self.assertIn("Plan: %s, sha256 %s" % (plan, hashlib.sha256(b"plan v1\n").hexdigest()),
                      self.last_stdin()["stdin"])
        plan.write_text("plan v2\n")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            second = cr.run_review(None, self.repo, self.brief, None, None, self.env,
                                   followup=first, dispositions=self.dispositions)
        self.assertIn(hashlib.sha256(b"plan v2\n").hexdigest(), self.last_stdin()["stdin"])
        self.assertNotIn("unchanged", stderr.getvalue())
        header = json.loads((second / "run.log").read_text().splitlines()[0])
        self.assertEqual(header["documents"]["plan"]["path"], str(plan))
        with redirect_stderr(stderr):
            cr.run_review(None, self.repo, self.brief, None, None, self.env,
                          followup=second, dispositions=self.dispositions)
        self.assertIn("target and documents unchanged since round 2", stderr.getvalue())

    def test_unreadable_document_is_invalid_input(self):
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.run_review("codex", self.repo, self.brief, None, None, self.env,
                          documents={"spec": str(Path(self._tmp.name) / "missing.md")})
        self.assertEqual(caught.exception.code, 2)

    def test_agent_is_required_without_followup(self):
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.run_review(None, self.repo, self.brief, None, None, self.env)
        self.assertEqual(caught.exception.code, 2)

    def test_legacy_claude_header_resumes_as_claude_code(self):
        first = cr.run_review("claude-code", self.repo, self.brief, None, None, self.env)
        log = first / "run.log"
        lines = log.read_text().splitlines(True)
        header = json.loads(lines[0])
        header["reviewer"] = "claude"
        del header["round"]
        os.chmod(log, 0o600)
        log.write_text(json.dumps(header) + "\n" + "".join(lines[1:]))
        new_dir = cr.resume_review(first, "Clarify F1.", self.env)
        self.assertEqual(json.loads((new_dir / "usage.json").read_text())["reviewer"],
                         "claude-code")

    def test_pass_env_reaches_the_reviewer(self):
        self.env["EXTRA_FOR_REVIEWER"] = "yes"
        source_check = ("import os,sys; sys.stdin.read(); "
                        "assert os.environ.get('EXTRA_FOR_REVIEWER') == 'yes'; "
                        "assert 'TASK_SENTINEL' not in os.environ; "
                        "open(sys.argv[2], 'w').write('Target reviewed: fixture\\n')")
        with mock.patch.object(cr, "build_run_command", fake_builder(source_check)):
            run_dir = cr.run_review("codex", self.repo, self.brief, None, None, self.env,
                                    pass_env=["EXTRA_FOR_REVIEWER"])
        header = json.loads((run_dir / "run.log").read_text().splitlines()[0])
        self.assertEqual(header["pass_env"], ["EXTRA_FOR_REVIEWER"])
        self.assertNotIn("yes", (run_dir / "run.log").read_text())


class CliArgumentTests(RunnerTestCase):
    def call_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cr.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_choices_are_enforced_before_any_run(self):
        base = ["run", "--repo", str(self.repo), "--brief", str(self.brief)]
        for extra in (["--reviewer", "bard"], ["--agent", "bard"],
                      ["--agent", "antigravity", "--effort", "minimal"],
                      ["--agent", "codex", "--effort", "auto"],
                      ["--agent", "codex", "--target", "everything"],
                      ["--agent", "codex", "--pass-env", "A=B"]):
            with self.subTest(extra=extra), \
                    mock.patch.object(cr.subprocess, "Popen") as popen:
                code, _, _ = self.call_main(base + extra)
                self.assertEqual(code, 2)
                popen.assert_not_called()
        self.assertEqual(self.run_dirs(), [])


def install_fake_bin(case):
    """Put fake codex, claude, and agy on PATH and record their calls (FAKE_CLI)."""
    base = Path(case._tmp.name)
    case.bin = base / "fake bin"
    case.bin.mkdir()
    for name in ("codex", "claude", "agy"):
        path = case.bin / name
        path.write_text("#!%s\n%s" % (sys.executable, FAKE_CLI))
        path.chmod(0o755)
    case.record = base / "record"
    case.record.mkdir()
    case.env["PATH"] = "%s%s%s" % (case.bin, os.pathsep, case.env.get("PATH", ""))
    case.env["FAKE_RECORD"] = str(case.record)
    case.env["FAKE_NEW_SESSION"] = SESSION


def last_record(case):
    paths = sorted(case.record.iterdir(), key=lambda p: p.stat().st_mtime_ns)
    return json.loads(paths[-1].read_text())


class ResolveTests(unittest.TestCase):
    def test_no_groups_is_one_reviewer_of_the_opposite_cli(self):
        self.assertEqual(cr.resolve_reviewers([], "claude-code"), [
            {"agent": "codex", "model": "gpt-6.1-sol", "effort": "low", "same_cli": False}])
        self.assertEqual(cr.resolve_reviewers([], "codex"), [
            {"agent": "claude-code", "model": "claude-opus-5-5", "effort": "medium",
             "same_cli": False}])

    def test_each_group_is_one_more_reviewer(self):
        tokens = "claude opus low gemini argon low".split()
        self.assertEqual(cr.resolve_reviewers(tokens, "claude-code"), [
            {"agent": "claude-code", "model": "claude-opus-5-5", "effort": "low",
             "same_cli": True},
            {"agent": "antigravity", "model": "gemini-4-argon", "effort": "low",
             "same_cli": False}])

    def test_model_and_effort_are_optional(self):
        cases = {
            "codex sol low": ("codex", "gpt-6.1-sol", "low"),
            "codex astra": ("codex", "gpt-6-astra", "low"),
            "codex": ("codex", "gpt-6.1-sol", "low"),
            "gemini high": ("antigravity", "gemini-4-argon", "high"),
            "gemini flash": ("antigravity", "gemini-3.8-flash", "medium"),
            "claude fable": ("claude-code", "claude-fable-5-1", "medium"),
            "claude claude-sonnet-5-5 max": ("claude-code", "claude-sonnet-5-5", "max"),
        }
        for text, (agent, model, effort) in cases.items():
            with self.subTest(text=text):
                [got] = cr.resolve_reviewers(text.split(), "codex")
                self.assertEqual((got["agent"], got["model"], got["effort"]),
                                 (agent, model, effort))

    def test_malformed_groups_are_invalid_input(self):
        for tokens in (["opus"], ["low"], ["claude", "opus", "sonnet"],
                       ["claude", "low", "opus"], ["claude", "low", "high"],
                       ["claude", "-x"], ["bard"]):
            with self.subTest(tokens=tokens):
                with self.assertRaises(cr.CrossReviewError) as caught:
                    cr.resolve_reviewers(tokens, "claude-code")
                self.assertEqual(caught.exception.code, 2)
        with self.assertRaises(cr.CrossReviewError):
            cr.resolve_reviewers([], "antigravity")

    def test_resolve_command_prints_one_json_line_per_reviewer(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cr.main(["resolve", "--host", "claude-code", "claude", "opus", "low",
                            "gemini", "argon", "low"])
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([line["agent"] for line in lines], ["claude-code", "antigravity"])
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(cr.main(["resolve", "--host", "codex"]), 0)
        self.assertEqual(json.loads(out.getvalue())["agent"], "claude-code")


class GitRunnerTestCase(RunnerTestCase):
    """A git repository with a tracked edit, a tracked .env change, and an untracked file."""

    def setUp(self):
        super().setUp()
        install_fake_bin(self)
        git("init", "-q", str(self.repo))
        (self.repo / "app.py").write_text("v1\n")
        (self.repo / ".env").write_text("TOKEN=old\n")
        self.commit("base")
        self.base = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"],
                                   check=True, stdout=subprocess.PIPE,
                                   text=True).stdout.strip()
        (self.repo / "app.py").write_text("v1 changed\n")
        (self.repo / ".env").write_text("TOKEN=new-secret\n")
        (self.repo / "new_module.py").write_text("untracked body\n")
        self.dispositions = Path(self._tmp.name) / "dispositions.md"
        self.dispositions.write_text("F1: accepted, fixed in app.py\n", encoding="utf-8")

    def commit(self, message):
        git("-C", str(self.repo), "add", "-A")
        git("-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t",
            "commit", "-q", "-m", message)

    def run_target(self, reviewer, **kwargs):
        kwargs.setdefault("target", ["working-tree", self.base])
        return cr.run_review(reviewer, self.repo, kwargs.pop("brief", self.brief), None,
                             None, self.env, **kwargs)



class BasketRunTests(GitRunnerTestCase):
    """Runner-built brief: embedded material, standard sections, follow-up refresh."""

    def test_claude_and_antigravity_briefs_embed_diff_and_untracked_files(self):
        for reviewer in ("claude-code", "antigravity"):
            with self.subTest(reviewer=reviewer):
                self.run_target(reviewer)
                stdin = last_record(self)["stdin"]
                self.assertTrue(stdin.startswith("fixture brief"))
                self.assertIn("+v1 changed", stdin)
                self.assertIn("untracked body", stdin)
                self.assertIn("new_module.py", stdin)
                # Standard exclusions never enter the embedded material.
                self.assertNotIn("new-secret", stdin)

    def test_codex_brief_does_not_embed_the_diff(self):
        self.run_target("codex")
        stdin = last_record(self)["stdin"]
        self.assertIn("new_module.py", stdin)
        self.assertNotIn("+v1 changed", stdin)
        self.assertNotIn("untracked body", stdin)

    def test_exclude_drops_a_path_from_the_material(self):
        self.run_target("claude-code", exclude=["new_module.py"])
        stdin = last_record(self)["stdin"]
        self.assertNotIn("untracked body", stdin)
        self.assertIn("- new_module.py", stdin.split("Excluded paths", 1)[1])

    def test_material_over_the_limit_fails_without_a_run(self):
        with mock.patch.object(cr, "MAX_EMBED_BYTES", 10):
            with self.assertRaises(cr.CrossReviewError) as caught:
                self.run_target("antigravity")
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.run_dirs(), [])

    def test_followup_refreshes_the_embedded_diff_without_a_new_brief(self):
        first = self.run_target("claude-code")
        (self.repo / "app.py").write_text("v2 fixed\n")
        second = cr.run_review(None, self.repo, None, None, None, self.env,
                               followup=first, dispositions=self.dispositions)
        stdin = last_record(self)["stdin"]
        self.assertTrue(stdin.startswith("fixture brief"))
        self.assertEqual(stdin.count("fixture brief"), 1)
        self.assertIn("+v2 fixed", stdin)
        self.assertNotIn("+v1 changed", stdin)
        self.assertIn("This is review round 2", stdin)
        header = json.loads((second / "run.log").read_text().splitlines()[0])
        self.assertEqual(header["target"]["kind"], "working-tree")
        self.assertEqual(header["target"]["ref"], self.base)

    def test_mode_appends_the_cr_request_sections(self):
        run_dir = self.run_target("antigravity", mode="implementation")
        stdin = last_record(self)["stdin"]
        for marker in ("## Reviewer instructions", "## Result contract", "## Severity",
                       "## Intent", "## System", "## Craft",
                       "file read and search tools"):
            self.assertIn(marker, stdin)
        header = json.loads((run_dir / "run.log").read_text().splitlines()[0])
        self.assertEqual(header["mode"], "implementation")
        self.run_target("codex", mode="plan")
        stdin = last_record(self)["stdin"]
        self.assertIn("### Document kind", stdin)
        self.assertNotIn("## Common smells", stdin)
        self.assertNotIn("file read and search tools", stdin)

    def test_mode_without_cr_request_is_dependency_unavailable(self):
        with mock.patch.object(cr, "CR_REQUEST_DIR", Path(self._tmp.name) / "missing"):
            with self.assertRaises(cr.CrossReviewError) as caught:
                self.run_target("codex", mode="plan")
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("cr-request", caught.exception.message)

    def test_documents_carry_status_and_outside_content_for_claude(self):
        spec = Path(self._tmp.name) / "spec.md"
        spec.write_text("# Spec\n\n**Status:** draft\n\nAC1: outside requirement\n")
        self.run_target("claude-code", documents={"spec": str(spec)})
        stdin = last_record(self)["stdin"]
        self.assertIn("Status: draft", stdin)
        self.assertIn("AC1: outside requirement", stdin)
        self.run_target("codex", documents={"spec": str(spec)})
        stdin = last_record(self)["stdin"]
        self.assertIn("Status: draft", stdin)
        self.assertNotIn("AC1: outside requirement", stdin)

    def test_agent_family_and_model_shorthand_reach_the_cli(self):
        out = io.StringIO()
        # main reads os.environ: the fake CLIs must be on its PATH, never the real ones.
        with redirect_stdout(out), redirect_stderr(io.StringIO()), \
                mock.patch.dict(os.environ, self.env):
            code = cr.main(["run", "--agent", "gemini", "--model", "argon",
                            "--effort", "low", "--repo", str(self.repo),
                            "--brief", str(self.brief)])
        self.assertEqual(code, 0)
        argv = last_record(self)["argv"]
        self.assertIn("gemini-4-argon", argv)


class AgyIdleTests(RunnerTestCase):
    def setUp(self):
        super().setUp()
        install_fake_bin(self)
        for name, value in (("AGY_IDLE_SECONDS", 0.5), ("AGY_POLL_SECONDS", 0.1)):
            patch = mock.patch.object(cr, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def test_answered_and_hanging_agy_returns_its_own_exit_code(self):
        self.env["FAKE_AGY_MODE"] = "hang"
        started = time.monotonic()
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.run_review("antigravity", self.repo, self.brief, None, None, self.env)
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(caught.exception.code, cr.EXIT_IDLE_AFTER_ANSWER)
        self.assertEqual(cr.EXIT_IDLE_AFTER_ANSWER, 25)
        run_dir = caught.exception.run_dir
        self.assertIn("Follow-up handled", (run_dir / "review.md").read_text())
        self.assertIn("idle-after-answer", (run_dir / "run.log").read_text())
        usage = json.loads((run_dir / "usage.json").read_text())
        self.assertEqual(usage["exit_reason"], "idle-after-answer")

    def test_agy_that_exits_is_unaffected(self):
        run_dir = cr.run_review("antigravity", self.repo, self.brief, None, None, self.env)
        self.assertNotIn("exit_reason", json.loads((run_dir / "usage.json").read_text()))


class AgyIsolationTests(RunnerTestCase):
    """Fail-closed preflight on the agy settings of the fixture HOME."""

    SECRET_ENTRY = "npm test --secret-entry"

    def setUp(self):
        super().setUp()
        install_fake_bin(self)
        self.settings = self.home / ".gemini" / "antigravity-cli" / "settings.json"

    def write_settings(self, text):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(text)

    def assert_stopped_before_the_brief(self, exc):
        self.assertEqual(exc.code, cr.EXIT_INVALID_INPUT)
        self.assertIn(str(self.settings), exc.message)
        self.assertNotIn(self.SECRET_ENTRY, exc.message)
        self.assertIsNone(exc.run_dir)
        self.assertEqual(self.run_dirs(), [])
        self.assertEqual(list(self.record.iterdir()), [])

    def run_agy_error(self):
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.run_review("antigravity", self.repo, self.brief, None, None, self.env)
        return caught.exception

    def test_non_empty_allow_list_exits_2_before_the_brief_is_sent(self):
        self.write_settings(json.dumps({"permissions": {"allow": [self.SECRET_ENTRY]}}))
        self.assert_stopped_before_the_brief(self.run_agy_error())

    def test_main_returns_2_and_names_the_file_without_its_content(self):
        self.write_settings(json.dumps({"permissions": {"allow": [self.SECRET_ENTRY]}}))
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err), \
                mock.patch.dict(os.environ, self.env):
            code = cr.main(["run", "--agent", "gemini", "--repo", str(self.repo),
                            "--brief", str(self.brief)])
        self.assertEqual(code, 2)
        self.assertIn(str(self.settings), err.getvalue())
        self.assertNotIn(self.SECRET_ENTRY, err.getvalue())
        self.assertEqual(list(self.record.iterdir()), [])

    def test_unparsable_settings_exit_2(self):
        for text in ("{not json " + self.SECRET_ENTRY, "[]",
                     json.dumps({"permissions": [self.SECRET_ENTRY]}),
                     json.dumps({"permissions": {"allow": self.SECRET_ENTRY}})):
            with self.subTest(text=text):
                self.write_settings(text)
                self.assert_stopped_before_the_brief(self.run_agy_error())

    @unittest.skipIf(os.geteuid() == 0, "root reads a mode 000 file")
    def test_unreadable_settings_exit_2(self):
        self.write_settings(json.dumps({"permissions": {"allow": []}}))
        self.settings.chmod(0)
        self.assert_stopped_before_the_brief(self.run_agy_error())

    def test_missing_settings_file_lets_the_run_proceed(self):
        run_dir = cr.run_review("antigravity", self.repo, self.brief, None, None, self.env)
        self.assertEqual(last_record(self)["stdin"], "fixture brief")
        self.assertTrue((run_dir / "review.md").exists())

    def test_empty_allow_list_lets_the_run_proceed(self):
        for text in (json.dumps({"permissions": {"allow": []}}), json.dumps({"theme": "x"})):
            with self.subTest(text=text):
                self.write_settings(text)
                cr.run_review("antigravity", self.repo, self.brief, None, None, self.env)

    def test_other_reviewers_do_not_read_the_agy_settings(self):
        self.write_settings(json.dumps({"permissions": {"allow": [self.SECRET_ENTRY]}}))
        cr.run_review("claude-code", self.repo, self.brief, None, None, self.env)

    def test_resume_checks_the_settings_again(self):
        original = cr.run_review("antigravity", self.repo, self.brief, None, None, self.env)
        self.write_settings(json.dumps({"permissions": {"allow": [self.SECRET_ENTRY]}}))
        before = len(list(self.record.iterdir()))
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.resume_review(original, "Re-check.", self.env)
        self.assertEqual(caught.exception.code, cr.EXIT_INVALID_INPUT)
        self.assertEqual(len(list(self.record.iterdir())), before)
        self.assertEqual(self.run_dirs(), [original])


class ReviewRoundOneTests(GitRunnerTestCase):
    """Fixes for the yngwald review round 1 findings on PR #13."""

    def test_non_utf8_tracked_diff_is_embedded_without_crash(self):
        (self.repo / "latin.txt").write_bytes(b"caf\xe9\n")
        self.commit("latin")
        self.base = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD~1"],
                                   check=True, stdout=subprocess.PIPE,
                                   text=True).stdout.strip()
        (self.repo / "latin.txt").write_bytes(b"caf\xe9 au lait\n")
        self.run_target("claude-code")
        self.assertIn("au lait", last_record(self)["stdin"])

    def test_untracked_symlink_inside_the_repo_is_never_read(self):
        os.symlink(".env", self.repo / "env-link")
        info = cr.compute_target(self.repo, "working-tree", None)
        self.assertIn("env-link", info["excluded"])
        self.run_target("antigravity")
        self.assertNotIn("new-secret", last_record(self)["stdin"])

    def test_key_and_credential_names_are_standard_exclusions(self):
        for name in ("id_rsa", "deploy/id_ed25519.pub", "server.pem", "tls.key", ".npmrc",
                     "credentials.json", "app/.netrc"):
            with self.subTest(name=name):
                self.assertTrue(cr.is_standard_exclusion(name))
        for name in (".envrc", ".git-credentials", "prod.tfvars", "kubeconfig", ".ENV",
                     ".Env.prod", ".local/share/token.txt"):
            with self.subTest(name=name):
                self.assertTrue(cr.is_standard_exclusion(name))
        self.assertFalse(cr.is_standard_exclusion("keyboard.py"))
        (self.repo / "server.pem").write_text("PRIVATE KEY BODY\n")
        self.run_target("claude-code")
        self.assertNotIn("PRIVATE KEY BODY", last_record(self)["stdin"])

    def test_exclude_is_normalized_and_an_unmatched_one_fails(self):
        for item in ("./new_module.py", str(self.repo / "new_module.py")):
            with self.subTest(item=item):
                self.run_target("claude-code", exclude=[item])
                self.assertNotIn("untracked body", last_record(self)["stdin"])
        runs = len(self.run_dirs())
        for item in ("new_modul.py", "/elsewhere/x.py"):
            with self.subTest(item=item):
                with self.assertRaises(cr.CrossReviewError) as caught:
                    self.run_target("claude-code", exclude=[item])
                self.assertEqual(caught.exception.code, 2)
        self.assertEqual(len(self.run_dirs()), runs)

    def test_followup_exclusions_add_to_the_previous_ones(self):
        (self.repo / "notes.md").write_text("private notes\n")
        first = self.run_target("claude-code", exclude=["new_module.py"])
        cr.run_review(None, self.repo, None, None, None, self.env, followup=first,
                      dispositions=self.dispositions, exclude=["notes.md"])
        stdin = last_record(self)["stdin"]
        self.assertNotIn("untracked body", stdin)
        self.assertNotIn("private notes", stdin)

    def test_followup_states_the_new_round_ids(self):
        first = self.run_target("claude-code")
        cr.run_review(None, self.repo, None, None, None, self.env, followup=first,
                      dispositions=self.dispositions)
        stdin = last_record(self)["stdin"]
        self.assertIn("Use finding IDs R2-<reviewer>-F<k>", stdin)
        self.assertIn("belongs to that round", stdin)
        cr.run_review(None, self.repo, self.brief, None, None, self.env, followup=first,
                      dispositions=self.dispositions)
        self.assertNotIn("belongs to that round", last_record(self)["stdin"])

    def test_followup_does_not_reuse_a_commit_pinned_range(self):
        self.commit("work")
        head = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], check=True,
                              stdout=subprocess.PIPE, text=True).stdout.strip()
        first = self.run_target("codex", target=["range", "%s..%s" % (self.base, head)])
        with self.assertRaises(cr.CrossReviewError) as caught:
            cr.run_review(None, self.repo, None, None, None, self.env, followup=first,
                          dispositions=self.dispositions)
        self.assertEqual(caught.exception.code, 2)
        symbolic = self.run_target("codex", target=["range", "%s..HEAD" % self.base])
        cr.run_review(None, self.repo, None, None, None, self.env, followup=symbolic,
                      dispositions=self.dispositions)

    def test_rename_embeds_as_delete_and_add(self):
        # Long unchanged content: git would detect this rename without --no-renames.
        (self.repo / "app.py").write_text("".join("line %d\n" % i for i in range(50)))
        self.commit("work")
        self.base = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"],
                                   check=True, stdout=subprocess.PIPE,
                                   text=True).stdout.strip()
        git("-C", str(self.repo), "mv", "app.py", "renamed.py")
        info = cr.compute_target(self.repo, "working-tree", self.base)
        self.assertIn("app.py", info["files"])
        self.run_target("claude-code")
        stdin = last_record(self)["stdin"]
        self.assertIn("deleted file mode", stdin)
        self.assertIn("+++ b/renamed.py", stdin)

    def test_non_utf8_file_name_does_not_crash(self):
        name = os.fsdecode(b"caf\xe9.txt")
        text = cr.format_target(self.repo, {"kind": "working-tree", "head": "0" * 40,
                                            "files": [name], "excluded": []})
        self.assertIn(b"caf", cr._utf8(text))
        if sys.platform == "darwin":
            self.skipTest("APFS rejects file names that are not UTF-8")
        name = os.fsdecode(b"caf\xe9.txt")
        (self.repo / name).write_text("latin name\n")
        self.run_target("claude-code")
        self.assertIn("latin name", last_record(self)["stdin"])

    def test_untracked_file_over_the_limit_is_not_read(self):
        (self.repo / "dump.sql").write_text("x" * 5000)
        with mock.patch.object(cr, "MAX_EMBED_BYTES", 2000):
            with self.assertRaises(cr.CrossReviewError) as caught:
                self.run_target("claude-code")
        self.assertEqual(caught.exception.code, 2)
        # The size check before the read, not the one after it.
        self.assertIn("untracked dump.sql alone exceeds", caught.exception.message)

    def test_status_needs_a_colon_and_whitespace(self):
        spec = Path(self._tmp.name) / "status.md"
        spec.write_text("Statuses are listed below.\n\nStatus: approved\n")
        self.assertEqual(cr.compute_documents({"spec": str(spec)})["spec"]["status"],
                         "approved")
        spec.write_text("**Status:** draft\n")
        self.assertEqual(cr.compute_documents({"spec": str(spec)})["spec"]["status"], "draft")

    def test_standard_sections_drop_subsections_that_do_not_apply(self):
        text = cr.standard_sections("implementation", "codex")
        self.assertNotIn("### Re-review kind", text)
        self.assertNotIn("### Document kind", text)
        text = cr.standard_sections("plan", "codex")
        self.assertIn("### Document kind", text)
        self.assertNotIn("### Re-review kind", text)

    def test_standard_sections_leave_out_the_host_only_text(self):
        # The cut at `Not checkable keeps the CI signature, the footer grammar, and the
        # publication-object sentence of cr-request brief.md out of the reviewer's brief.
        for mode in cr.MODES:
            for reviewer in cr.REVIEWERS:
                with self.subTest(mode=mode, reviewer=reviewer):
                    text = cr.standard_sections(mode, reviewer)
                    self.assertIn("## Result contract", text)
                    for phrase in ("Reviewed with", "CI footer grammar",
                                   "conversation comment"):
                        self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
