# Compact Result

The compact presentation of a review result, the one the CI auto-review
(`claude-review.yml`) posts. A reader sees the verdicts and the readiness at a glance and
opens every other detail, the findings and the target included, on demand from one
collapsed `<details>` block. The CI-only parts stay in the workflow prompt: the marker
line `<!-- claude-review sha=<head sha> -->` that opens the body, the GitHub link
patterns (blob, compare, commit), and the inline comments file.

## Layout

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

## Inside `<details>`

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

## Footer

The body ends with the two CI closing lines of SKILL.md: the signature
``Reviewed with: `/cr-request` <version> skill``, then the `Next step` line as the very
last line, in the forms and the grammar of [brief.md](brief.md) "CI footer grammar".
