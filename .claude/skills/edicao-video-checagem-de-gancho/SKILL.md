---
name: edicao-video-checagem-de-gancho
description: Use to check or improve the opening of a short video — triggers "checar o gancho", "primeiros segundos", "abertura do reel", "o início está fraco", "hook", "primeiro quadro", "retenção no começo". Measures the frame at 0.0 s and 0.5 s (not black, not fading, title legible), the spoken hook within about 1.5 s, and visual change density; proposes a hook variant as a tracked A/B. Part of the Diretor de Edição set.
version: 0.1.0
---

# edicao-video-checagem-de-gancho — the first 1.5 seconds

## Workflow
1. **Extract** frames at 0.0 s and 0.5 s (`ffmpeg -ss 0 -i out.mp4 -frames:v 1`; and `-ss 0.5`). Measure, do not guess: mean luma (not near black), difference between the two (not mid-fade), and whether the title/hook band area is populated (compare against the preset's band region; if text is overlaid, OCR-free check = the planned overlay is `enable`d at t=0).
2. **Spoken hook:** from the transcript, the first speech must start by ~1.0 s and the hook statement complete by ~1.5 s (≈ ≤ 12 words). Leading silence/breath is trimmed by `edicao-video-corte-e-legenda`; if it is not, flag.
3. **Visual rhythm:** count scene/cut changes in the first 10 s (`select='gt(scene,0.3)'`); flag stretches of 3+ s with no change unless the preset is a calm format.
4. **Report** with evidence levels: each check `ok | falha | nao_medido`, with the measured value. A hook failure is a revision row, never silently fixed.
5. **Variants:** when proposing an alternative opening (different first take, title, first-frame image), store it as `variacao` (`variavel: gancho`, `hipotese`, `base_id`); `resultado` stays `nao_medido` until Redes Sociais metrics exist. Never present a variant as proven better.
6. Stills 0.0 / 0.5 / 1.5 s go into the sample for the user.

## Guardrails
Targets are heuristics from the preset (duration range, hook length), not laws; the user's roteiro wins. Do not invent a claim to make a hook stronger.

Spec: `gancho`, `variacao` in `KB § PATTERNS/media/video-edit-spec.md`.
