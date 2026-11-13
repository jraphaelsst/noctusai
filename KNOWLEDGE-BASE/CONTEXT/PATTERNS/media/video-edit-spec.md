# Video edit spec — the contract between the Diretor de Edição and the render worker

> **Status: v0 draft (2026-11-13), `.md`-agent phase.** The agent `.claude/agents/diretor-de-edicao.md` and the skills `.claude/skills/edicao-video-*/` emit and consume this schema today as JSON files in the job folder. When the agent moves into the agents product (consumed via API), this document is the contract: **the agent emits a spec, a deterministic worker renders it; the agent never hand-writes render code per job.** Field names are pt-BR (they surface in the review UI and in events); nothing here is copied from third-party material (see Sources).

## 1 · Why a spec

- Reproducible: same spec + same source hashes ⇒ same render. A revision is a spec delta, not a new improvisation.
- Reviewable: the approval UI shows the spec's cut list, scene map and sample, not a transcript of chat.
- Movable: the same JSON works from a Claude Code session (ffmpeg on the laptop) and from the future `video.*` job family (`CORESTUDIO-STRUCTURE.md` §3, a sandboxed worker per edit).
- Measurable: every state change is an append-only event (EOA); every revision is a row. → `KB § PATTERNS/architect/measurement-by-design.md` · `KB § PATTERNS/architect/event-oriented-architecture.md`

## 2 · Where it plugs into CoreStudio (verified against `CORESTUDIO-STRUCTURE.md` §1.2, §3 on `origin/feat/corestudio-structure`)

One post, three independent axes. The spec touches only the first and hints at the other two:

| Axis | Lives on | Spec's relation |
|---|---|---|
| Tipo de mídia (`imagem` / `video`) | `cs_post_assets.tipo_midia`, one row per file, `ordem`, `versao` | each `saida[]` entry becomes ONE `cs_post_assets` row (`tipo_midia = video`, `versao` = job output version, `proporcao`, `duracao_s`, `storage_path` read from the file, never trusted from the spec) |
| Formato / posicionamento (`feed` `carrossel` `reel` `story` `short` `video_longo`) | `cs_post_publicacoes.formato` (per target) | the spec carries only `saida[].destino_sugerido` as a hint for aspect/safe-zone/duration defaults; the validity matrix (`post_formatos.py`, data) decides what is allowed, and scheduling picks the real target |
| Rede | `cs_post_publicacoes.rede` | same: hint only (drives the safe-zone table); never written by the editor |

Rules that follow: the editor never writes `cs_post_publicacoes` and never publishes; a finished render creates a new asset **version** in `midia_em_producao → midia_pronta` (T6); approval and `agendado` belong to the CoreStudio approval flow (T8). The spec's `modo_aprovacao` governs only the approvals INSIDE the edit job (plan, sample); it never replaces the post's media approval.

Worker seams used: job queue with retry (`domain.jobs`, family `video.editar | video.preview | video.export`), one throwaway sandbox per job, SSE progress (`fase`, `pct`, `eta`). Transcription is the existing server (`noctus.transcription.*`): **one file ≤ 600 s and ≤ 150 MB per call; longer media is chunked by the caller** (skill `edicao-video-preparo-de-midia` has the recipe) and the timestamps re-offset. Today the service returns text and optional `segmentos` (`start`,`end`,`text`); **it does not return per-word timestamps** (see §8, open item 1).

## 3 · The spec (top level)

```jsonc
{
  "spec_versao": "0.1",
  "job": {
    "id": "…", "org_id": "…", "post_id": "…",         // ids come from the harness; the agent never invents them
    "objetivo": "texto livre: o que o vídeo precisa conseguir",
    "ritmo": "natural | enxuto | acelerado",           // preference, per user, confirmed (see §6)
    "modo_aprovacao": "previa | criterios",
    "estimativa": { "min_render": 0, "custo_usd": 0 }  // estimate BEFORE; actuals go to events
  },
  "fontes": [ { "id","path","sha256","papel":"fala|prova|demonstracao|referencia_estilo|ilustracao|trilha",
                "origem","direitos":"proprio|licenciado|terceiro_nao_liberado|desconhecido",
                "normalizacao":{ "hdr_para_sdr":bool,"vfr_para_cfr":bool,"rotacao":0,"nota":"…" },
                "fps","largura","altura","duracao_s","intervalo_origem":[0,0] } ],
  "preset": { "id":"base-limpa", "versao":3 },         // §5; the version used is frozen into the job
  "saida": [ { "id":"s1","largura":1080,"altura":1920,"fps":30,"codec":"h264_aac",
               "destino_sugerido":{ "rede":"instagram","formato":"reel" },   // hint only
               "duracao_alvo_s":[20,45] } ],
  "cortes": [ { "de_s":0,"ate_s":0,"motivo":"silencio|repeticao|erro_de_fala|enchimento|ruido|pedido",
                "take_mantido":"…","evidencia":"observado|inferido" } ],
  "legendas": { "modo":"frase|palavra","grupos":[{"inicio_s":0,"fim_s":0,"texto":"…","palavras":[{"t":"…","inicio_s":0,"fim_s":0}]}],
                "destaque":"cor|pilula|nenhum","faixa":{"y_pct":[0,0]},"glossario":["termos"],"incertas":["palavra?"] },
  "cenas": [ { "id","trecho":{"de_s":0,"ate_s":0},"entender":"…","olhar":"…","muda":"…","permanece":"…",
               "layout":"nome-do-preset","entrada_s":0,"permanencia_s":0,"saida_s":0 } ],
  "letreiros": [ { "texto":"= trecho da fala ou string aprovada","funcao":"principal|apoio|cta","regiao":{"x_pct":[0,0],"y_pct":[0,0]},
                   "ancora":{"palavra_id":"…","deslocamento_s":-0.1},"empilhar":false } ],
  "insercoes": [ { "id","tipo":"imagem|video|cartao|logo|banner","fonte_id":"…","ancora":{"palavra_id":"…","deslocamento_s":0},
                   "duracao_s":0,"rotulo":"ilustrativo|exemplo|null","direitos":"…" } ],
  "audio": { "loudness":{"alvo_lufs":-14,"pico_dbtp":-1.5},"trilha":{"fonte_id":"…","duck_db":-10},
             "sfx":[{"fonte_id":"…","ancora":{…},"nivel_db":0}],"silencio":[{"de_s":0,"ate_s":0}] },
  "gancho": { "variacao_id":"…","texto_0s":"…","verificacoes":{"quadro_0_0s":"nao_medido","quadro_0_5s":"nao_medido","fala_ate_1_5s":"nao_medido"} },
  "zona_segura": { "tabela_ref":"zonas-por-rede@v1","violacoes":[] },
  "numeros": [ { "valor":"…","unidade":"…","fonte":"…","data":"YYYY-MM-DD","exemplo":false } ],
  "enquadramento": { "regioes_protegidas":[],"suavizacao":"…","reset_por_take":true },
  "amostra": { "tipo":"stills_3 | stills_mais_trecho","n_quadros":3,"intervalo_s":[0,0],"escolhida_por":"dificuldade" },
  "restricoes": { "sem_fala_nova":true,"sem_numero_novo":true,"musica_sfx_autorizados":false,"teto_servicos_usd":0 },
  "variacao": { "base_id":"…","variavel":"gancho|titulo|take_de_abertura","hipotese":"…","resultado":"nao_medido" },
  "proveniencia": { "alteracoes":[],"preexistente":[],"nao_demonstra":[] },      // filled by the worker
  "verificacao": { "duracao_s":0,"quadros":0,"largura":0,"altura":0,"audio_lufs":0,"hash_origem_ok":true }  // measured, never asserted
}
```

Conventions:
- **Every claim by the agent carries an evidence level:** `observado` (measured/seen) · `inferido` · `nao_verificavel` · `proposto`. A cut list row, a QA finding and an assumption all carry it. Never label an internal check as the user's approval.
- **Times are seconds on the SOURCE timeline** inside `cortes`/`cenas`/`legendas.grupos`; the compiler produces the output timeline. Anchors use `palavra_id` + signed `deslocamento_s`, never absolute timestamps (survives re-cuts).
- **Text on screen** (`letreiros`, cards) must equal a transcript span or a string the owner approved; `numeros[]` without `fonte`+`data` is refused unless `exemplo: true`, which prints an "valores de exemplo" note.
- **Layers:** a revision row carries `camada` (`base | legendas | letreiros | insercoes | audio`) so the worker re-renders only the layer that changed (cache key = source sha256 + layer inputs).
- **Recompose, never shrink:** a new aspect re-lays-out the scenes (same spec, new `saida[]` entry), it does not squeeze the old frame.

## 4 · Revisions and events (measurement-by-design)

A revision is a typed row, not chat. `revisoes[]`:

```jsonc
{ "id":"r7","trecho_ref":"cena:c3 | palavra:w120-w131","propriedade":"legendas.faixa.y_pct | cortes | audio.trilha.duck_db …",
  "delta":"+20% | -0.1s | remover","congelar":["cena:c1","cena:c2"],"camada":"legendas",
  "escopo":"job | preset | marca","origem":"usuario | verificacao_automatica",
  "promovido_em":null,"verificado_contra_golden":false }
```
`escopo = preset|marca` means "save this into the preset" (§5); default is `job`. The worker proves a freeze with an unchanged-frame count ("N quadros alterados, M idênticos").

Proposed event names (EOA, append-only, same transaction as the state change; they extend `cs_post_eventos`/job events once S1 lands — not yet implemented): `edicao_iniciada` · `midia_normalizada` · `plano_de_cortes_aprovado` · `amostra_gerada` · `amostra_aprovada` (with `origem: usuario|criterios`) · `revisao_aplicada` · `preset_ajuste_promovido` · `preset_versao_criada` · `golden_regressao_falhou` · `edicao_concluida` (with `custo_estimado` vs `custo_real`, `min_render`). Outcomes are enums; nothing is inferred from silence.

Metrics these enable: revisions per approved job **per preset version** (a preset that does not converge in 2–3 jobs is flagged for redesign) · stills-gate rejections per version · first-pass approval rate by preset · cost and render minutes per approved piece · hook-check failures by preset · safe-zone violations caught before vs after the human saw them · time from upload to first approved sample · hook variant (`variacao`) vs performance, joined later from Redes Sociais metrics (`resultado: nao_medido` until then).

## 5 · Presets are data

A preset is a versioned row (YAML/JSON), never code, never in a prompt. Seeds start `status: nao_testado` until their first approved render.

```yaml
id: base-limpa
versao: 3
status: nao_testado | em_uso | aposentado
nome: "Base limpa"
quando_usar: "fala direta para a câmera; só limpar e legendar"
frases_gatilho: ["tira os silêncios", "só legenda", "deixa limpo"]
aspectos: ["9:16", "4:5", "1:1"]
ritmo:  { natural: {pausa_max_s: 0.6}, enxuto: {pausa_max_s: 0.4}, acelerado: {pausa_max_s: 0.25} }
legendas: { modo: palavra, linhas: [1, 2], destaque: pilula, faixa_y_pct: [66, 76] }
layouts: { cheio: {...regiões em % do quadro...} }
tokens: { cores: {...com papéis...}, tipografia: {...}, movimento: {...} }
audio: { lufs: -14, pico_dbtp: -1.5, trilha_duck_db: -10, sfx: nenhum }
checklist_revisao: ["texto dentro da zona segura", "legenda == fala", "primeiro quadro legível"]
regras:   # typed; the only place a learning lives
  - { id: g1, texto: "nunca cortar no meio da palavra", origem: pergunta_respondida }
  - { id: g2, texto: "legenda abaixo do peito, fora do rosto", origem: ajuste_promovido, revisao_origem: "job-41/r7" }
armadilhas: [ { id: a1, texto: "HDR do iPhone estoura o render", resolvido_por: "edicao-video-preparo-de-midia" } ]
golden_stills: [ "storage://…/job-38/amostra-1.png" ]
historico: [ { versao: 2, mudanca: "…", job_origem: "job-41", revisoes: ["r7"] } ]
```

**Promotion is an explicit, versioned step.** Flow: user adjusts in plain pt-BR → the agent converts to revision rows → user approves the preview → the agent ASKS once: "Quer salvar este ajuste no estilo (para os próximos vídeos) ou só neste vídeo?" Only on "salvar no estilo": (1) append a typed `regras[]` entry with `origem: ajuste_promovido`; (2) create `versao+1` (never edit in place), `historico[]` gets the source job + revision ids; (3) **regression guard:** re-render the preset's `golden_stills` (the approval frames of the last approved jobs) with the new version and diff them; any unexpected change blocks the promotion until the user sees both; (4) emit `preset_ajuste_promovido`. A one-off fix stays `escopo: job`. An approved job records the preset version it used; later versions never rewrite old jobs.

Preferences (pace, approval mode, "nada sobre o rosto") are per-user/org overrides on top of the preset, set only from an explicit answer, never inferred; a value is surfaced as "recomendado, igual ao último vídeo" and still asked once per job.

## 6 · Defaults and open choices (owner to confirm; see the agent's open questions)

Captions on (burned), last take wins, natural pause compression, −14 LUFS / −1.5 dBTP, 9:16, no music/SFX unless authorized, no third-party footage, no new speech/offers/numbers. `ritmo` is a per-user preference (three levels) plus an optional playback-speed hint 1.0–1.2×; first job asks, later jobs recommend. `modo_aprovacao` default proposed: `previa` for a user's first jobs and for any preset still `nao_testado`; `criterios` only after the preset has approved renders.

## 7 · Optional render stacks (the worker owns cut/audio/grade/master; overlays are a seam)

| Tier | What | Notes |
|---|---|---|
| Base (default) | ffmpeg + libass (cuts, concat, ASS captions with word highlight, simple overlays, loudness, ducking, reframe, stills for QA) | deterministic, no browser; `edicao-video-*` skills target this first |
| Overlay (optional, behind a named seam) | headless-browser renderer producing alpha overlay clips, composited by ffmpeg | candidates: Remotion (React; **paid company licence above a small-team threshold: legal review before use**) · HyperFrames (Apache-2.0; its GSAP dependency is not OSI: **legal review before use**; young project, vendor telemetry must be off). Neither is a dependency today |
| ML data artefacts | face/pose landmarks (reframe), matte/alpha, ASR alignment | each its own cached stage keyed by source hash |

Third-party skill packs studied have **no licence file: study-only, nothing is vendored, installed or executed.**

## 8 · Open items (not decided here)

1. **Word-level timestamps.** The transcription service returns `segmentos` only. Word-anchored captions/letterings need either per-word output from the service (tooling ask, the cheapest) or a forced-alignment stage (licence check). Until then the skill degrades to segment-level and says so in the report.
2. Safe-zone numbers per rede × formato are `nao_verificado` in the skill; they must come from the official docs via the validity matrix (S1), not from memory.
3. Event names in §4 are proposals; they bind when the job events table lands.

## Sources

Study notes (outside git, third-party reference only, paraphrased, nothing copied): `_private-studies/{edicao-ia-aulao,maquina-edicao-ia,caixa-preta-ia,aprendavfx}/STUDY-*.md`. Verified against: the CoreStudio structure spec (file CORESTUDIO-STRUCTURE.md on branch `feat/corestudio-structure`, not yet on dev) §1.2, §3; `mcp/noctusai/tools/noctus/transcription/client.py`; `seed/lib/backend/noctusai_lib/integrations/transcription/validation.py` (`max_duration_s = 600`).

→ Composes with `KB § PATTERNS/common/agent-context-architecture.md` · `KB § GUIDES/agent-creation.md` (when the agent moves to the agents product).
