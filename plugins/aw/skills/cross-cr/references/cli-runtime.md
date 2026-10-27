# CLI Runtime

How the host launches the runner, what the runner executes, and how to read its exit
codes. Everything here was observed with `codex-cli 0.160.0` and Claude Code `2.1.288`,
the environment allowlist with `codex-cli 0.160.1` and Claude Code `2.1.296`, and the
Antigravity reviewer with `agy 1.3.3`; items marked UNASSESSED were not observed.

Contents:

- [Runner interface](#runner-interface): argument groups, reviewer table, models,
  environment allowlist, `--target`, the runner-built brief, follow-up rounds;
- [Artifacts](#artifacts): run directory files and usage parsing per reviewer;
- [Production commands](#production-commands): the exact argv per reviewer and its flags;
- [Launch from the host](#launch-from-the-host): background launch per host and reviewer;
- [Exit codes](#exit-codes).

## Runner interface

Call the runner by the absolute path of `scripts/cross_review.py` inside the installed
`cross-cr` skill directory, never from a source clone:

    python3 <skill-dir>/scripts/cross_review.py resolve --host claude-code|codex \
      [<family> [<model>] [<effort>]]...

    python3 <skill-dir>/scripts/cross_review.py run --agent claude|codex|gemini \
      --repo <repo-root> --brief <brief-file> [--mode plan|implementation] [--model <id>] \
      [--effort low|medium|high|xhigh|max] \
      [--target range <BASE>..<HEAD> | --target tree <REV> | --target working-tree [<BASE>]] \
      [--exclude <path>]... [--plan <path>] [--spec <path>] \
      [--followup <previous-run-dir> --dispositions <file>] [--pass-env <NAME>]...

    python3 <skill-dir>/scripts/cross_review.py resume --run-dir <previous-run-dir> \
      --prompt "<follow-up>" [--pass-env <NAME>]...

The runner reads the brief as UTF-8, starts the reviewer with `cwd` set to the repository,
passes the brief on stdin, and sets no timeout on a reviewer that is still working
(the one exception is `agy` after a complete answer, exit 25). It refuses to start when
`CROSS_REVIEW_DEPTH` is present in its environment, even empty, and sets
`CROSS_REVIEW_DEPTH=1` for the reviewer process.

Reviewer agents live in the `REVIEWERS` table of `cross_review.py`: CLI name, default
model and effort, the environment prefixes the CLI needs, and whether its cost is known
(`priced`). Adding an agent means one table entry plus its command builder, read-only
policy, usage parser, and prices when it has any; the `--agent` choices follow the table.
`--agent` also takes the family names `claude` (= `claude-code`) and `gemini`
(= `antigravity`).

`resolve` turns the skill's argument groups into reviewers. A token that is a family
(`claude`, `codex`, `gemini`) opens a group, a token from the effort set is the group's
effort, and any other token is its model; a model or effort before the first family, two
models or efforts in one group, or a model after the effort is exit 2. No group means one
reviewer, the CLI opposite to `--host`. Each line of output is JSON:
`{"agent", "model", "effort", "same_cli"}`, with the model shorthand expanded and missing
values filled with the defaults below.

| Family | Shorthand -> model id |
| --- | --- |
| `claude` | `opus` -> `claude-opus-5-5`, `sonnet` -> `claude-sonnet-5-5`, `haiku` -> `claude-haiku-5-5`, `fable` -> `claude-fable-5-1` |
| `codex` | `sol` -> `gpt-6.1-sol`, `terra` -> `gpt-6.1-terra`, `astra` -> `gpt-6-astra`, `luna` -> `gpt-6-luna` |
| `gemini` | `argon` -> `gemini-4-argon`, `flash` -> `gemini-3.8-flash` |

`run --model` expands the same shorthands; any other value passes as a full model id. The
table is `MODEL_ALIASES` in the runner: update it when a newer model of a family ships.

| Agent | CLI | Default model | Default effort |
| --- | --- | --- | --- |
| `codex` | `codex` | `gpt-6.1-sol` | `low` |
| `claude-code` | `claude` | `claude-opus-5-5` | `medium` |
| `antigravity` | `agy` | `gemini-4-argon` | `medium` |

Model and effort are always passed explicitly, so the reviewer's global configuration does
not override them. `--model` and `--effort` replace the defaults. Effort must be one of
`low`, `medium`, `high`, `xhigh`, `max`: every CLI accepts exactly these, though a model
may support fewer (Codex `models_cache.json` lists the levels per model). The model is not
validated against a list, because model names change faster than the runner; a value that
starts with `-` is rejected so it can never be read as a CLI flag, and an unknown model
fails inside the reviewer CLI with code 22. Model examples: Codex `gpt-6.1-sol`,
`gpt-6-astra`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-luna`; Claude `claude-opus-5-5`,
`claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-1`; Antigravity
`gemini-4-argon`, `gemini-3.8-flash` (`agy models` lists each with
the effort suffixes it supports). Pass the id without the
suffix: a suffixed id such as `gemini-3.8-flash-medium` that disagrees with `--effort`
fails with exit 1. `agy models` also lists Claude and GPT-OSS ids; pass a Gemini id to
keep the review cross-vendor. Resume reuses the values of the previous run. A `--followup` round
reuses the previous run's agent, and its model and effort when the agent is unchanged,
unless new values are given.

### Reviewer environment

The reviewer process receives an allowlist, not the host environment: `PATH`, `HOME`,
`USER`, `LOGNAME`, `SHELL`, `TMPDIR`, `TERM`, `LANG`, `TZ`, `LC_*`, the `XDG_*` base
directories, proxy and CA variables (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` in both
cases, `SSL_CERT_FILE`, `SSL_CERT_DIR`, `NODE_EXTRA_CA_CERTS`), `__CF_USER_TEXT_ENCODING`,
`CROSS_REVIEW_DEPTH`, and the agent's own prefixes: `CODEX_*` and `OPENAI_*` for Codex;
`ANTHROPIC_*`, `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_USE_*`, and `CLAUDE_CODE_OAUTH_TOKEN` for
Claude; `AGY_*` and `GEMINI_API_KEY` for Antigravity, whose own `ANTIGRAVITY_*` session
markers stay out. `--pass-env NAME` (repeatable) adds one more variable by name, for example
`AWS_PROFILE` and `AWS_REGION` for Claude on Bedrock or `GOOGLE_APPLICATION_CREDENTIALS`
for Vertex and for `agy` with application default credentials. The `run.log` header
records the names passed, never their values. Host markers such as `CLAUDECODE` do not
reach the reviewer.

### Target

`--target` makes the runner compute the boundary and append a `Review target` section to
the brief: the file list, the excluded paths with an instruction not to read them, and the
fingerprint.

| Target | Files | Fingerprint |
| --- | --- | --- |
| `range BASE..HEAD` | `git diff --name-only BASE HEAD` | both commit SHAs and a SHA-256 of `git diff --binary BASE HEAD` |
| `tree REV` | every tracked file at `REV` | the tree SHA only |
| `working-tree` | tracked changes against `HEAD` plus untracked files that gitignore keeps | `HEAD`, a SHA-256 of `git diff --binary HEAD`, and a SHA-256 per untracked file |
| `working-tree BASE` | `git diff BASE` (committed, staged, and unstaged) plus untracked files that gitignore keeps | `BASE`, `HEAD`, a SHA-256 of `git diff --binary BASE`, and a SHA-256 per untracked file |

Standard exclusions, matched without regard to case: `.env`, `.env.*`, any path with
`.local` in a name or directory, untracked files that cannot be read, key and credential
names (`*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`, `*.ppk`, `*.tfvars`,
`id_rsa*`, `id_dsa*`, `id_ecdsa*`, `id_ed25519*`, `.npmrc`, `.netrc`, `.pypirc`,
`.pgpass`, `.envrc`, `.git-credentials`, `kubeconfig`, `credentials`,
`credentials.json`, `secrets.json`, `secrets.yaml`, `secrets.yml`), and every untracked
symlink, which the runner never follows. An untracked file larger than what is left of
the 4 MiB budget fails before it is read; untracked files are hashed in chunks. `--exclude <path>` (repeatable) adds a file, or a directory with
everything under it, relative to the repository root or absolute inside it; one that
matches no path of the target, or lies outside the repository, is exit 2. The `run.log`
header records the list. File lists and the embedded diff use `--no-renames`, so a
rename shows as a deletion and an addition. Gitignored files never
enter the list. A revision that does not resolve to a commit, or one that starts with `-`,
is invalid input. The target summary without the file list, plus a `fingerprint` hash of
the whole computed target, goes into the `run.log` header.

### Runner-built brief

For a `claude-code` or `antigravity` reviewer, a `range` or `working-tree` target also
appends an `Embedded material` section: `git diff --no-ext-diff --no-textconv` of the
tracked files in scope (never the excluded ones) and the full content of each untracked
file in scope, each in a fence longer than any backtick run inside it. An untracked file
that is not UTF-8 is listed as a gap instead; a tracked diff that is not UTF-8 is shown
with replacement characters. This diff and these files over 4 MiB (`MAX_EMBED_BYTES`) are
exit 2 before any run directory exists; nothing is truncated. A Codex reviewer runs Git
itself and gets the file list only.

`--mode plan|implementation` appends the `Reviewer instructions`, `Result contract`
(without its closing-line rules for the host), and `Severity` sections of the installed
cr-request `references/brief.md` (without `Re-review kind`, which the follow-up section
replaces, and with `Document kind` in `plan` mode only), plus the `Intent`, `System`, and
`Craft` sections of its
`references/lenses.md` in `implementation` mode, and for `antigravity` the line that limits
it to file read and search tools. cr-request is read from the skills directory that holds
`cross-cr`; when it is missing, the run is exit 2 with `dependency unavailable:
cr-request`. The `run.log` header records the mode, `unspecified` without the flag.

### Requirement documents

`--plan <path>` and `--spec <path>` make the runner hash each file and append a
`Requirement documents` section with `Plan: <path>, sha256 <hash>` and
`Spec: <path>, sha256 <hash>` to the brief, with a `<Kind> Status: <value>` line read
from the file's first `Status:` line at each run; the paths, hashes, and statuses go into
the `run.log` header as `documents`. For a `claude-code` or `antigravity` reviewer, the
full content of each document outside `--repo` follows in the brief. A `--followup` round without these flags rehashes the previous
round's paths, and a new flag replaces its path. An unreadable file is invalid input.

### Follow-up rounds

`--followup <previous-run-dir> --dispositions <file>` starts a fresh session, not a resume:
the new round reviews the current target from scratch. Without `--brief`, the runner takes
the host part of the previous `brief.md` (its length is `host_brief_bytes` in the header);
without `--target` or `--mode`, the previous values, and a new `--exclude` adds to the
previous list. A previous `range` or `tree` target whose head is a full commit id is exit 2
without `--target`, because the fixes since then lie outside it. It then rebuilds every
section it adds from the current files, so the embedded diff, the untracked files, the
hashes, and the `Status:` lines are those of the new round. The runner reads the previous
run's header and `review.md` (both must be private files of a private run directory),
appends the previous review and the host's dispositions to the brief, and asks for a
status of every previous finding: `ADDRESSED` or `NOT ADDRESSED`. It also states the new
round's finding IDs and, when it reused the host part, that a round, ID prefix, or `Tree`
in it belongs to the previous round. The round
number is the previous one plus one. When the target and documents match the previous
round's header, the runner prints `cross-review: target and documents unchanged since
round N` on stderr and still runs. Both flags go together, and an unreadable previous
run or an empty dispositions file is invalid input.

## Artifacts

Each `run` or `resume` creates a new private directory
`<system temp>/cross-review/<YYYYMMDD-HHMMSS>[-N]/` (mode 0700, files 0600). The
`cross-review` parent must be a real directory, not a symlink, owned by the current user,
with mode exactly 0700; the runner creates it that way when it is missing and refuses an
existing one that fails any of these checks, without repairing it.

| File | Content |
| --- | --- |
| `brief.md` | the brief as sent; for resume, the wrapped follow-up prompt |
| `review.md` | the reviewer's final answer |
| `session.txt` | reviewer session UUID, empty when Codex or `agy` printed none |
| `run.log` | first line JSON metadata, then CLI diagnostics |
| `usage.json` | model, effort, reviewer skills, token counts, approximate cost, session total on resume, round and target total |

The `run.log` header holds `schema_version`, `reviewer` (the agent name), `mode`
(`plan`, `implementation`, or `unspecified`), absolute `repo`, `model`, `effort`, `round`,
`pass_env` (names only), `cli_version`, `host_brief_bytes`, and, when present, `target`,
`documents`, `exclude`, `followup_of`, and `resumed_from`. It never
holds environment values or credentials. Resume trusts only a header and session that pass
validation; a header written before 1.55.0 with `reviewer: claude` reads as
`claude-code`.

Codex runs with `--json`: stdout (JSONL events) and stderr go to `run.log`; the final answer
comes from `-o`; the session UUID is the `thread_id` of the first `thread.started` event, so
an id quoted in the brief or the answer is ignored. Token counts are the sum of
`turn.completed.usage`; skills are the directory names of `SKILL.md` files read by a
`command_execution` item. Claude runs with `--output-format json`: stdout goes to the private
`claude-output.json`, whose `result` becomes `review.md` and whose `modelUsage` and
`total_cost_usd` feed `usage.json`; the raw file is removed after a successful parse and kept
otherwise (exit 0 without a JSON result ends with code 23). stderr goes to `run.log`; the
runner generates the session UUID.

Antigravity runs with `--output-format json`: stdout goes to the private
`agy-output.json`, one object with `conversation_id`, `status`, `response`, and `usage`
(`input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`). `response`
becomes `review.md` and the raw file is removed; without a non-empty `response` and
`status: SUCCESS` the raw file stays and `review.md` holds it for diagnosis. The session
UUID is `conversation_id`. The runner logs `status` other than `SUCCESS`, `error`, and
each entry of `denied_actions` to `run.log`. A denied tool call ends the turn with exit 0,
`status: SUCCESS`, an empty `response`, and a `jetski: no output produced` line on stderr;
the runner ends that run with code 23. `status: ERROR` (unknown model, invalid effort)
comes with exit 1 and ends with code 22. In `usage.json`, `input` is `input_tokens`,
`cached_input` is `cache_read_tokens`, `output` is `output_tokens`, which already includes
`thinking_tokens` (`total_tokens` is input plus output), and `reasoning` is
`thinking_tokens`. `agy` reports no cost and no price table exists, so `cost_usd` is always
`null`, the session total is complete with tokens alone, and skills are `not detected`.
`target_total` stays incomplete, because its only figure is the cost.

In `usage.json`, `input` counts all input tokens including cache reads and writes, and
`output` includes reasoning. The Codex cost is
`((input - cached_input) * input_price + cached_input * cached_price + output * output_price) / 1e6`
from `PRICES` in `cross_review.py`; a model missing there gets `cost_usd: null` and the
run report says `cost unknown`. The Claude cost is the CLI's `total_cost_usd` at list
price; when the CLI reports tokens without a cost, the runner falls back to
`CLAUDE_PRICES` (input, 5-minute cache write, cache hit, output), with `cost_basis:
price-table`. To update prices, edit `PRICES`, `CLAUDE_PRICES`, and `PRICES_AS_OF` from
https://developers.openai.com/api/docs/pricing and
https://platform.claude.com/docs/en/about-claude/pricing, and the literals in
`test_prices_are_the_published_table`; add only models those pages list. On `claude -p --resume` the CLI reports `modelUsage` and
`total_cost_usd` cumulatively for the whole session, so the runner takes `session_total` from
them and derives this run by subtracting the previous `session_total`, which must be
complete; when that previous total is unreadable or incomplete, the session id differs, or a
difference is negative, this run's `tokens` and `cost_usd` are `null` and `run.log` says why.
`agy --conversation` also reports `usage` cumulatively for the whole conversation, and the
runner subtracts it the same way, tokens only.
`round` is the round number of the target, and `target_total` adds the cost of every run of
the target, followup rounds and resumes alike, with `rounds` and `complete`. The runner
prints the `usage.json` path only when the file is readable and always ends with the
summary lines, `usage: unknown` when it is not. The summary is plain ASCII (`|` and `~$`),
so a stdout without UTF-8 prints no question marks; a `Target:` line appears from round 2
on.

## Production commands

The runner builds these argv lists and runs them without a shell. Values in angle brackets
are filled from the run. Each argument is shown as one argv token: the double quotes in the
Codex `-c` values are part of the token, because they make the value a TOML string. Typed
into a shell, those quotes would be stripped, which is one reason to call the runner rather
than these commands.

Codex run:

    codex exec --json -s read-only -m gpt-6.1-sol -c model_reasoning_effort="low" \
      -c projects={"<path>"={trust_level="untrusted"}, ...} \
      -C <repo> -o <run-dir>/review.md -

Codex resume (with `cwd` set to the repository from the previous run's header):

    codex exec resume --json -m gpt-6.1-sol -c model_reasoning_effort="low" \
      -c sandbox_mode="read-only" \
      -c projects={"<path>"={trust_level="untrusted"}, ...} \
      -o <run-dir>/review.md <session-uuid> -

The `projects` table holds one entry per distinct path, each a JSON-escaped TOML string:

- the resolved repository and, where the file system reports it (macOS), its on-disk
  spelling;
- the worktree root from `git rev-parse --show-toplevel`;
- the parent of the Git common directory, which is the main worktree root of a normal
  repository and the containing directory of a bare or separate Git directory;
- the common directory itself when it is not named `.git`.

Git runs without `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_CEILING_DIRECTORIES`,
and `GIT_INDEX_FILE`. The runner also reads the nearest `.git` entry directly (a directory,
or a `gitdir:` file and its `commondir`) and adds the same paths from it, so a missing or
failing git still yields the set. When a `.git` entry exists but neither source yields a
path, or a path holds a control character or undecodable bytes, the runner exits with
code 2. The set is resolved after the CLI lookup and before the run directory exists.

Claude run:

    claude -p --output-format json --model claude-opus-5-5 --effort medium --permission-mode default \
      --tools "Read,Grep,Glob" --allowedTools "Read,Grep,Glob" \
      --disallowedTools "Write,Edit,NotebookEdit,Bash,Agent,Skill,mcp__*" \
      --strict-mcp-config --disable-slash-commands --safe-mode \
      --restricted --setting-sources "" --session-id <session-uuid>

Claude resume: the same command with `--resume <session-uuid>` in place of
`--session-id <session-uuid>`.

Antigravity run, with the brief on stdin and `cwd` set to the repository:

    agy --output-format json --model gemini-4-argon --effort medium \
      --disable-slash-commands --print-timeout 0

Antigravity resume: the same command followed by `--conversation <session-uuid>`. An
unknown id only prints `conversation not found` and starts a new conversation with exit 0,
so the runner compares the reported `conversation_id` with the resumed one and ends a
mismatch with code 24; that run's `session.txt` holds the new conversation, which lacks
the earlier context. `-p` is never passed: it takes the next token as the prompt.

What each safety flag does:

| Flag | Purpose |
| --- | --- |
| `--json` | JSONL events on stdout: session id and token usage |
| `--output-format json` | one JSON result with the answer, token usage, and cost |
| `-s read-only` | Codex sandbox forbids writes for the run |
| `-c sandbox_mode="read-only"` | `exec resume` has no `-s` and otherwise inherits the user's global sandbox, which can be `danger-full-access` |
| `-c projects={...trust_level="untrusted"}` | marks the reviewed repository untrusted even when the user's `~/.codex/config.toml` trusts it or the main repository of its worktree, so Codex loads no project `.codex/config.toml` from it: no MCP servers or `developer_instructions`; project hooks also need persisted hook trust, which the runner never bypasses |
| `-o <run-dir>/review.md` | keeps only the final answer, separate from progress output |
| `-` | brief or follow-up arrives on stdin |
| `--tools "Read,Grep,Glob"` | the only built-in tools loaded into the Claude session |
| `--allowedTools "Read,Grep,Glob"` | pre-approves those tools so the headless run never waits on a prompt |
| `--disallowedTools ...` | denies write, shell, delegation, skill, and MCP tools even if a setting enables them |
| `--permission-mode default` | overrides a permissive default mode from settings |
| `--strict-mcp-config` | loads no MCP servers from any configuration |
| `--disable-slash-commands` | disables skills and slash commands |
| `--safe-mode` | disables customizations such as project hooks while keeping authentication |
| `--restricted` | ignores user, project, and local settings files and keeps file tools inside the repository; the host embeds any needed file from outside it in the brief |
| `--setting-sources ""` | an empty source list: no settings file is loaded, the same intent stated explicitly |
| `--session-id` / `--resume` | fixes the session for resume; resume never uses `--last` |
| `--disable-slash-commands` (agy) | disables slash command and skill expansion of the brief in print mode |
| `--print-timeout 0` | pins the default: wait until the headless turn completes |
| `--conversation` | resumes the conversation by its id; never `--continue` |

Project configuration matters for both reviewers because the reviewed repository is
untrusted. For Codex, a trusted project's `.codex/config.toml` applied its
`developer_instructions` and started its `[mcp_servers]` commands outside the sandbox;
with the `projects` override neither happened, and `-c mcp_servers={}` alone did not help
because it merges. The runner never passes `--dangerously-bypass-hook-trust`. For Claude,
the reviewed repository's `.claude/settings.json` is the equivalent risk. Loaded as a
project source, it enabled the server-side `advisor` tool through `advisorModel` and
injected its `env` values into the reviewer's environment, overriding
`CROSS_REVIEW_DEPTH`. With this policy neither happened.

Observed effect of the Claude policy: the initial tool inventory is `Glob`, `Grep`, `Read`
with no MCP servers, skills, slash commands, or `advisor`, also in a repository whose
`.claude/settings.json` sets `advisorModel` and `env`, allows `Bash(*)`, `Write`, and
`Edit`, and defines `SessionStart` and `PreToolUse` hooks; those hooks did not run, and a
read of a file outside the repository was refused. Authentication through the CLI login
keeps working. Codex resume logged `sandbox: read-only`. In a trusted repository with a
project `.codex/config.toml`, the Codex run with the `projects` override loaded no project
config, started no MCP server, and completed normally.

Antigravity has no read-only flag, and the runner adds none. Observed effect of headless
`agy` without a permission flag: reads and searches inside the workspace run; a file
write, a read outside the workspace, and a command missing from the user's global
`permissions.allow` (in `~/.gemini/antigravity-cli/settings.json`) are denied and end the
turn. A command that list allows does run, so a test or build command there runs the
reviewed repository's code. `agy` loaded the reviewed repository's `AGENTS.md` and
`GEMINI.md` as rules even in an untrusted workspace, and no flag or environment variable
turns that or the user settings off. `--mode plan` is ignored together with
`--disable-slash-commands`, so the runner does not pass it. The runner never passes
`--dangerously-skip-permissions` or `--mode accept-edits`.

UNASSESSED: Antigravity project hooks and MCP servers in a workspace listed in
`trustedWorkspaces`, and whether `cache_read_tokens` counts inside `input_tokens`; the
probes saw no cache reads.

UNASSESSED: Claude authentication through an `apiKeyHelper`, which lives in a settings
file this policy does not load.

UNASSESSED: MCP servers and plugins configured in the Codex reviewer's own
`~/.codex/config.toml`; the Codex commands do not disable them. Only the project layer of
the reviewed repository is forced untrusted. Project hooks did not run in the probe because
Codex requires persisted hook trust; that was not tested with hooks the user had already
trusted.

## Launch from the host

A review can run for more than ten minutes. Wait for the runner's actual exit; a job that
is still running has produced no review.

### Claude Code host (reviewer: Codex)

Run the runner with the Bash tool and `run_in_background: true`, then read the output
after the completion notification. A 660-second background job completed with its exit
code and output.

Fallback when background execution is unavailable: start the runner detached with stdin
from `/dev/null`, output redirected to a file, and a wrapper that writes the exit code to a
marker file, all inside a private directory from `mktemp -d`. Treat only the exit marker
as completion; a live PID proves nothing.

### Antigravity reviewer

Launch it like the Codex reviewer from a Claude Code host: Bash with
`run_in_background: true`. `agy` reads its login from the user's home directory, so no
`--pass-env` is needed with a CLI login. UNASSESSED: a Codex host starting `agy`.

`agy` can write its complete answer and then never exit. The runner polls its
`agy-output.json` every `AGY_POLL_SECONDS` (1); once it parses as a `SUCCESS` answer with a
non-empty response and the process is still alive `AGY_IDLE_SECONDS` (60) later, the
runner stops it, writes `review.md` from the answer, logs `exit_reason:
idle-after-answer`, records `exit_reason` in `usage.json`, and exits 25.

### Codex host (reviewer: Claude)

Run the runner as one `exec_command` call with
`sandbox_permissions: "require_escalated"` and a justification such as "Allow
cross-review to run the Claude CLI, which needs its login credentials and the Claude API".
Do not try the command inside the sandbox first: under `workspace-write` the Claude CLI
reported `Not logged in` there, with or without network access. Allowing network access
alone does not help; the Claude CLI needs the escalated run to reach its login.

If the approval policy is `never` or the escalation is denied, cross-review is unavailable:
report the reason and apply the fallback.

Start with an early yield, keep the returned process session, and poll with `write_stdin`
until the call reports `exit_code`. This is costly in tokens: thirteen 60-second polls used
about 259k input tokens, mostly cached.

UNASSESSED: escalation behavior in the interactive Codex TUI and under approval policies
other than `never`; only `codex exec` was observed as a host.

## Exit codes

| Code | Meaning | Agent action |
| --- | --- | --- |
| 0 | `review.md` holds a non-empty answer | check completeness, then hand off to `cr-received` |
| 25 | `agy` wrote a complete answer and did not exit; the runner stopped it after `AGY_IDLE_SECONDS` and `review.md` holds the answer | check completeness as for 0 and name the stop in the run report |
| 2 | invalid input: unknown agent, a malformed argument group, effort outside the fixed set, empty or option-like model, missing repository, invalid `--target` or `--pass-env`, unreadable `--plan` or `--spec`, unusable `--followup` or `--dispositions`, embedded
material over 4 MiB, cr-request missing for `--mode`, a follow-up without `--brief` whose
previous run records no host brief, a Codex trust path that cannot be determined or holds a control character, missing or non-UTF-8 brief, empty prompt, unsafe run root, or a failure to create the run root | fix the invocation once; otherwise report unavailable |
| 20 | `CROSS_REVIEW_DEPTH` is set: this process is already a reviewer | perform the review yourself; never retry delegation |
| 21 | reviewer CLI not found or not executable | report unavailable and apply the fallback |
| 22 | reviewer exited non-zero or `agy` reported a status other than `SUCCESS`, or a runtime I/O failure after the run directory exists | report unavailable with the cause from `run.log`; partial output is no review |
| 23 | reviewer exited 0 with an empty or whitespace-only answer, including an `agy` turn ended by a denied tool call | report unavailable and apply the fallback |
| 24 | resume impossible: previous run directory missing or unsafe, header invalid or of an unknown schema, no valid session UUID, or `agy` started a new conversation instead of resuming | start a fresh `run` with a full brief if the follow-up is still needed |
| 130 | interrupted by SIGINT or SIGTERM; the runner stops the reviewer CLI | no review; partial artifacts stay for diagnosis |

Whenever a run directory exists, the runner prints it and its artifact paths, also on
failure. Exit code 0 shows that an answer exists; whether it covers the target is the
completeness check in `SKILL.md`.
