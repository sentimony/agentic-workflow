# Review Lenses

Prompts for attention, applied with judgement. Apply what the change touches; skip
what tooling (compiler, linter, formatter) already enforces. The project's documented
standards override every heuristic here.

## Intent

- Every acceptance criterion maps to a change; each partial one is named.
- Each changed file has a reason traceable to the objective; unconnected edits are
  scope findings even when they are good code.
- The change solves the stated problem itself, without swapping in an easier neighbor.
- Behavior the spec is silent on matches what a reasonable user would expect.

## System

Look past the diff to what it touches.

- **Contracts** - signatures, schemas, formats, error shapes, exit codes. Who depends on
  them, and does anything break for existing callers or stored data?
- **Data and state** - invariants, validation at trust boundaries, nullability and
  empty cases, encoding, units, time zones, precision.
- **Failure paths** - errors surfaced or swallowed, partial writes, cleanup, retries and
  idempotence, timeouts.
- **Concurrency and order** - shared mutable state, races, reentrancy, ordering
  assumptions.
- **Feedback loops** - caches, retries, queues, and background jobs that amplify a small
  error.
- **Security** - injection, authorization on every path, secrets in code or logs, unsafe
  deserialization, path handling.
- **Resources** - unbounded growth, N+1 access, hot-path cost, leaked handles.
- **Operability** - observability of the new behavior, configuration defaults, migration
  and rollback, backward compatibility, release order.

## Craft

- Names say what a thing does or holds.
- Each unit changes for one reason; one logical change does not scatter edits widely.
- Abstraction matches present needs: no speculative parameters, hooks, or layers, and no
  wrappers that only rename.
- Duplicated logic is the concern; similar-looking text is fine.
- Tests exercise required behavior and material negative paths, assert outcomes rather
  than implementation details, and would fail if the behavior broke.
- The change follows local idioms of the surrounding code.
- Leftovers: debug output, commented-out code, stray files, unpinned dependencies.

## Documents

For a spec or plan under review, the axes keep their names and change their object:

- **Intent** - the document answers the request it came from: every stated need is
  covered, and nothing outside the request is decided silently.
- **System** - it agrees with the repository as it is (paths, commands, names, versions
  that exist) and with neighboring specs, plans, and instructions; a conflict names
  both sides.
- **Craft** - each acceptance criterion is a checkable predicate; no placeholders, open
  TODOs, or steps without a command; names stay consistent across sections; a plan task
  lists its inputs, outputs, and the criteria it covers.

Locate each finding by section (`§<heading>`), not by line.

## Re-review

- Check each previous finding against the fix diff, not against the author's reply.
- A fix that moves the defect elsewhere is `NOT ADDRESSED` plus a new finding.
- Look for breakage the fix introduced in its own lines; older code outside the fix diff
  is out of scope for this round.
- Outside the fix diff, report only a regression the fix caused, tagged `[regression]`,
  with evidence that links it to the fix.

## Common smells

Judgement calls, always labelled "possible": unclear name, duplicated logic, a function
more interested in another module's data than its own, values that always travel
together, a primitive standing in for a domain concept, the same branching on a type
repeated across files, a pass-through layer, an inherited interface mostly ignored.
