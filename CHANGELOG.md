# Changelog

The historical entries below were reconstructed from annotated release tags and
Git commit subjects. Skill changelogs retain the detailed skill history.

## [0.0.17] - 2026-11-01

1. Retire embedded cross-cr and integrate the separately installed cross-agent 0.0.1
   through a versioned workflow owner adapter.
2. Preserve immutable review provenance, opaque intake binding and separately measured
   post-action identity.
3. Update cr-request 0.0.12, cr-received 0.0.8, plan-craft 0.0.7 and verify 0.0.8
   without changing delivery contracts.
4. Native pair installation and live resume remain unverified:
   https://github.com/sentimony/agentic-workflow/issues/31.

## [0.0.16] - 2026-11-01

1. Isolate mutable verification dependencies and require fresh project checks for
   hostless ready PRs, bound to the current committed target.
2. Separate fresh local readiness from strict merge eligibility: remote jobs can start
   after ready, unknown policy stays unknown, and merge waits for applicable checks.
   Add finite deadlines and target guards before checks, ready, waiting and pinned merge.
3. Preserve post-merge task evidence through authorized own-comment readback and an
   ignored durable pending store, without editing tracked plan/spec content on base.
4. Require captured ownership and canonical evidence for transferred duplicate-hunk
   removal. Guard branch/workspace disposal separately with current authority,
   integration or retention, local data checks and explicit trusted task inventory.
   No-task local/committed work needs no fabricated patch, PR or deployment; unknown
   inventory and actual pending evidence block disposal. Preserve foreign staging.
   Block whole-clone removal with common Git storage inside its removal root; linked
   worktrees need surviving common storage and retaining refs outside that root.
5. Add offline integration coverage and CI discovery-count guards. Live forge and
   production validation, installation migration and native evals remain unverified;
   owner-accepted follow-ups: https://github.com/sentimony/agentic-workflow/issues/29
   and https://github.com/sentimony/agentic-workflow/issues/30.

## [0.0.15] - 2026-11-01

1. Rename the plugin identity and active command namespaces from aw to agentflow,
   retaining the repository, skill names and legacy state identifiers.
2. Document explicit uninstall/reinstall migration without a duplicate alias plugin.
3. Update cross-cr 0.0.5, finalize 0.0.7 and session-learnings 0.0.6 references.
4. Native migration evidence remains unverified; owner-accepted follow-up:
   https://github.com/sentimony/agentic-workflow/issues/29.

## [0.0.14] - 2026-11-01

1. Move the aw plugin and its unchanged skills to the repository root.
2. Add portable and Antigravity manifests alongside the Claude Code and Codex manifests.
3. Validate root discovery and preserve historical pinned review-skill loading.
4. Native installation, invocation, scratch authorization and migration evidence
   remain unverified under the owner-approved release exception; follow-up:
   https://github.com/sentimony/agentic-workflow/issues/29.

## [0.0.13] - 2026-11-01

1. Refactor cross-cr 0.0.4 into a compact entrypoint and linked workflow details,
   preserving its contract and adding body-size, link, and heading regression checks.
2. Include review-operation documentation (#21) and shared reviewer-package alignment
   (#24), integrated before the cross-cr refactor.

## [0.0.12] - 2026-10-30

Release tag: `v0.0.12` (`1da49d402e41b47d41fa0a381d2c02f6e0c1eaef`).

1. Tag summary: aw 0.0.12: cr-received 0.0.7, cr-request 0.0.11, cross-cr 0.0.3,
   finalize 0.0.6, implement 0.0.6, plan-craft 0.0.6, specify 0.0.6, verify 0.0.6.
2. Unify review cycles and isolate thread resolution (#20).

## [0.0.11] - 2026-10-30

Release tag: `v0.0.11` (`49a4056bcd62df4a2715dd0aff22631f01789a2b`).

1. Tag summary: aw 0.0.11: specify 0.0.5, plan-craft 0.0.5, implement 0.0.5, verify
   0.0.5, cr-request 0.0.10, cr-received 0.0.6, cross-cr 0.0.2, finalize 0.0.5,
   session-learnings 0.0.5.
2. Compact yngwald reviews with inline comments and the latest cr-request (#17).
3. aw 0.0.11: --auto chain, checkpoints, verification record, CI footer (#16).

## [0.0.10] - 2026-10-29

Release tag: `v0.0.10` (`60202753592e77b0c2efecd36dd9e812d15381a5`).

1. Tag summary: aw 0.0.10: specify 0.0.4, plan-craft 0.0.4, implement 0.0.4, verify
   0.0.4, finalize 0.0.4, cr-request 0.0.9, cr-received 0.0.5.
2. Release aw 0.0.10: external audit fixes for the aw chain (#15).

## [0.0.9] - 2026-10-27

Release tag: `v0.0.9` (`612e6617904df3deb38dc84808e3b673be8921df`).

1. Tag summary: aw 0.0.9: cr-received 0.0.4, cr-request 0.0.8, finalize 0.0.3, implement
   0.0.3, plan-craft 0.0.3, specify 0.0.3, verify 0.0.3.
2. Release aw 0.0.9: specify rounds, approval invariant, no own marketplace.

## [0.0.8] - 2026-10-27

Release tag: `v0.0.8` (`873431d9eb6127a54cff512dcd7979c2396c910a`).

1. Tag summary: aw 0.0.8: cr-received 0.0.3, cr-request 0.0.7, cross-cr 0.0.1, finalize
   0.0.2, implement 0.0.2, plan-craft 0.0.2, session-learnings 0.0.4, specify 0.0.2,
   verify 0.0.2.
2. Release aw 0.0.8: rename awf to aw, add cross-cr 0.0.1 (#13).

## [0.0.7] - 2026-10-27

Release tag: `v0.0.7` (`02a24b46148be6106ed63841b42d28ce885cd523`).

1. Tag summary: awf 0.0.7: session-learnings 0.0.3.
2. Review footer with duration and Next step last; pin cr-request v0.0.6 (#10).
3. Check the full Next step line format in the review validator (#11).
4. Release awf 0.0.7: session-learnings 0.0.3 for subagents (#12).

## [0.0.6] - 2026-10-26

Release tag: `v0.0.6` (`1e151554148db6086fbb6a1f17374508cc321664`).

1. Tag summary: awf 0.0.6: cr-request 0.0.6.
2. Align Claude review: cap auto reviews, SHA concurrency, hide .claude (#7).
3. Cancel outdated Claude reviews per PR, drop nested CLAUDE.local.md (#8).
4. Release awf 0.0.6: cr-request footer order for CI reviews (#9).

## [0.0.5] - 2026-10-26

Release tag: `v0.0.5` (`9f4b16728d4e4613e9ca55430838b96604d9dd2a`).

1. Tag summary: awf 0.0.5: cr-request 0.0.5.
2. Split Claude review into gate, review, and publish jobs (#5).
3. Release awf 0.0.5: cr-request headless reviewer and versioned signature (#6).

## [0.0.4] - 2026-10-24

Release tag: `v0.0.4` (`a5cf04b2d5d72d6fa624bdb46223f1ada6a2047a`).

1. Tag summary: awf 0.0.4: cr-received 0.0.2, cr-request 0.0.4, finalize 0.0.1,
   implement 0.0.1, plan-craft 0.0.1, session-learnings 0.0.2, specify 0.0.1, verify
   0.0.1.
2. Add the awf workflow chain and update review and learnings skills (#4).

## [0.0.3] - 2026-10-18

Release tag: `v0.0.3` (`132a003019d2a8bb467079364b9b6695462cfe9a`).

1. Tag summary: awf 0.0.3: cr-received 0.0.1, cr-request 0.0.3, session-learnings 0.0.1.
2. Release awf 0.0.3: cr-received, session-learnings 0.0.1, auto review on cr-request
   v0.0.2 (#3).

## [0.0.2] - 2026-10-18

Release tag: `v0.0.2` (`006400f88d768452a9aa07c6736bbbb7bb5d55c3`).

1. Release awf 0.0.2: cr-receive 0.0.1, cr-request 0.0.2, auto review without F2 (#2).

## [0.0.1] - 2026-10-18

Release tag: `v0.0.1` (`39626fcce7cadd6a77b1cf5ebc6b0ce922f37960`).

1. Add awf plugin with cr-request skill 0.0.1 (#1).
