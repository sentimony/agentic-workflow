# Compact Result

The shared presentation for local `cr-request`, `cross-cr`, and CI auto-review
(`claude-review.yml`). Show verdicts, severity counts, readiness, and the next step;
keep the complete evidence available on demand. Local calls link a persistent full
review archive. CI embeds the full result in one collapsed `<details>` block.

## Local transport

After the trusted host archives the completed review using
[review-actions.md](review-actions.md), show the one-row table and `Readiness` line
below, then `Full review: <link to archived review.md>` and the local
`Next step: <skill> - <reason>` line. Keep full findings, target identity, evidence,
set-aside items, and gaps in the archived report. A missing or failed archive makes
the handoff `INCOMPLETE`, with the failed operation and recovery path visible.

For `cross-cr`, show one row per reviewer, with reviewer/model, effort, cost or
`unknown`, its own Intent/System/Craft verdicts and Critical/Important/Minor counts,
and a link to its full result. Preserve original IDs and provenance; differing verdicts
never collapse to an unconditional PASS. Follow those rows with readiness and the
local next step. Each reviewer retains its complete report and identity in the stable
session repository archive; a temporary runner path alone is incomplete.

## CI transport

The CI-only parts stay in the workflow prompt: the marker
`<!-- claude-review sha=<head sha> -->` that opens the body, GitHub link patterns
(blob, compare, commit), the inline comments file, and the action draft path. Publish
adds the durable machine ledger before the footer, using
[review-actions.md](review-actions.md); that service comment is not a visible section
or an additional Details block. Preserve the footer grammar unchanged.

### Layout

These parts, in this order, with no headings outside the `<details>` block:

```text
| Intent | System | Craft | Critical | Important | Minor |
| --- | --- | --- | --- | --- | --- |
| <verdict> | <verdict> | <verdict> | <n> | <n> | <n> |

**Readiness:** <ready | ready with fixes | not ready>

<details><summary>Details</summary>

#### Findings

#### Target

#### Axis verdicts

#### Set aside, open questions, and review gaps

</details>
```

then the footer.

- Each verdict is `PASS`, `FINDINGS`, or `UNASSESSED`. Use only the severities Critical,
  Important, and Minor; the counts match the findings, and zero findings means zeros.
- The `**Readiness:**` line holds ready, ready with fixes, or not ready, and nothing else.
- The `<details>` block is the only one in the body; do not nest another inside it. Put a
  blank line after its `<summary>...</summary>` line, before `</details>`, and after
  `</details>`, so the Markdown inside and after it renders.

### Inside `<details>`

`#### Findings`: one line per finding, most severe first,
`` - **<severity>** <id> `<path>:<line>` <title> `` (CI links the location to the file at
the head commit), then each finding with severity, confidence, file:line, impact, and
evidence, and an optional suggestion. Omit this part when there are no findings.

`#### Target`: `**Target:**` with the pull request or other target and its head and base
branches; the target identity (base, head, tree, uncommitted state, excluded paths);
`**Range:**` the reviewed range with short SHAs and the number of files and lines;
`**Commits:**` one line per commit (short SHA and subject), and after 20 commits
`and <n> more`; `**Coverage:**` how the review ran, the files read, what was skipped, and
the intent sources.

`#### Axis verdicts`: the reason for the readiness in one line, then one bullet per axis
with its verdict and reasons; on a fresh review pass, the status of each finding of the
previous review after them.

`#### Set aside, open questions, and review gaps`: the set-aside list, open questions, and
review gaps.

### Footer

The body ends with the two CI closing lines of SKILL.md: the signature
``Reviewed with: `/cr-request` <version> skill``, then the `Next step` line as the very
last line, in the forms and the grammar of [brief.md](brief.md) "CI footer grammar".
