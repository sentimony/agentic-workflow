# Spec template

Path: the spec folder the project already uses (named in its instructions or visible
from existing files); otherwise `docs/specs/YYYYMMDD-HHMM-<topic>.md`. The plan later
reuses the same topic.

Header field keys and values stay literal English tokens even when the rest of the spec
is in another language. Section headings follow the language of the project's existing
specs; the order below does not change.

## Header

```markdown
# <Topic>

Status: draft
Route: design
Date: YYYY-MM-DD
```

- `Status`: `draft` | `approved`. It becomes `approved` only after the user's explicit
  yes in the conversation.
- `Route`: `note` | `design`. The `direct` route writes no file.

## Route `design`, sections in this order

```markdown
## Goal

What the change is for and who uses it, from the caller's side, in a few sentences.

## Evidence

| Assumption | State | Source |
| --- | --- | --- |
| <claim the design rests on> | verified | <command, file, or user statement> |
| <claim> | assumed | <why it was not checked> |
| <claim> | contradicted | <what disproved it> |
| <claim> | partial: <exception> | <source> |

## Decisions

1. <Decision>. Take <X> over <Y>: <what is gained and what it costs>.
   Rejected: <alternative> - <reason>.

## Behavior

What a user or caller observes: inputs, outputs, states, errors, edge cases.

## Contract

Interfaces, formats, and fields other parts depend on. No implementation file paths:
those belong to the plan.

## Out of scope

- <item left out on purpose>

## Open questions

- <question> - recommended answer: <answer>
(or "None.")

## Acceptance criteria

- AC1: <observable, checkable predicate>
- AC2: <...>

## Security Model

Trusted inputs, untrusted inputs, which content is data rather than instructions, and
which shell commands or network calls the change makes.
```

## Route `note`, sections in this order

```markdown
## Goal
## Decisions
## Acceptance criteria
```

## Acceptance criteria rules

- One line per criterion: `AC<n>: <checkable predicate>`.
- Numbering starts at 1 and has no gaps; renumber after removing one.
- The predicate names something that can be observed (a command result, a visible
  state, a value in a file), never an activity such as "tests were written".
- Each criterion can be checked on its own, without reading the others.

## Large requests

When the request holds several independent parts, the Goal lists them with a build
order, and each part gets its own spec or its own block of criteria.
