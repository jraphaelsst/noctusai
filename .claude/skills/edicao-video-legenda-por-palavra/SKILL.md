---
name: edicao-video-legenda-por-palavra
description: Use when captions or lettering must land on the exact spoken word — triggers "legenda palavra por palavra", "destacar a palavra", "karaokê", "letreiro na fala", "título que aparece quando eu falo", "texto sincronizado", "lettering", "palavra de impacto", "corrigir sincronia da legenda". Anchors captions, highlights, lettering and inserts to spoken-word ids with a signed offset, fits text by hierarchy, and never stacks competing text. Part of the Diretor de Edição set.
version: 0.1.0
---

# edicao-video-legenda-por-palavra — time to the word, not to the second

## Workflow
1. **Need word times.** The transcription service today returns `segmentos` only (no per-word times). Options, in order: (a) per-word output: the owner decided (2026-11-13) that our transcription service gets a `palavras[]` field in a separate slice, `segmentos[].palavras[{texto, inicio, fim, confianca}]`; when a result carries it, use it and low `confianca` feeds `legendas.incertas[]`; (b) a forced-alignment stage if the owner has cleared one (licence + tool = open item); (c) **degrade**: distribute words inside a segment by character weight and mark every anchor `inferido`, tell the user timing is approximate and keep highlights to 1–2 key words. Never present (c) as exact.
2. **Word ids.** Give every word an id (`w1…`) with `inicio_s/fim_s`. Anchors in the spec are `palavra_id` + `deslocamento_s` (small lead, default −0.1 s, preset-tunable), never absolute times. A sentence cut anchors to the END of the previous pause, not the recognizer's start time.
3. **Correct the ASR** against the glossary/roteiro (`correcoes_asr{}`); doubtful words → `legendas.incertas[]`.
4. **Caption groups:** 1–2 lines, meaning units, break at punctuation/breath; highlight mode from the preset: colour or pill on the active word. libass `\k` karaoke tags cover highlight without a browser; per-word pop/sweep motion needs an overlay renderer (optional, licence note in the spec doc §7).
5. **Lettering hierarchy:** one principal (the idea), optional apoio, optional cta; text must equal a transcript span or an approved string. Fit order when it does not fit: re-break → split into two beats → shorten (needs approval) → shrink last. Default `empilhar: false`: captions pause while lettering is on screen.
6. **Semantic colour** (neutro / negativo / positivo / cta) is a token the preset maps to its palette.
7. **Check:** caption/lettering boxes inside the safe zone across their whole animation (`edicao-video-zona-segura`); every on-screen word exists in the transcript or approved string; stills at 3 anchored moments for approval.

## Guardrails
Numbers on screen need `fonte` + `data` or `exemplo: true`. No overlay renderer is a dependency; if one is proposed, flag the licence (Remotion paid threshold; GSAP/HyperFrames legal review).

Spec: `legendas`, `letreiros[]`, `numeros[]`, `ancoras` in `KB § PATTERNS/media/video-edit-spec.md`.
