---
name: edicao-video-referencia-para-preset
description: Use to turn a reference video into a reusable preset draft — triggers "faz no estilo desse vídeo", "copia o estilo", "estudar essa referência", "salvar meu estilo", "extrair o estilo", "transformar em preset", "analisa esse vídeo e cria um estilo". Studies the reference in analysis-only mode (frames, rhythm, layout, caption behaviour), produces a three-column what-works / our-way / never-use study, a preset draft with typed rules, then tests, adjusts and promotes only by explicit versioned step. Part of the Diretor de Edição set.
version: 0.1.0
---

# edicao-video-referencia-para-preset — reference → study → preset (versioned)

## Workflow
1. **Rights first.** Only a reference the user supplied or a link they own/are allowed to analyse. Record origin. A reference is read for structure, never copied: no text, no brand identity, no distinctive art, no music.
2. **Analysis-only pass (no edits).** Extract ~24 frames evenly + frames at every scene change; transcript with timing (`segmentos`); measure: words/min, pause stats, cut cadence, caption position/lines/highlight, graphic coverage %, layout regions in % of frame, palette (dominant colours with roles and approximate ratios), type character (not font names unless licensed), motion timing, sound use. Every finding carries evidence `observado | inferido | nao_verificavel`.
3. **Three-column study:** *o que funciona* · *como faríamos* (our version in our tokens) · *nunca usar* (their brand, copy, art, assets). Show it to the user; **human corrections go into `correcoes_humanas[]`; the corrected study, not the raw one, feeds the draft.**
4. **Preset draft** (data, `status: nao_testado`, version 1): `quando_usar`, `frases_gatilho`, aspects, layouts (named regions in %), caption rules, tokens, pacing by `ritmo`, audio, `checklist_revisao`. Clarifying answers the user gives ("nunca cortar no meio da palavra", "nada sobre o rosto") become typed `regras[]` with `origem: pergunta_respondida`, not chat memory. Offer a palette from the user's own footage/brand as an alternative to the reference's.
5. **Test on one real job.** Stills first (3 frames; or frames + short excerpt for talking heads), then motion. Adjust in plain pt-BR → revision rows.
6. **Save = explicit and versioned.** Ask: "Quer salvar estes ajustes no estilo?" Yes ⇒ new version, `historico[]` entry, then **re-render the preset's golden stills and diff before it goes live**; otherwise `escopo: job`. Expect convergence in 2–3 jobs; the metric is revisions per approved job per version.
7. Output: study file, preset YAML, and the first test stills. Never register the preset as published/used until its first approved render.

## Guardrails
Third-party style packs, courses and kits are study-only: no files, prompts, code, names of their styles or bundled assets are copied, installed or run. Preset names are ours and describe the format, not their look.

Spec: `KB § PATTERNS/media/video-edit-spec.md` §5.
