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
