# Review budgets by phase

The Round rule in SKILL.md limits automatic rounds. A chain can hold a document review of a
plan and then a review of the implementation; they are counted apart.

1. The phase follows the target, not the mode label: `document` for a spec, a plan or
   prose and their re-reviews, `code` for an implementation and its re-reviews.
2. Each phase has its own count of automatic rounds under the Round rule, with the same
   limit: three, or the count the user gave explicitly. The last allowed automatic round of
   a phase is decision-only, as the Round rule says.
3. The journal form is `Round review <n>: [document|code] <cause>`. A line without a phase
   takes the phase of the nearest `Review` line above it; when none exists it counts
   against both phases. Review IDs `R<n>` and finding IDs keep counting across phases and
   are never renumbered.
4. A new reviewer, a different model, a renamed document or `mode re-review` does not reset
   the count of its phase. Re-reviewing the same document or fix continues its phase.
5. One round count the user gave for the whole chain covers both phases together. Before
   the first document review, say how many rounds that leaves for the code review.
6. Permissions to call APIs, touch data or act outside the repository stay as they are in
   every phase.

## Scenarios

1. Two automatic document rounds, then the first code review finds an Important defect: the
   code review is automatic round 1 of 3 in the `code` phase; the fix path is open without
   asking the user for a fourth round.
2. Three automatic code rounds in a row: the fourth needs the user (`Next step: none -
   round limit reached, awaiting user`); document rounds before them do not add to the
   three.
3. The user said "two rounds": two automatic rounds in total across both phases. After two
   document rounds the code review needs a new permission, and the skill said before the
   first document review that no round would be left for code.
4. After the user allows one more round past the limit: the round is recorded with its
   `Ruling: round R<n> started by the user past the limit - ...` line, keeps counting from
   the next ID (`R6`, not `R1`) and does not rename the earlier rounds.
