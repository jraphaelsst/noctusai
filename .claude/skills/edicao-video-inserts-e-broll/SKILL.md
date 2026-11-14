---
name: edicao-video-inserts-e-broll
description: Use to add images, cards, b-roll or motion inserts synced to what is said — triggers "coloca b-roll", "insere imagem quando eu falo", "cartão com o dado", "mostra o imóvel enquanto eu descrevo", "animação explicativa", "inserções", "cobrir o corte", "punch-in", "zoom". Plans inserts against transcript spans, checks rights and provenance per asset, composes with ffmpeg overlays or stacked layouts, and asks before any third-party material or paid generation. Part of the Diretor de Edição set.
version: 0.1.0
---

# edicao-video-inserts-e-broll — every insert answers a sentence

## Workflow
1. **Inventory the assets** the user supplied (photos, clips, logos, listing data). Give each a role (`prova | demonstracao | ilustracao`) and a rights state (`proprio | licenciado | terceiro_nao_liberado | desconhecido`). Unknown ⇒ treat as not usable until the user says whose it is.
2. **Plan per scene** (not per second): for each span that needs support write `entender / olhar / muda / permanece` (what the viewer must understand, where to look, what changes, what stays) and the insert that does it. Reject inserts that decorate without proving; reject a beat with no object that supports the sentence.
3. **Anchor** to transcript spans/word ids (`edicao-video-legenda-por-palavra`), enter/hold/exit in the preset's tokens; minimum hold so it can be read (~0.8 s + 0.06 s per word on screen), no empty gaps between consecutive inserts.
4. **Compose, base tier first:** full-frame cover, top-insert/bottom-presenter, stacked frames, corner frame, side card; slide/fade `overlay` with `enable='between(t,a,b)'`. Punch-in alternation (zoom 1.0 / ~1.12 in alternating ranges) masks jump cuts; recentre the crop after each cut. Layouts are named regions in % of the frame (preset data).
5. **Motion cards** (animated lists, counters, diagrams) are overlay-tier: only if a render stack is approved (spec doc §7); otherwise propose a static card with a fade.
6. **Labels:** illustrative or reused material gets a visible label ("ilustrativo", "exemplo"). Prices/areas/claims shown must match the listing record; numbers need `fonte` + `data`.
7. **Third-party footage / scraping / AI-generated assets:** off by default. If the user asks, record named acceptance (who, when, asset) in `proveniencia` and ask the `legal-advisor` path; paid generation needs an explicit spend ceiling and approval.
8. **Verify:** insert windows inside the sentence span (±0.3 s), no insert covering the face of the presenter beyond the preset's allowance, stills of 3 key moments.

## Guardrails
Real-estate extras on request: blur plates/faces/house numbers; CRECI/disclaimer card slot. Voice is never re-encoded through the graphics path (mux the original audio back).

Spec: `insercoes[]`, `cenas[]`, `proveniencia` in `KB § PATTERNS/media/video-edit-spec.md`.
