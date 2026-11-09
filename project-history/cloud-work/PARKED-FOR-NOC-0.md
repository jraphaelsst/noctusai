# Parked items → noc-0 (owner order 2026-11-09)

**Owner:** none of these are worked on until the **agentic architecture work** is finished.
noc-0 holds the list; pick it up after that. The cloud steward session is closing.

## 1 · Ship / git (steward's)

- `cloud-work-2` landed on dev (48af0600e). **Prod deploy is yours** — deploy notes are in that
  READY commit body (fleet-wide FE: Tailwind 4 + lucide 1.x; open one page per product after).
- `cloud-work-3` (this branch, docs only): enqueue whenever.
- GitHub cleanup awaiting owner OK: ~58 stale branches + ~39 dependabot PRs —
  `MANIFEST.md` §2/§3 (also delete `fix/deploy-verify-truncation-explicit(-r2)`, `cloud-work`, `cloud-work-2`).

## 2 · Owner decisions (from the archived Oct-11 hub)

See `OPEN-DECISIONS-from-2026-10-11-hub.md` (10 items: SW org redesign, QuintoAndar/Vista fixes,
IgIg help-chat key, Store Asaas URL, contract walkthrough, academia data/domain, image-swap
consents, Limiar tweaks, NF-e scope, contract PDF/.docx + LGPD intake).

## 3 · Items that lived only in Mac sessions (being archived)

| From session | Pending |
|---|---|
| Seed agent e noc-new-agent | Owner Q14: Haiku's role — A) runs the agents now, B) stand-in for our own LLM while we build training/serving, C) both. Context in memory `project_own_llm_learning.md`. |
| Session context request (10-17) | Delete the 11 test deals in prod? Restart MCP (`/mcp`). |
| Pick-a-winner (contract v3, SW / One Consultoria) | Owner: in Favorecidos → Santa Maria Fracasso, keep only the bank in "Banco", move agência/conta to their fields. Then: generate contract v3 dated 12/10 and compare with v1, v2 and the signed contract. |
| Haiku 4.5 support chat (10-09) | Help-chat save path untested in prod (chat once in IgIg, check `help_chat_conversas`). |
| Release notes / limiar-app | Optional: "Próximo" label on the next arrow; move the step-screen links up (limiar-app repo). |
| Instagram 10449 campaign | Minor: translate the .md report to pt-BR too? |

## 4 · Not parked — still running

- **Ad-lead brief and Julia's handover** (Mac, active): `feat/agents-eval-consolidation` (ace65298e) is
  queued with you, after the parallel-eval-runs change; its background intake engineer is still
  running; the Vista key one-liner waits on the owner. Do not archive it until it finishes.
