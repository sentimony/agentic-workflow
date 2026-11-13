# Enforcement ladder, rule forms, and placement surfaces

## The ladder

A learning is pinned on the highest rung that can carry it. Each rung down relies more on
an agent reading and obeying text.

1. **Structure** - make the wrong action impossible or unnatural: a file layout, a name,
   a single entry point, a default that is already right.
2. **Type** - a schema, a type, or a config field that rejects the wrong value.
3. **Check or lint** - a script, a CI step, a hook, or a lint rule that fails loudly.
4. **Test** - a test that turns red when the behavior regresses.
5. **Prose** - a line in an instruction file.

Rules for climbing:

- A mechanical rule (a forbidden character, a required flag, a file that must exist) is
  proposed as a check or a hook, with the prose line at most pointing at it.
- A learning that comes back although a prose rule already covers it moves one rung up.
  Rewording the same line is not a fix: the line was there and did not hold.
- Recording only names the higher-rung change in the note. A check, a hook, or a test is
  a code change: triage drafts it, it goes through the approval step like any edit, and
  the user may choose to keep only the prose line.
- When the candidate stays on `prose`, its record names why the rungs above do not fit.

## Rule forms

Pick the form by the kind of failure, not by habit:

| Failure | Form | Shape |
| --- | --- | --- |
| An action did damage or wasted a run | prohibition | "Do not X when Y: Z happens." |
| The right command or sequence was found by trial | recipe | "To X, run Y (not Z: reason)." |
| A required piece of an artifact was missing | template slot | a new field or heading in the template the project already uses |
| Behavior differs by situation | condition | "When X, do Y; otherwise Z." |

A recipe copies the flags of the command that worked verbatim: shorten the explanation,
never the command. "Connect with `psql -h <host> -p <port> -U postgres -d postgres`" works
on a fresh cluster; trimmed to `psql -h <host> -p <port>` it fails on the missing role.
Step 7 runs the written form before the note is recorded, and triage runs it again on the
text that goes into the target.

Write the rule, not the story. "On 2026-10-21 the push failed because..." is a story;
"Push with X when Y: otherwise Z" is a rule. Dates, branch names, and who did what stay in
the session.

## Placement surfaces

Beyond the instruction files (root, nested, global, other repositories), a learning can
belong in:

- **A file read during review** - a contributing guide, a review checklist, or a pull
  request template, when the rule is about what reviewers should catch.
- **A glossary** - when the learning is a name: which term the project uses for a thing,
  and which old or ambiguous terms it replaces.
- **A decision record** - only for a decision that is hard to reverse, not obvious from
  the code, and the result of a real trade-off. Record the options and why the chosen one
  won. Routine conventions do not get one.
- **A "why" comment beside the code** - when the rule is about one place in the code and
  a reader there is the one who needs it.

Prefer the surface the next agent will read at the moment it needs the rule. A rule in
the root instruction file is paid for on every session; a comment beside the code is
read only where it applies.
