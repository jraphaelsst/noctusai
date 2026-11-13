---
name: edicao-video-zona-segura
description: Use to verify text and graphics stay clear of platform UI and the face — triggers "zona segura", "safe zone", "a legenda some atrás do botão", "texto cortado no reel", "checar posição do texto", "interface do Instagram cobre". Checks the union of every caption, lettering and insert box across its whole animation (including overshoot and camera moves) against a per-platform zone table, and produces an overlay sheet for review without burning the overlay into the master. Part of the Diretor de Edição set.
version: 0.1.0
---

# edicao-video-zona-segura — check the whole animation, not the anchor

## Workflow
1. **Zone table as data** per `saida[].destino_sugerido` (rede × formato × aspect): margins for top, bottom, right, left as % of the frame. **Values must come from the official documentation via the CoreStudio validity matrix (`post_formatos.py`, slice S1) with a citation.** Until that exists, use the conservative placeholder below and mark every result `nao_verificado`:
   `{9:16: top 12 %, bottom 22 %, right 12 %, left 6 %}`, `{4:5: 8/12/6/6}`, `{1:1: 6/8/6/6}`, `{16:9: 6/10/6/6}`. These are our own conservative defaults, not platform numbers.
2. **Boxes:** for each caption group, lettering and insert, compute its bounding box at EVERY frame of its animation (enter, hold, exit, overshoot, camera/zoom). Use the union. For ASS captions, derive from font metrics × text width; for overlays, from the filter geometry; when unsure, measure by rendering a mask frame and finding the bounding box of changed pixels.
3. **Face region:** from the reframe/face track (or a detected face box on sampled frames) — text must not cover the face except where the preset allows.
4. **Findings** as rows: element, frame range, which margin is violated, by how many %, suggested fix (move, re-break, shrink last). Violations become revision rows; fix automatically only within the preset's tolerance and say so.
5. **Overlay sheet:** a copy of 3–5 stills with the zone drawn (`drawbox`) for the review UI. The delivered master never contains the overlay.
6. Re-run after any layout or caption change.

## Guardrails
Do not claim a platform's exact UI geometry from memory; say the table is a conservative default until verified. Platform UI changes: the table is versioned data (`zonas-por-rede@vN`).

Spec: `zona_segura` in `KB § PATTERNS/media/video-edit-spec.md`.
