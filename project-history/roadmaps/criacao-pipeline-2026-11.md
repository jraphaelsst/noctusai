# CoreStudio criação pipeline — roadmap (2026-11)

> Multi-session home for taking the CoreStudio media-creation pipeline (chat → headline + roteiro approval →
> Esteira card → Criação → media approval → post fields) from "landed on dev" to "producing in prod".
> Contract: `products/social-wiring/projects/core-studio-build/specs/criacao-pipeline-contract.md`.
> The `consent_ref` of `deploy/consent/social-wiring-criacao.prod.yml` points at milestone **M0** below.

## Phase 1 — internal test (nothing published)

- **M0: owner consent to publish social-wiring-criacao (the media worker)** — owner, 2026-11-23 ✅ 2026-11-23
- **M1: worker live in prod** — `social-wiring-criacao` service in `deploy/fleet/docker-compose.prod.yml`, deployed,
  claiming `media.step` jobs. Blocked on M0.
- **M2: Diretor de Criação agent in the agents product** — created from a published template through the
  agent-creator process, eval loop run (the refine loop of the agents product), published by the owner.
- **M3: `social-wiring:criacao-tools` token minted per org + `chat_diretor_criacao` on** — the CoreStudio chat is
  answered by the Diretor (strangler, per org). Blocked on M2.
- **M4: first reel end to end** — One Consultoria card: headline + roteiro approved → Criação → media approved.
  Needs the marca voice consent (signed PDF upload) for the narrated step.
- **M5: CTA labels** — the per-purpose CTA set the agent picks from, owner-approved.

## Phase 2 — deferred (trigger: owner says "next step")

- **HeyGen avatar captions** — HeyGen account + adapter for the Captions stage (avatar videos only).
- Context assembler / retrieval ranking / voz_amostras binding (S10); onboarding "método do criador" (S12);
  render per-scene progress.
