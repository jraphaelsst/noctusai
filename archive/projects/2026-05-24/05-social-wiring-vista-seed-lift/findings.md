# social-wiring-vista-seed-lift — Findings

> Phase-6 close note. The lift shipped cleanly in one push (Wave 1-2, 2026-05-20) and was
> live-validated against `ONE10010` (Casa em Alphaville). This file is the curated knowledge
> artifact, not a transcript — §11 of PROJECT.md holds the what-we-did.

## Errors encountered
- None functional. The migration kept the social-wiring backend suite green throughout
  (465/465 at Wave-2 close); seed-lib suite 1761/1761 after the adapter layer landed.

## Mistakes / slips
- **Phase-5 doc instruction was a phantom.** The PROJECT.md §6 Phase-5 line said "update
  `seed-lib-layout.md` § integrations roster (auto-derived; ensure listing)" — but that doc
  is a *layer-layout guide*, not a per-service inventory, and has no auto-derived roster.
  No action was needed there; the instruction was written against an assumed structure that
  doesn't exist. (Codebase-is-source-of-truth: verify the target before scheduling the edit.)

## Lessons learned (durable rules)
- **Split transport from domain at lift time.** Vista REST access went to
  `integrations/vista` (IO; Protocol+Fake+Real+factory), while `PropertyData` +
  `build_youtube_metadata` + `validate_product_code` went to `domain/real_estate` (pure logic).
  The YT-metadata shape is *real-estate-specific, not Vista-specific* — it could be fed by any
  CRM — so it fails the "would a Fake here exercise different code than the Real?" test and
  belongs in `domain/`, not `integrations/`. Mirrors `KB § PATTERNS/seed-lib-layout.md`.
- **Consume-docs ship in the same project that lifts the code** ([[feedback_absorption_ships_consume_docs]]).
  `KB § CONTEXT/INTEGRATIONS/vista.md` §6a (consume recipe) + §8 (change-log) landed
  same-day with the seed modules — not deferred. Honored R1.

## Interesting findings (surprises, discoveries)
- **A lower-level `VistaClient` already shipped** (formalized 2026-05-03 from the ERP showcase
  + `mcp/vista` at N=2). The new high-level `VistaRESTAdapter` (`get_property(code) → PropertyData`)
  was built to *compose alongside* it rather than replace it — the low-level client is
  endpoint-level (`/imoveis/detalhes`, normalizers, showcase DTOs); the adapter is
  consumer-facing (one property by code → cross-CRM domain shape). Both legitimately coexist.
  The architect ratified this deviation (the engineer surfaced it mid-Wave-1).

## Knowledge pieces (durable patterns)
- **Open N=2 DRY follow-up (tracked, not blocking):** `VistaRESTAdapter` currently re-implements
  the `/imoveis/detalhes` httpx call (byte-for-byte port of the old product-local `crm_service.py`).
  At the next consumer it should be refactored to compose
  `VistaClient.detalhes_imovel(...)` + `vista_imovel_detalhes_to_showcase` + a small
  showcase→`PropertyData` mapper, eliminating the duplicated transport. Triage: [R] refactor at
  N=2. Recorded in `vista.md` §6a "Composition vs §5 low-level client" + §8 change-log.
- **Consume recipe (first consumer = social-wiring):**
  `from noctusai_lib.integrations.vista import get_vista_adapter, VistaError, VistaNotConfigured`
  + `from noctusai_lib.domain.real_estate import build_youtube_metadata, PropertyData, validate_product_code`.
  Product-local `crm_service.py` is gone (zero local copy).
