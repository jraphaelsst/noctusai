# CoreStudio roteiro (Roteiro Avançado) — params contract and what is missing

> **Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.**
> **No roteiro prompt text was captured.** This file documents the input contract and the behaviour seen, so a prompt can be designed and validated later.

Sources: `captures/xhr-2026-10-06/c16_roadmap_41429.json` (`GET /roadmaps/view/41429`), `captures/raw/corestudio-data.json` → `roteiros.41428` (same endpoint, 2026-10-05), `c15_adv_roadmap_201775.json`, `c14_reversa_*.json` (roteiro fields of suggested headlines). All roteiros are the owner's.

**Tags:** **C** confirmed · **I** inferred · **U** unknown.

---

## 1 · Why there is no prompt

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

| Where a prompt could have been | What came back | Tag |
| --- | --- | --- |
| `user_roadmaps.payload` (41428, 41429) | `""` (empty string) in both | C |
| `eng_reversa_headlines.roadmap_payload` / `roadmap_response` (6 suggested headlines) | `null`: no roteiro was ever made from them | C |
| `GET headlines/suggested/advanced-roadmap/show/{id}?headline_id=201775` | `{"success":false,"message":"Roteiro avançado ainda não foi processado", "use_article":false, …}` | C |
| `GET headlines/suggested/view/{id}` (`xhr-to-fetch.md` #1, assumed to hold headline payloads) | `{"success":false,"message":"Roteiro ainda não foi processado","status":"completed","use_article":0}`: it is a **roteiro status** endpoint | C |

The roteiro prompt is therefore not stored where the owner can read it, or is stored only after a run through a path that fills `payload` (legacy path A, **U**). The chat "Trace da IA" drawer covers the chat ROTEIRO agent, not this job.

---

## 2 · Params contract (Roteiro Avançado, `save_to = user_roadmaps`)

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

`params` as stored on the roteiro row (union of 41428 and 41429). All values are strings unless noted. **C**

| Param | 41428 | 41429 | Meaning |
| --- | --- | --- | --- |
| `headline_text` | the headline (with final ".") | same headline (without ".") | headline to develop |
| `ai_provider` | `claude` | `claude` | model family; the modal's default (C) |
| `mode` | `steps` | `steps` | the modal's two-stage flow ("passa por 2 etapas de análise") |
| `save_to` | `user_roadmaps` | `user_roadmaps` | target table (`eng_reversa_headlines` for a suggested headline) |
| `observations` | the owner's own draft script | the same draft, with an `ABERTURA DO REELS:` label added | "Instruções" free text; here a full draft labelled ABERTURA / DESENVOLVIMENTO / VIRADA DO VÍDEO / FECHAMENTO |
| `roadmap_source_type` | `none` | `serper` | research source: `none`, `links` (≤ 4) or `serper` |
| `roadmap_use_pubmed` | `0` | `1` | restrict Serper to PubMed |
| `serper_search_in_portuguese` | — | `1` | language toggle of the search plan |
| `serper_query` | — | `emotion that takes over during the purchasing process site:pubmed.ncbi.nlm.nih.gov` | the query the planner LLM wrote (in English despite the Portuguese toggle) |
| `source_links` (list) | — | 1 PubMed URL | the links the user ticked from the search results |
| `viral_video_id` | — | `115244` | the viral used as the roteiro's **structure reference** |
| `duration_minutes` | `auto` | `auto` | target length |
| `is_reprocess` | `0` | `0` | reprocess flag |

Row-level fields next to `params`: `name` ("Roteiro Avancado: <headline without accents>"), `headline`, `observations`, `brain_id` (null in both: no brain picked), `viral_id`, `viral_video{id, title, description, plays, likes}`, `roadmap_gpt` (the output), `roadmap_liked` (41428 = 2, 41429 = 0), `payload` (empty), `search_id` (`serper-<epoch>-<hex>`), `search_text` (the fetched source text, 9,124 chars for one PubMed page, with the Serper snippet first and then "Conteúdo extraído:"). **C**

Not in `params`, but expected from the modal: `core_id` (brain, empty here), headline id. **C** (modal) / absent here.

---

## 3 · Behaviour seen (a natural A/B: same headline and draft)

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

| | 41428 (no viral, no source) | 41429 (viral 115244 + 1 PubMed page) | Tag |
| --- | --- | --- | --- |
| Length | 391 words | 307 words | C |
| Opening | the headline verbatim, then "Salve esse vídeo, pois…" | same | C |
| Body | third-person founder story ("Gilson Tangerino descobriu isso…"), with **invented statistics** ("67% … se arrependem", "mais de 3.000 famílias", "menos de 3%") | second-person demonstration that copies the **viral's device**: the viral says "Isso daqui é você no ambiente certo … Esse é você no ambiente errado"; the roteiro says "Isso aqui é você tomando decisão com equilíbrio … Esse é você decidindo só com emoção" | C |
| Use of the draft | ideas kept (family imagining the house, 30 years, emotion vs reason), wording rewritten | same | C |
| Use of the PubMed source | — | none visible: the paper (purchase intention for health products on WeChat) is off-topic and no fact from it appears | C |
| CTAs | "Salve esse vídeo…" + "Compartilhe com aquela pessoa que está pensando em comprar um imóvel, você pode salvar o patrimônio dela." | same two CTAs | C |
| Closing | the same three-sentence self-presentation ("Eu sou Gilson Tangerino, especialista no mercado imobiliário. Eu acredito que imóveis são ferramentas para construir segurança, liberdade e legado. …") | identical | C |

Inferences:

1. `viral_video_id` makes the generator **model the viral's rhetorical skeleton** (its transcript reaches the prompt). **I** (strong)
2. Roteiro beats follow CoreStudio's fixed sequence: Headline → CTA de Salvar → body → virada → CTA de Compartilhar → Apresentação Magnética. This matches the beat names seen in chat and in the "Narrativa" brain. **I**
3. The closing self-presentation is fixed per user. Its source is **U**: it is **not** the Meu Perfil `presentation_magnetic` field, **not** the "### APRESENTAÇÃO MAGNÉTICA" section of the Narrativa brain (4192), and **not** the bio. A close variant appears in the owner's own earlier scripts pasted into chat. A brain or a memory is plausible.
4. With no source, the model invents numbers (41428). With an off-topic source, it ignores the source (41429). Nothing checks facts. **C** behaviour / **I** cause

---

## 4 · What is missing to write the prompt

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

1. The system/user prompt of the Roteiro Avançado `store` call (`mode: steps`) and of its first stage (the search planner that wrote `serper_query`).
2. How the viral transcript, brain (`core_id`), `duration_minutes` and `observations` are framed in the prompt.
3. Where the fixed self-presentation and the CTAs come from (profile `ctas` is empty for the owner).
4. The legacy path A prompt ("1. Pesquisando → 2. Extraindo Núcleo → 3. Método"), the only path whose `payload` might be filled. Reading it would need an existing legacy roteiro (none on this account).

Our own roteiro prompt should be designed from the Método Audience (`products/social-wiring/backend/app/modules/media_creation/prompts/methodology.py`) and validated by the owner. This file is input to that design, not a spec of it.
