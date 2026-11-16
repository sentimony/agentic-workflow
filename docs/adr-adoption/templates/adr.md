# ADR template

Use the [ADR policy](../policy.md) and its project-specific canonical sources. Copy
only the relevant block in the project's language. Title, status, actual recorded
date, context, decision, and reason are required. Remove optional fields when they add
no useful explanation of the trade-off.

## New decision

```md
# <Short decision title>

Status: proposed
Recorded date: <actual YYYY-MM-DD>

<Context: what required a choice. Decision: what is proposed. Reason: why this
option fits the constraints and which trade-off is accepted.>

Approval: <pending; after explicit owner approval, record who, when, and the
supporting source, then change the status to accepted>
```

Statuses: `proposed`, `accepted`, `deprecated`, `superseded`. A superseded record
requires a replacement link. Saving an ADR grants no implementation, push, merge,
release, or external-action permission.

Use `NNNN-short-title.md` for a separate file. Read existing records, choose the next
free number after the highest, and recheck immediately before creating it exclusively
as a new file, for example Python `open(path, "x")`. Coordinate a single writer or lock
for number selection and creation. On collision, reread the numbers and try another.
Preserve earlier filenames and records. Create the designated collection only when
saving its first real ADR.

## Optional fields

1. Retrospective: yes; supporting sources; a separate known historical decision date.
   The recorded date is always the actual creation date.
2. Alternatives and consequences that explain the real trade-off.
3. Replaces: a link to the earlier record. Once replacement is explicitly approved,
   retain the earlier record with `superseded` and a reverse link. Until approval the
   earlier decision remains current.
4. Cancellation reason and evidence of the owner's decision for `deprecated` without
   replacement.

## Existing journal compatibility

Preserve the existing journal's identifiers, ordering, and equivalent fields. Its
entry can contain the minimum contract in this form:

```md
## <Actual recorded date YYYY-MM-DD> - <Title>

Decision: <Context and proposed or approved choice.>
Reason: <Rationale; identify anything unknown explicitly.>
Status: proposed. <Approval evidence once available; retrospective marker and
sources for a historical entry; a separate historical date only when known;
links to the previous or replacement entry when applicable.>
```

Keep the original text. On replacement, add the status and links in both records.

## Teaching example 1: verified historical approval

Every detail below is fictional: the Paper Moon Observatory, its owner, protocol, and
technical choice. The source identifier is a teaching placeholder that does not exist
in this repository. Keep this example in the template; it is no real product ADR.

```md
# One catalog of star postcards

Status: accepted
Recorded date: 2026-11-01
Retrospective: yes
Historical decision date: 2025-04-12
Evidence: fictional protocol PM-7, 2025-04-12, item 2; Marta, owner of the
fictional observatory, explicitly approved one catalog instead of a catalog
per dome, together with the rationale below.

Domes exchange star postcards, and moving their stable identifiers between
catalogs would be costly. The owner chose one catalog to keep each postcard's
identifier stable across domes. The trade-off is dependency on shared catalog
availability. The protocol verifies approval; retrospective recording needs
no new adoption of this historical choice.
```

The actual recorded date of this fictional example is 2026-11-01. The separate
2025-04-12 date is its fictional historical decision date.

## Teaching example 2: unknown original reason

Every detail below is fictional: the Glass Wind Museum, its architecture, and the
search results. This is a demonstration of uncertainty, retained only in the template.
It is not a decision for a real project.

```md
# Keep a shared kite-route archive

Status: proposed
Recorded date: 2026-11-01
Retrospective: yes; describes observed state, approval not established
Evidence of facts: fictional diagram MZ-4 shows one shared archive; no approval
was found in the fictional documents and commits examined.

Kite routes already have identifiers in one archive, and splitting it would
require migrating references. Original reason unknown. Historical decision
date unknown; owner approval is unverified. The agent proposes adopting the
shared archive today because migration would be costly, accepting a shared
update cycle. The owner may leave the question open or approve the new choice
today. Until explicit approval, the proposal remains proposed.
```

If the owner approves adoption today, record that approval and today's date as a new
decision. Keep the original historical reason explicitly unknown.
