# CoreStudio headline prompt (engenharia reversa) — reconstructed template

> **Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.**
> The owner will refine and validate it later. Every section below carries the same status.

Source: `captures/xhr-2026-10-06/c14_reversa_{201774,201775,201755,201760,201765,201770}.json` (`GET /roadmaps/reversa/show/{id}`), plus `c13_suggested_get_*.json`, `b3_profile_viral_search_*.json`, `b2_library_result_*.json`, `c8_items_avatar.json` and the profile page in `captures/crawl-2026-10-06/pages/html__profile.html`. Read 2026-10-06.

**Tags:** **C** = confirmed in the captured data · **I** = inferred · **U** = unknown.

> **Privacy note (read first).** Only 201774 and 201775 belong to the owner (user 1667, workspace 1619). The other four ids belong to **two other CoreStudio customers** (user 1639 / workspace 1591 and user 603 / workspace 601). CoreStudio returned them to the owner's session, so `roadmaps/reversa/show/{id}` (and `headlines/suggested/get/{id}`) has no ownership check. Their persona text is not reproduced here. They are called **tenant B** (a pediatric ophthalmologist, 3 samples) and **tenant C** (an education mentor for women 50+, 1 sample). Their capture files are kept out of git (see `specs/xhr-to-fetch.md` §F).

---

## 0 · What a "suggested headline" row stores

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

| Field | Meaning | Tag |
| --- | --- | --- |
| `eng_reversa_result_id` | the source viral (library video) | C |
| `eng_reversa_flow_result_id` | the analysis-run record of that viral. The same column links a viral to its format classification in `library/result` (`engReversaFormatVideoRelation[].eng_reversa_flow_result_id`) | C (shared column) / I (one run produces both format and blueprint) |
| `eng_reversa_headline_text` | the **blueprint document** of that viral (§2), plus a trailing subject line in manual mode | C |
| `payload_headline_old_1` | **pass-1 user payload** = Núcleo line + `eng_reversa_headline_text` (§1) | C |
| `callback_headline_old_1` | pass-1 model output, a JSON string `{"headline_1", "headline_2"}` | C |
| `payload_headline` | pass-2 (revision) payload | **null in all 6 samples** (C) |
| `callback_headline` | pass-2 output | **identical to `callback_headline_old_1` in all 6** (C) |
| `number_headline` ∈ {1, 2} · `headline` | one model call yields two headlines; the server writes **two rows** with the same payload and callback, and `headline` = `headline_{number_headline}` (201774 → 1, 201775 → 2) | C |
| `mode` ∈ {`manual`, `automatic`} | `automatic` = daily suggestions; `manual` = generated on request (the Biblioteca "Gerar headline" wizard is the only manual path that writes suggested rows) | C values / I origin |
| `link_viral` | source post permalink | C |
| `roadmap_payload`, `roadmap_response`, `roadmap`, `roadmap_id` | roteiro attached to this headline (all null here) | C |
| `use_article`, `use_article_niche`, `search_id`, `search_text` | Roteiro Avançado sources (empty here) | C |
| `approved`, `admin_id`, `niche_id` | `approved=1` on all; `admin_id`, `niche_id` null | C |

**So there is no second pass for suggested headlines** in these samples: the "Payload Revisão / Callback Revisão" boxes of `#viewHeadlineFlowModal` would show null and a copy of pass 1. Whether form batches (`headlines/store`, state `in_gpt2`) run a real second pass: **U**.

---

## 1 · Pass 1 — user payload template

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

The stored payload is the **user message only**. It contains **no instructions about the task or the output format**, yet every output is a two-key JSON. So a **system prompt exists and was not captured** (§4). **C** (absence in payload) / **I** (system prompt).

```text
###NÚCLEO DE INFLUENCIA: {{NUCLEO_DE_INFLUENCIA}}

{{BLUEPRINT_DOCUMENT}}
```

- Literal prefix: `###NÚCLEO DE INFLUENCIA: ` (sic: "NÚCLEO" with accent, "INFLUENCIA" without, no space after `###`). **C**
- Separator: one blank line (`\n\n`) between the Núcleo and the blueprint document. **C**
- Nothing follows the blueprint document; the payload ends where `eng_reversa_headline_text` ends. **C** (6/6: `payload_headline_old_1 == prefix + eng_reversa_headline_text`).

### 1.1 `{{NUCLEO_DE_INFLUENCIA}}`

| Observation | Tag |
| --- | --- |
| For the owner, the text equals the **Meu Perfil `bio` field** word for word ("Eu sou Gilson Tangerino, especialista em negócios imobiliários. / Falo sobre … / Ajudo … / Porque …", 384 chars) | C (text equality) |
| The same four paragraphs are also the `### BIO` section of the owner's custom brain **Narrativa** (core 4192) | C (text equality) |
| It is **not** the content of the **Núcleo de Influência brain** (core 3081 / brain 8775), which is a different text ("### Perfil Profissional de Gilson Tangerino …", four sections built from the questionnaire). Same name, different object | C |
| Tenant B: 453 chars, the same four-paragraph "Eu sou / Falo sobre / Ajudo / Porque" shape. Tenant C: 4,256 chars, the shape plus a long "Narrativa central" (Origem, Inimigo, Mantra, Promessa, Arco emocional, Tom) | C |
| Most likely source: the profile `bio` (Meu Perfil warns that the bio is needed for suggestions, and tenant C's long text fits a free-text field). Copied from the Narrativa brain instead: not excluded | I |

### 1.2 `{{BLUEPRINT_DOCUMENT}}` = `eng_reversa_headline_text`

Two observed variants. Placeholders in `{{UPPER_SNAKE}}` are ours; slots in `{{UPPER-KEBAB}}` are CoreStudio's own variable slugs and appear literally in the payload.

**Variant A — automatic (4/4 samples, LF line endings, machine-generated I):**

```text
**HEADLINE ORIGINAL:**
{{HEADLINE_ORIGINAL}}

**BLUEPRINT (ENGENHARIA REVERSA):**
{{BLUEPRINT}}

**PROMPT EXPLICATIVO DE SUBSTITUIÇÃO:**

{{SUBSTITUICOES}}

**HEADLINES MODELADAS (3 nichos):**

1. ({{NICHO_1}}) {{HEADLINE_MODELADA_1}}
2. ({{NICHO_2}}) {{HEADLINE_MODELADA_2}}
3. ({{NICHO_3}}) {{HEADLINE_MODELADA_3}}

**CONFORMIDADE (STRICT):**

* Todas as substituições derivam exclusivamente dos conteúdos literais do extrator: {{SIM_NAO}}
* Número de linhas no PROMPT EXPLICATIVO = número de variáveis no BLUEPRINT: {{SIM_NAO_NA}}
* Headlines sem CTA/emojis, 8–18 palavras, nichos rotulados: {{SIM_NAO}}
```

**Variant B — manual (201774/201775, CRLF inside the body, which suggests text that went through a web form, I):**

```text
ENGENHARIA REVERSA E HEADLINE ORIGINAL OBRIGATÓRIA

**HEADLINE ORIGINAL:**
{{HEADLINE_ORIGINAL}}

**BLUEPRINT (ENGENHARIA REVERSA):**
{{BLUEPRINT}}

**PROMPT EXPLICATIVO DE SUBSTITUIÇÃO:**

{{SUBSTITUICOES}}

**HEADLINES MODELADAS (3 nichos):**

1. ({{NICHO_1}}) {{HEADLINE_MODELADA_1}}
2. ({{NICHO_2}}) {{HEADLINE_MODELADA_2}}
3. ({{NICHO_3}}) {{HEADLINE_MODELADA_3}}

{{ASSUNTO}}
```

Variant B differs by: the header line `ENGENHARIA REVERSA E HEADLINE ORIGINAL OBRIGATÓRIA`, **no CONFORMIDADE block**, and a trailing subject line (`maternidade` in the sample). **C**. `{{ASSUNTO}}` is the subject typed or picked in the Biblioteca wizard (`variable_contents[{variable_name:'ASSUNTOS_VIRAIS', content …}]` or its manual text). The owner has 0 approved viral topics, so it was probably typed. **I**

| Placeholder | Content | Tag |
| --- | --- | --- |
| `{{HEADLINE_ORIGINAL}}` | the viral's spoken hook, verbatim (9 to 135 words in the samples) | C |
| `{{BLUEPRINT}}` | `{{HEADLINE_ORIGINAL}}` with literal phrases replaced by `{{VARIABLE-SLUG}}` slots; everything else verbatim | C |
| `{{SUBSTITUICOES}}` | one bullet per slug: `* {{SLUG}} → Substitua por <definição contextual>; use apenas conteúdos literais fornecidos pelo extrator.` The definition is **rewritten per viral** (e.g. PESSOAS → "figuras parentais ou familiares reconhecidas pelo avatar"). With no slot: `*N/A — nenhuma variável identificada; headline permanece inalterada.*` | C |
| `{{NICHO_n}}`, `{{HEADLINE_MODELADA_n}}` | three worked examples in three other niches. In automatic mode, example 1 is the original copied verbatim (4/4) | C |
| `{{SIM_NAO}}`, `{{SIM_NAO_NA}}` | the generator's self-check | C |

---

## 2 · The upstream "blueprint" step (engenharia reversa) — inferred contract

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

The blueprint document is itself the output of an earlier LLM step run per viral. **Its prompt was not captured.** What its output shows about the rules it was given:

| Rule (from the CONFORMIDADE lines and the shape) | Followed in the samples? | Tag |
| --- | --- | --- |
| Slot only phrases that **an extractor** returned literally ("conteúdos literais fornecidos pelo extrator") | The extractor exists: `profile-viral-search` returns, per viral, `(variable slug, value)` pairs, and **641 of 643** values are literal substrings of that viral's hook | C (extractor) / I (that the blueprint step reads it) |
| Slots use the **DB variable slugs** | yes, 11 of 11 distinct slots are DB slugs or `GPT` (§3) | C |
| One substitution line per distinct slug | broken in 201774/201775: 8 distinct slugs, 7 lines (no line for `MOMENTO-DE-VIDA-DO-AVATAR`) | C |
| Modeled headlines: no CTA, no emoji, **8–18 words**, niche labelled | the word rule is broken in **every** sample (modeled headlines run 16–55 words) while the self-check says "Sim" | C |
| Unparseable hook → keep verbatim, `N/A` | 201765: a sung-syllable hook; blueprint = the hook, no slots, three nonsense "modeled" lines | C |

The self-check is therefore **not reliable**. Slot choices are also noisy: in 201775 the word for trust ("confiança") is slotted as `{{MEDOS-DO-AVATAR}}` and "o trabalho" as `{{INSTITUICOES-CONHECIDAS-PELO-AVATAR}}`. **C**

---

## 3 · Slots seen in blueprints, mapped by definition

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

Mapping rule: the slug string is the DB slug (identity of identifier), **and** the per-viral definition in `PROMPT EXPLICATIVO` must agree with the DB variable's meaning (label, classifier definition, extracted items). Name similarity alone never counts.

| Slot in blueprint | Samples | Definition given in the blueprint (abridged) | DB variable (`specs/variables-usage.md`) | Definitions agree? |
| --- | --- | --- | --- | --- |
| `PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR` | owner | figuras parentais ou familiares reconhecidas pelo avatar | 13 "Pessoas e personagens conhecidos pelo meu público" | yes (narrowed to family). **Not** the classifier spelling `PESSOAS-E-PERSONAGENS-CONHECIDOS-PELO-MEU-PUBLICO` |
| `DORES-TANGIVEIS-DO-AVATAR` | owner, B | dores/sintomas concretos percebidos pelo avatar | 17 "Dores do meu público" | yes |
| `DESEJOS-TANGIVEIS-DO-AVATAR` | owner, B | desejos concretos (ou saudades) do avatar | 18 "Desejos do meu público" | yes |
| `MEDOS-DO-AVATAR` | owner | medos específicos adquiridos na experiência familiar | 9 "Medos do meu público" | definition yes; the slotted word ("confiança") no |
| `CRENCAS-DO-AVATAR` | owner | crenças ou verdades percebidas pelo avatar | 8 "Crenças do meu público" (beliefs about the world) | yes. Not `CRENCAS-LIMITANTES-DO-AVATAR` (classifier-only, distinct) |
| `INSTITUICOES-CONHECIDAS-PELO-AVATAR` | owner | instituições conhecidas pelo avatar (contexto familiar ou profissional) | 14 "Instituições conhecidas pelo meu público" | definition yes; slotted word "o trabalho" is a stretch |
| `MOMENTO-DE-VIDA-DO-AVATAR` | owner | **no definition line** | 21 "Momentos de vida do meu público" | slotted word "infância" fits the label; no definition to compare |
| `CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR` | B, C | características demográficas do avatar | 16 "Características demográficas do meu público" | yes |
| `ITENS-CONHECIDOS-PELO-AVATAR` | C | itens reconhecíveis e familiares ao avatar | 15 "Itens conhecidos pelo meu público" | yes |
| `CRENCAS-DO-ESPECIALISTA` | B, C | crenças (ou afirmações) do especialista | 1 "Crenças e ideias que eu defendo" | yes. In a viral, "especialista" is the **original creator**; in generation the slot is refilled for the user (I) |
| `GPT` | owner | "verbos ou ações específicas … adaptando a novos cenários": a free slot the model fills | **no DB slug is known.** Global id 29 is *labelled* "GPT" but its slug and definition were never captured | **U — do not merge** with id 29 on the label alone |

Ten DB slugs (9 avatar: 8, 9, 13, 14, 15, 16, 17, 18, 21; 1 especialista: 1) plus `GPT`. None of the 7 classifier-only slugs (FRUSTRACOES, CRENCAS-LIMITANTES, INIMIGO-COMUM, MECANISMO-UNICO, PROMESSA-PRINCIPAL, PROVA-SOCIAL, NICHO-OU-MERCADO) appears. **C** (6 samples, 5 virals: a small sample).

---

## 4 · What is NOT in the payload (system prompt, unseen)

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

What the outputs show the hidden instructions must cover (**I**, from behaviour):

1. Return exactly `{"headline_1": "...", "headline_2": "..."}` (6/6; stored with PHP-style `\uXXXX` escapes).
2. Keep the blueprint's **syntax** (sentence frames, rhythm, contrasts) and refill the slots for the Núcleo's niche. Example: "Como {{PESSOAS…}} falava com você se tornou sua {{DORES…}}" became "Como seus pais falavam sobre comprar imóvel se tornou sua voz interior sobre dinheiro".
3. Fill slots with **the Núcleo's own vocabulary**, not with research items. The owner's outputs use "patrimônio", "gerações", "família" (all in the bio). Of the owner's 263 avatar research items, the only one found literally in the outputs is the single word "imóvel" (a pending item), which is also in the bio. So the blueprint's "use apenas conteúdos literais fornecidos pelo extrator" is **overridden** in generation. C (no literal item) / I (instruction).
4. Shorten long blueprints: 135-word original → 46–47-word outputs (owner). Short originals grow (21 → 29–30 words, B). There is no fixed length. C (counts)
5. Emoji: forbidden for modeled headlines, but one output (201765) starts with 🎵. So no emoji ban, or one that is ignored. C
6. The two headlines take different angles (e.g. B: "mãe" vs "pai"; owner: "pai/casa própria" vs "pais/comprar imóvel"). C

Research items, brains (other than the Núcleo text), formats, triggers, `thermometer` and Instagram data are **absent from the suggested-headline payload**. **C** for the payload; **U** for the system prompt.

---

## 5 · Output contract (pass 1)

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

```json
{"headline_1": "<string>", "headline_2": "<string>"}
```

Server side: stored verbatim in `callback_headline_old_1` (and copied to `callback_headline`), then split into two rows `number_headline = 1 | 2` with `headline = headline_{n}`. **C**. Status goes straight to `completed`. **C**

---

## 6 · Diff across the six samples

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

| | 201774 | 201775 | 201755 | 201760 | 201765 | 201770 |
| --- | --- | --- | --- | --- | --- | --- |
| tenant | owner | owner | C | B | B | B |
| `mode` | manual | manual | automatic | automatic | automatic | automatic |
| created (2026-10-04 UTC) | 19:22:30 | 19:22:39 | 19:11:14 | 19:14:39 | 19:14:45 | 19:15:00 |
| viral (`eng_reversa_result_id`) | 157591 | 157591 | 7145 | 7153 | 7148 | 7147 |
| `eng_reversa_flow_result_id` | 1012840 | 1012840 | 26908 | 26953 | 26936 | 26935 |
| `number_headline` | 1 | 2 | 2 | 2 | 1 | 2 |
| Núcleo length (chars) | 384 | 384 | 4,256 | 453 | 453 | 453 |
| header line `ENGENHARIA REVERSA…` | yes | yes | no | no | no | no |
| original hook (words) | 135 | 135 | 39 | 25 | 9 | 21 |
| slot occurrences / distinct slugs | 21 / 8 | 21 / 8 | 3 / 3 | 3 / 3 | 0 / 0 | 2 / 2 |
| substitution lines | 7 | 7 | 3 | 3 | N/A | 2 |
| modeled niches | Psicologia, Carreira, Educação | same | Comportamento, Nutrição, Moda | Psicologia, Fitness, Carreira | Música, Arte, Comédia | Autoestima, Fitness, Moda |
| modeled #1 = original verbatim | no | no | yes | yes | yes | yes |
| CONFORMIDADE block | no | no | yes | yes | yes (line 2 N/A) | yes |
| trailing subject | `maternidade` | `maternidade` | — | — | — | — |
| output words (h1 / h2) | 47 / 46 | 47 / 46 | 38 / 40 | 31 / 30 | 32 / 40 | 30 / 29 |
| pass 2 payload | null | null | null | null | null | null |

**Fixed in every sample:** the `###NÚCLEO DE INFLUENCIA: ` prefix, the four bold section headings, the bullet format of the substitution lines, the clause "use apenas conteúdos literais fornecidos pelo extrator", "3 nichos", the JSON output keys, the two-rows-per-call split.
**Varies:** the Núcleo (per tenant), the hook and its blueprint (per viral), the slot set, the per-viral slot definitions, the three modeled niches, the presence of the header / CONFORMIDADE / subject (per mode).

Automatic rows reuse **old virals** (ids 7145–7153, flow ids ~26.9k) for tenants B and C. The manual row uses a recent viral (157591, flow id 1,012,840). Daily suggestions therefore draw on the whole corpus, not only on recent posts. **I**

---

## 7 · Worked examples (abridged)

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

### 7.1 Owner, manual (201774 / 201775) — owner content quoted, creator content abridged

Input (payload, abridged):

```text
###NÚCLEO DE INFLUENCIA: Eu sou Gilson Tangerino, especialista em negócios imobiliários.
Falo sobre patrimônio, segurança familiar, qualidade de vida e decisões inteligentes no mercado imobiliário.
Ajudo famílias e investidores a construírem patrimônio com clareza, propósito e visão de longo prazo.
Porque comprar ou vender um imóvel não é apenas uma transação: é uma decisão que impacta gerações.

ENGENHARIA REVERSA E HEADLINE ORIGINAL OBRIGATÓRIA
**HEADLINE ORIGINAL:** "Como sua mãe falava com você se tornou sua voz interior. …" (135-word psychology hook, creator content, abridged)
**BLUEPRINT (ENGENHARIA REVERSA):** Como {{PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR}} falava com você se tornou sua {{DORES-TANGIVEIS-DO-AVATAR}}. … (21 slots, 8 slugs incl. {{GPT}} and {{MOMENTO-DE-VIDA-DO-AVATAR}})
**PROMPT EXPLICATIVO DE SUBSTITUIÇÃO:** 7 bullets
**HEADLINES MODELADAS (3 nichos):** (Psicologia) … (Carreira) … (Educação) …
maternidade
```

Output (verbatim, owner content):

```json
{"headline_1":"Como seu pai tratava a casa própria se tornou sua visão sobre patrimônio. Como sua mãe lidava com aluguel lhe mostrou como a segurança deveria ser, mesmo que não fosse estabilidade. Você não aprendeu apenas a morar, você aprendeu a valorizar ou temer decisões que impactam gerações.",
 "headline_2":"Como seus pais falavam sobre comprar imóvel se tornou sua voz interior sobre dinheiro. Como sua família tratava o patrimônio lhe ensinou o que fazer com o seu: arriscar, travar ou ficar em silêncio. Você pode mudar isso tomando decisões que protejam sua família por gerações."}
```

The output keeps 3 of the blueprint's 7 sentences, borrows "impacta gerações" from the bio, and does not use the subject "maternidade" visibly.

### 7.2 Tenant B, automatic (201760) — structure only, no tenant text

- Blueprint (creator hook, short form): `O recado vai pra você, {{CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR}}. {{CRENCAS-DO-ESPECIALISTA}} {{DORES-TANGIVEIS-DO-AVATAR}}.`
- Output shape: both headlines keep "O recado vai pra você, <papel do público>." + "<comportamento> não é <virtude>. É <problema do nicho> disfarçado de <falsa virtude>." The demographic slot becomes "mãe" / "pai" and the rest comes from the tenant's specialty.

---

## 8 · Open points for the owner (validation backlog)

Status: DRAFT — extracted from CoreStudio, not validated; do not use as final.

1. The system prompt of pass 1 (§4) is the missing half. The only remaining read-only source is the chat "Trace da IA" drawer, and it covers chat agents, not this job.
2. The blueprint-step prompt (§2) is not captured. Do we rebuild it from the contract above or design ours?
3. Do we keep the "Núcleo = bio" input, or feed our richer brain (Método Audience) instead?
4. Do we want the self-check block at all, given it is never true here?
5. Pass 2 (revision) never ran for suggested headlines. Do we want one?
