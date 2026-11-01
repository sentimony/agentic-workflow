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
| <claim the design rests on> | verified | <`path:line`, command and its output, or the user's words> |
| <claim> | assumed | <why it was not checked; listed under Open questions or as a risk> |
| <claim> | contradicted | <what disproved it> |
| <claim> | partial: <exception> | <source> |

## Decisions

1. <Decision>. Take <X> over <Y>: <what is gained and what it costs>.
   Rejected: <alternative> - <reason>. (optional)

## Behavior

What a user or caller observes: inputs, outputs, states, errors, edge cases.

## Contract

Interfaces, formats, and fields other parts depend on. No implementation file paths:
those belong to the plan.

## Out of scope

- <item left out on purpose>

## Open questions

- <question> - recommended answer: <answer>, because <reason>
- <question> - decision for the user: <what each option leads to>
- blocking: <question> - risk if left open: <what it changes> - recommended answer:
  <answer>, because <reason>
(or "None.")

Prefix a question with `blocking:` when its answer would change Behavior, Contract, or
an acceptance criterion, and name the risk the user may accept instead of answering.

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

## Decision rules

Name a rejected alternative ("over <Y>", `Rejected:`) only when it was actually
considered; `Rejected:` is optional. A decision with one viable option says why the
others fell away instead of inventing a second. A `note` decision may have no
alternative.

## Verification record (optional, both routes)

The last section of a spec that is worked without a plan. `specify` never creates it;
the first skill that writes there (`implement` or `verify`) adds it after every other
section:

````markdown
## Verification record

```text
Branch: <name>
```
````

After `Branch`, lines follow the same formats and append rules as a plan's execution
record (`plan-craft` plan template): `Commits`, `Initial dirty state`, `Task`, `Verify`,
`Round`, `Review`, `Finding`, `Received`, `Ruling`, `Deferred`, each added at the end of
the block, right before its closing fence. On a re-approval of a spec that has this
section, `specify` appends `Ruling: spec re-approved - <YYYY-MM-DD>`. The tree
fingerprint excludes the spec that hosts the record, as it excludes a plan.

Appending lines to a spec's `## Verification record` is not a material change and does not
reset its approval.

## Acceptance criteria rules

- One line per criterion: `AC<n>: <checkable predicate>`.
- Numbering starts at 1 and has no gaps; renumber after removing one.
- The predicate names something that can be observed (a command result, a visible
  state, a value in a file), never an activity such as "tests were written".
- Each criterion can be checked on its own, without reading the others.

## Acceptance criteria coverage

Check before saving the draft:

- `design`: every material behavior in `Behavior` and every item in `Contract` has at
  least one criterion, and every criterion traces to `Behavior`, `Contract`, or a
  decision;
- `note`: every criterion traces to `Goal` or a decision, and every decision that
  changes behavior has a criterion;
- critical failure and boundary cases have criteria;
- security and permission rules have criteria when they apply;
- no ceremonial criteria for trivial cases.

## Fresh-reader checklist

The fresh reader gets the spec file and this list, nothing else, and returns a verdict
(`pass` or the defect) for each item:

1. Every material behavior has an acceptance criterion.
2. No two decisions, or a decision and a criterion, contradict each other.
3. Inputs, outputs, errors, and edge cases are unambiguous.
4. Every assumption the design needs is verified, or listed as an open question or risk.
5. Security, permissions, and compatibility are covered where they apply.
6. A plan can be written from this file alone, without the conversation.

It also returns questions where a wrong guess by a builder would change the plan. It
does not propose new scope.

## Large requests

When the request holds several parts, the Goal lists them with a build order. A part
gets its own spec when it can be approved, built, and accepted without the others; parts
that share a decision or a contract, or ship together, stay in one spec with a block of
criteria each. Specify the first part in build order now; the Goal names the specs that
follow.
