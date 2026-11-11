# S4 — endpoint contract: blind labelling + agreement read

> Authored once (noc-contract-first); the backend (`products/assistant/backend/app/routers/classificacao_router.py`) and the page
> (`products/assistant/frontend/src/pages/avaliacao/`) are both built to it. Router fixes the envelope: **bare bodies**, no `{data}`.
> Tier of every route: `org`, org ADMIN only (seed `make_organ_auth(...).admin`). Unauthenticated -> 401, non-admin member -> 403.

## Endpoints

| Route | Request | Response (200) | Errors |
|---|---|---|---|
| `GET /api/classificacao/amostra?por_estrato=1..100&modo=cego` (S3, **one change**) | — | `{modo, prompt_version, modelo, itens:[{intake_id, output_id, texto, recebida_em}]}` — no verdict, confidence, reason or stratum | 503 prompt registry down |
| `POST /api/classificacao/rotulos` | `{intake_id: uuid, output_id: uuid, rotulo: agendamento\|nao_agendamento\|nao_sei, rodada: int 1..1000}`, extra fields rejected | `{evento_id, repetido, intake_id, output_id, rotulo, rodada}` | 404 the output is not a classification of that intake row in this org · 422 shape |
| `GET /api/classificacao/rotulos/progresso` | — | `{rotuladas, por_rotulo:{agendamento, nao_agendamento, nao_sei}}` (the caller's LATEST label per message) | — |
| `GET /api/classificacao/rotulos/concordancia` | — | `{grupos:[{prompt_version, modelo, total, nao_sei, decididos, concordam, concordancia\|null, matriz:{agendamento\|outro:{agendamento, nao_agendamento, nao_sei}}}]}` | — |

**The one S3 change:** in `modo=cego` the sample now omits messages the caller already labelled (any round). `modo=revelado` is unchanged.

## Stateful legs (the label POST)
- **Side effect / state after:** one row in `assistant.ai_feedback_events` (seed organ seam). After a 200 the (labeler, intake, rodada) event exists; the message no longer appears in the caller's blind sample.
- **Append-only:** no PUT/PATCH/DELETE route; a DB trigger refuses UPDATE/DELETE. **Relabel = POST with `rodada` = last + 1**; the highest rodada is the effective label. Same (labeler, intake, rodada) twice = no-op, `repetido: true`, no second row.
- **Strictness:** unknown fields -> 422 (`extra=forbid`).
- **Error taxonomy:** 401 no session · 403 not admin ("restrito a administradores") · 404 foreign/mismatched ids ("Mensagem não encontrada para esta organização.") · 422 invalid enum/rodada.
- **Deprecations:** none.

## Agreement definition (written)
Model verdict `agendamento|outro`; owner label `agendamento|nao_agendamento|nao_sei`. Agree = (agendamento, agendamento) or (outro, nao_agendamento). `nao_sei` is counted and shown but is outside the denominator (`decididos = total - nao_sei`); `concordancia = concordam / decididos`, `null` (never 0) when none decided. One human label scores EVERY classification of that message (every prompt_version/model that classified it); the latest round per labeler counts.

## Records / Metrics
- **Records:** `ai_feedback_events` — dated, append-only; who (labeler_id), what (subject_id = intake row, output_id = the classification shown blind), the enum label, the round. No message text, no phone, no chat ref.
- **Metrics enabled (derived in one place, `resumo_rotulos` + `app/shadow/avaliacao.py`):** agreement %, confusion matrix, `nao_sei` rate, per prompt_version/model; labels per labeler (progress).

## LGPD
The page shows third-party message text to an admin: a permanent notice ("conteúdo de terceiros, uso restrito à avaliação"); no route or hook logs message text; the label write carries ids only; text is never put in a URL, storage or query key.
