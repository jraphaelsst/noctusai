---
name: edicao-video-escolha-de-estilo
description: Use to pick a visual style/preset for an edit with at most two questions — triggers "qual estilo usar", "que formato combina", "me sugere um estilo", "quero algo mais dinâmico", "escolher preset", "estilo para imóvel", "tour do imóvel", "antes e depois". Maps material type and goal to one preset (max two options), explains the choice in one or two sentences, and pre-fills the roteiro skeleton; reads preset `quando_usar` and `frases_gatilho` from data. Part of the Diretor de Edição set.
version: 0.1.0
---

# edicao-video-escolha-de-estilo — two questions, one answer

## Workflow
1. **Never before the first win.** A user's first job is cleanup + captions (`edicao-video-corte-e-legenda`); styles come after the first approved result.
2. **Load presets from data** (`status != aposentado`): each has `quando_usar`, `frases_gatilho[]`, `aspectos`, `layouts`. If the user's own words match a `frases_gatilho`, propose it directly.
3. **Ask at most two questions**, with a recommendation shown inline:
   - Q1 material: "É você falando para a câmera, uma sequência de passos/telas, ou fotos/clipes do imóvel?"
   - Q2 goal: "O que a pessoa precisa fazer no final: pedir contato, salvar, ver o imóvel?"
   Stop at two; "tanto faz" twice ⇒ apply the recommendation visibly.
4. **Rule of thumb:** step-by-step speech or a list of items ⇒ card-based preset; otherwise talking-head base + a few inserts. Real-estate seeds to offer as data (ours, untested until first approval): tour do imóvel, corretor falando, antes e depois, "3 motivos para comprar", guia do bairro.
5. **Answer** in 1–2 sentences ("Recomendo X porque… custa mais ~N min de render") + the roteiro skeleton the preset expects. Mark presets `nao_testado` honestly.
6. **Style from a link/video** → hand to `edicao-video-referencia-para-preset`.
7. Record the choice in `spec.preset {id, versao}`; the chosen version is frozen in the job.

## Guardrails
Never copy a creator's distinctive look or brand; "inspired by" = structure, rhythm, layout. If a user re-routes your suggestion by hand, note the phrase as a candidate `frases_gatilho` for the preset (a proposal; promoting it is a versioned change).

Spec: `preset` in `KB § PATTERNS/media/video-edit-spec.md` §5.
