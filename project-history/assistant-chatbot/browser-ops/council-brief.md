# Council brief: server-side browser automation in place of the Google and Meta official APIs (for now)

## Subject
The owner (2026-11-10) asked whether to run a container on the prod VPS with Chrome. Claude would automate actions in it "as if it were me logged in", for Google (Drive and the like) and Instagram (checks and automations, on one account and possibly several). This would defer the official APIs and app verification for Meta and Google, because "we need time": validate the process where and how we can now, then verify the apps for the official APIs. The owner also floated "an API that listens for and receives requests and executes them on Google Drive through the server's browser". The first consumer is the Assistant product: the owner's personal assistant on WhatsApp via WAHA (an unofficial client, whose ban risk the owner has already accepted), which replies in the owner's self-chat.

## The decision to challenge
Should this browser-ops design be adopted for now, and in what shape? Options on the table (not ranked):
- **A.** As asked: one or more browser containers on the VPS for BOTH Google and Instagram, with Claude driving them.
- **B.** No browser for Google: add the Drive, Sheets and Docs write scopes to the existing owner OAuth client and use the API. A browser container only for Instagram.
- **C.** No server-side browser yet: keep browser automation on the owner's laptop (Claude in Chrome, which already works) until the official APIs are in place.
- Any other option you can defend.

Sub-decisions:
1. One container per account, or one container with a profile per account?
2. How the owner's login and 2FA get in (noVNC through the tunnel behind Cloudflare Access, or an SSH port-forward only).
3. Claude's runtime role: free browsing, recipe-only tasks, or Claude only at dev time to write recipes.
4. The owner's primary accounts, or dedicated or expendable accounts, for the first version.
5. Multi-account, including possible client accounts.

## Constraints
- Prod is one VPS: 8.1 GB RAM total, about 3.5 GB available, 2 vCPU, 18 containers, measured 2026-11-10. A Chromium context is estimated at 0.4–1 GB (not measured).
- House rules: seed-first with Fake+Real+factory for seed IO; MCP-first; access tiers (a route acting with the owner's identity is `platform` tier); no silent errors.
- Google today: the owner refresh-token trio in the NoctusAI GCP project drives Calendar, Drive read and Gmail. The seed Drive reader exports Sheets and Docs. There is no Sheets or Docs write code. A personal app with fewer than 100 users needs no verification (whether a published but unverified app's tokens outlive 7 days is unverified).
- The owner decides on prod exposure. The council informs; the session that called it decides.

## Evidence: four specialist position reports (independent, written before this council)
Read all four (claim, grounds, proposal, acceptable, red lines, open questions):
- /private/tmp/claude-501/-Users-rapha-Documents-repository-NoctusAI-noctusai/5ff8685d-cc9e-45fd-b31b-09ebd5f822d3/scratchpad/browser-ops/architect.md
- .../browser-ops/security.md
- .../browser-ops/agents-security.md
- .../browser-ops/legal.md

(All four are in that `browser-ops` folder of the scratchpad path above.) Where the reports disagree (container count against capacity, the login channel, proxies), say which side you take and why.

## Repo
/Users/rapha/Documents/repository/NoctusAI/noctusai/.claude/worktrees/assistant-chatbot, read-only. Relevant files:
- `quintoandar-agent/playbook/browser.md` (how laptop browser automation behaves today)
- `.claude/skills/noc-ig-analysis/SKILL.md`
- `.claude/skills/noc-refs-sheet/SKILL.md`
- `mcp/google_workspace/`
- `seed/lib/backend/noctusai_lib/integrations/`
- `project-history/assistant-chatbot/phase0-audit-assistant.md`
