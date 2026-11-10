# Multi-steward study: branch steward ↔ dev steward (started 2026-11-09)

> The owner set this up as a study round ("we're studying and evaluating"). Two stewards work in
> parallel:
> - **noctusai-22** is the BRANCH steward, owning `feat/assistant-chatbot`.
> - **noctusai-b5** is the DEV steward, owning the merge queue into `dev`, release and deploy.
>
> This file logs what happens as it happens. The final refinement is written from it, not from
> memory.

## Hypothesis
- A two-tier model is cheaper and safer than a single steward that handles every slice, or
  than N peers each merging to `dev`.
  - Branch stewards integrate their own slices into a long-lived integration branch.
  - Exactly one dev steward owns the queue, release and deploy.
- **Metrics:**
  - deliveries per ejection
  - number of steward↔steward messages per delivery
  - re-merge conflicts on shared surfaces
  - wall-clock time from "packet sent" to "LANDED"
  - owner interruptions (target: 0 small asks under the free pass)

## Proposed protocol (v0, sent to b5 2026-11-09)
1. **Roles:**
   - The dev steward is the only writer to the merge queue, and owns release and deploy.
   - A branch steward owns its integration branch and never touches the queue, `main` or the VPS.
2. **Delivery packet:**
   - branch@sha, already merged with `origin/dev`, gates green, pushed
   - slug
   - migrations
   - products touched
   - hot shared files
   - fleet-wide notices
   - whether a deploy is wanted
   - consent reference
3. **Verdicts:**
   - The dev steward replies `LANDED <sha>` or `EJECTED <reason>`.
   - The branch steward fixes on its own branch and re-delivers; the dev steward never patches it.
4. **Early warning:** the dev steward pings the branch steward when `dev` lands something that
   touches shared surfaces (`.claude/agents`, `.claude/skills`, CLAUDE.md, KB INDEX).
5. **Collisions on derived artifacts:** the queue tree wins and the branch steward re-merges.

## Observations log
| when (UTC-3) | who | observation |
|---|---|---|
| 2026-11-09 | 22 | The owner's split arrived as one long free-text message. The branch steward had to rebuild the session→work map from memory files before relaying it, and the peer sessions had each announced themselves without a shared roster. Friction: there is no canonical "who owns what" registry between sessions. |
| 2026-11-09 | 22 | The council tools on the unlanded branch were not loadable as MCP tools or agent types in a session started on primary, so the council ran via the CLI plus general-purpose seats. Friction: an integration branch's own tooling is unusable until it lands in `dev`, which argues for landing methodology early and on its own (D1). |
| 2026-11-09 | b5 | It inherited the steward role and reconstructed the per-session worktree split into a scratchpad handoff file (`WORKTREE-HANDOFF-2026-11-09.md`). The handoff lives in a session-private scratchpad, not a durable place. |
| 2026-11-10 00:20Z | b5 | After the reboot every session came back under a NEW name (noc-0/83/74/fc → b5/e4/e1/22). Nothing mapped old roles to new names, so peers and the owner re-established who is who by hand. |
| 2026-11-10 00:25Z | b5 | Fresh sessions answered "not a resumed session" before any role was assigned; e4 had to correct itself after the owner told it. A role registry is missing. |
| 2026-11-10 00:30Z | b5 | The steward lease went stale on reboot and the guard denied the enqueue until it was claimed. That worked as intended, but a new steward only learns the claim+announce step from the denial. |
| 2026-11-10 00:35Z | b5 | sw-roteiro-ciclo FE+BE was declared "ship together" but enqueued as 2 entries. BE was ejected and FE landed alone, so dev is not deployable for SW. A multi-branch delivery must be ONE train entry. |
| 2026-11-10 00:40Z | b5 | The steward inbox kept 5 already-landed requests as "queued"; they were reconciled by hand with git cherry. Needs auto-reconcile. |
| 2026-11-10 00:44Z | b5 | A parked branch's migration number (feat/council-db-parked, agents 073) blocked another session's enqueue through the collision gate. Rule: a parked branch never holds a migration number. |
| 2026-11-10 00:45Z | b5 | Consent relays ("type it to noc-0") die with the session name on reboot. Consent must be typed in the session that runs the action. |
| 2026-11-09 | 22+b5 | Protocol v1 agreed in 2 messages: v0 proposal + 4 amendments (A1 packet via the release_steward tool inbox, durable across reboot; A2 methodology delivery alone, re-merge after overlapping entries land; A3 no migration number on a parked branch; A4 prod migration consent typed in the dev steward's session). |
| 2026-11-09 | 22 | The primary-dirt guard blamed the branch steward for transient `.merge_file_*` files. These come from merge drivers configured with absolute paths into the primary, so the guard misattributes concurrent activity during merges. |
| 2026-11-09 | 22 | The branch steward ran the council and dispatched 4 file-disjoint fix slices off its integration branch, with no dev-steward involvement. Integration-branch autonomy worked; 0 owner asks so far under the free pass. |
