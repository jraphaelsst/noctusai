# Tours Virtuais — API contract (backend ↔ frontend), draft v0 2026-11-07

Contract-first (skill `noc-contract-first`): BE and FE both build to this file; each side's tests assert these shapes. Status: **draft, not approved** — the FE half is re-cut against the `product-designer` mockups before any FE slice. Raw-dict responses (no `{"data":…}` envelope), the card convention used by `antigos-proprietarios-CONTRACT.md`. Request bodies are `StrictHttpModel` (`extra=forbid` ⇒ unknown field = 422). Times ISO-8601 UTC. Angles in radians (D-T5).

Error body everywhere: `{"detail": "<pt-BR message>", "code": "<snake_code>", ...extra}`.

## 0 · Common

**Versioned writes (D-T2).** Every PATCH/DELETE on a versioned row carries `"versao": <int>` in the body (DELETE: query `?versao=`). Mismatch ⇒ **409** `{"code":"versao_conflito","atual": <current row>}`; the FE replaces its copy with `atual` and shows "Alterado por outra pessoa — revise e repita". Success returns the row with `versao + 1`. Reorder and tour-level fields use the tour's `versao`.

**Shapes**

```jsonc
// TourResumo (list item)
{"id":"uuid","titulo":"…","codigo_imovel":"ONE1234","status":"rascunho|concluido|removido","publicado":false,
 "fotos":7,"fotos_processando":0,"thumb_url":"https://…signed…|null","visitas_30d":0,"leads_30d":0,
 "criado_por":{"id":"uuid","nome":"…|null"},"updated_at":"…","versao":3}

// Foto
{"id":"uuid","ordem":0,"nome":"Sala","status":"aguardando_envio|processando|pronta|erro","erro_codigo":null,
 "proporcao_ok":true,"largura":7680,"altura":3840,"vista_inicial":{"yaw":0.0,"pitch":0.0},
 "urls":{"web":"…|null","thumb":"…|null","preview":"…|null"},   // signed, TTL 1 h, null until pronta
 "duplicada_de":null,"versao":1}

// Conexao (one per pair)
{"id":"uuid","foto_a_id":"uuid","foto_b_id":"uuid","pin_a":{"yaw":1.2,"pitch":-0.1},"pin_b":{"yaw":-2.0,"pitch":-0.05},
 "a_para_b_vista_inicial":false,"b_para_a_vista_inicial":false,"versao":1}

// PontoInfo
{"id":"uuid","foto_id":"uuid","tipo":"texto|link","titulo":"…","conteudo":"…","posicao":{"yaw":0.3,"pitch":0.1},"versao":1}

// Tour (detail)
{ ...TourResumo, "segmento":"imobiliario","navegacao_modo":"pins","foto_inicial_id":"uuid|null",
  "contato":{"whatsapp":"5511…|null","whatsapp_efetivo":"5511…|null","nome":"…|null"},
  "lead_form":{"ativo":false,"campos":{"nome":true,"telefone":true,"email":false},"gatilho_pct":null},
  "autorotacao":{"ativa":true,"velocidade":1.0,"avancar_ao_completar":false},"marca_id":"uuid|null",
  "imovel":{"codigo":"ONE1234","titulo":"…|null","bairro":"…|null","cidade":"…|null","no_catalogo":true},
  "fotos":[Foto…],"conexoes":[Conexao…],"pontos_info":[PontoInfo…],
  "link":{"url":"https://<host>/t/<token>","criado_em":"…"} | null,
  "pendencias":[{"codigo":"sem_fotos|foto_processando|foto_sem_nome|foto_isolada|sem_contato","foto_id":"uuid|null"}] }
```
`fotos` in TourResumo is a count; in Tour it is the array. `pendencias` are warnings computed server-side; none blocks publishing except `sem_fotos` and `foto_processando` (Q: confirm).

## 1 · Editor routes — tier `org` (`get_current_user_org`; role rule per Q6)

| # | Method + path | Body | 2xx | Errors |
|---|---|---|---|---|
| E1 | `GET /api/tours?status=&publicado=&q=&page=&page_size=` | — | 200 `{"items":[TourResumo],"total":n,"page":1,"page_size":50,"cota":{"usados":n,"limite":n|null}}` | 401 |
| E2 | `POST /api/tours` | `{"codigo_imovel":"…","titulo":"…"}` | 201 Tour | 401 · 422 invalid · 404 `imovel_desconhecido` (code not in registry and not registrable, Q5) · **402 `cota_tours_esgotada`** `{"usados","limite"}` · 409 `tour_ativo_existe` (only if Q5 = one per imóvel) |
| E3 | `GET /api/tours/{id}` | — | 200 Tour | 401 · 404 (other org = 404) |
| E4 | `PATCH /api/tours/{id}` | any of `titulo, foto_inicial_id, contato{whatsapp,nome}, lead_form{…}, autorotacao{…}, marca_id, navegacao_modo` + `versao` | 200 Tour | 409 `versao_conflito` · 422 (`navegacao_modo` ≠ pins ⇒ `navegacao_indisponivel`; foreign `foto_inicial_id`) |
| E5 | `POST /api/tours/{id}/publicacao` | `{"publicado":true|false,"versao":n}` | 200 Tour; publishing creates the link if none | 409 · 422 `pendencias_bloqueantes` `{"pendencias":[…]}` · 422 `tour_removido` |
| E6 | `POST /api/tours/{id}/concluir` | `{"versao":n}` | 200 Tour (`status=concluido`; edits remain allowed) | 409 · 422 `pendencias_bloqueantes` |
| E7 | `POST /api/tours/{id}/remover` | `{"motivo":"vendido|alugado|concluido|outro","texto":"…?","versao":n}` | 200 Tour (`status=removido`, `publicado=false`, link revoked) | 409 · 422 (`texto` required for `outro`) · 403 per Q6 |
| E8 | `POST /api/tours/{id}/copiar` | `{"titulo":"…?"}` | 201 Tour (rows copied, storage objects copied server-side, new draft, unpublished, no link) | 402 `cota_tours_esgotada` |
| E9 | `POST /api/tours/{id}/link/rotacionar` | `{"versao":n}` | 200 `{"url","criado_em"}` (old token revoked at once) | 409 · 422 `tour_nao_publicado` |
| F1 | `POST /api/tours/{id}/fotos` | `{"arquivos":[{"nome_arquivo":"…","bytes":n,"content_type":"image/jpeg|image/png","sha256":"hex?"}]}` (1..50) | 201 `{"fotos":[{"foto":Foto,"upload":{"url":"…signed upload…","metodo":"PUT","headers":{…},"expira_em":"…"}}]}` rows created `aguardando_envio`, appended to `ordem` | 413 `imagem_grande_demais` (> limit, Q11) · 415 `formato_invalido` · 422 |
| F2 | `POST /api/tours/{id}/fotos/{foto_id}/envio-concluido` | `{}` | 202 Foto (`processando`; job `tour_foto_ingest` enqueued, dedupe key = foto id + versao) | 404 · 409 `arquivo_ausente` (object not in storage) |
| F3 | `GET /api/tours/{id}/fotos/status?ids=…` | — | 200 `{"fotos":[Foto]}` — polled with the seed `job-polling` helper | |
| F4 | `PATCH /api/tours/{id}/fotos/{foto_id}` | `{"nome"?, "vista_inicial"?:{yaw,pitch}, "versao"}` | 200 Foto; a new start view enqueues `tour_foto_thumb` | 409 · 422 |
| F5 | `PUT /api/tours/{id}/fotos/ordem` | `{"ids":["uuid",…],"versao":<tour versao>}` (must be the exact set) | 200 `{"fotos":[Foto],"versao":n}` | 409 · 422 `conjunto_diferente` |
| F6 | `POST /api/tours/{id}/fotos/{foto_id}/substituir` | `{"arquivo":{…as F1},"deslocamento_yaw":0.0,"versao":n}` | 201 `{"foto":Foto,"upload":{…}}`; on ingest the new image is rotated by `deslocamento_yaw` so pins stay valid | 409 |
| F7 | `DELETE /api/tours/{id}/fotos/{foto_id}?versao=n` | — | 204; its pairs and info points go with it; `ordem` re-densified | 409 |
| C1 | `POST /api/tours/{id}/conexoes` | `{"foto_a_id","foto_b_id","pin_a":{yaw,pitch},"pin_b":{yaw,pitch}}` (server orders a<b) | 201 Conexao | 409 `conexao_existe` · 422 same photo / other tour / photo not `pronta` |
| C2 | `PATCH /api/tours/{id}/conexoes/{cid}` | any of `pin_a, pin_b, a_para_b_vista_inicial, b_para_a_vista_inicial` + `versao` | 200 Conexao | 409 |
| C3 | `DELETE /api/tours/{id}/conexoes/{cid}?versao=n` | — | 204 (both directions) | 409 |
| P1 | `POST /api/tours/{id}/fotos/{foto_id}/pontos-info` | `{"tipo","titulo","conteudo","posicao"}` | 201 PontoInfo | 422 (non-https link, too long) |
| P2 | `PATCH …/pontos-info/{pid}` / `DELETE …/pontos-info/{pid}?versao=n` | | 200 / 204 | 409 |
| S1 | `GET /api/tours/{id}/estatisticas?de=&ate=` | — | 200 `{"visitas":n,"duracao_media_s":n,"fotos_vistas_media":n,"whatsapp_cliques":n,"leads":n,"por_dia":[{"dia":"YYYY-MM-DD","visitas":n}]}` | |

**State after.** E2: tour `rascunho`, unpublished, no link, quota usage +1. E5(true): `publicado=true`, `publicado_em` stamped, one active link exists; the viewer answers for that token on the next request. E5(false) / E7: the viewer answers 404 on the next request (no cache longer than 60 s, §2). F2: the photo turns `pronta` or `erro` asynchronously; the FE polls F3. F7/C3: no dangling pair can exist (FK cascade).

**Side effects.** None outside the DB/storage in v1 (no webhook, no notification). Storage objects of a removed tour are kept (Q10 retention); a hard purge is a later admin job.

## 2 · Viewer routes — tier pending owner Q1 (recommended `service`: the handler verifies the token)

All: `@limiter.limit(...)`, CORS same-origin, `Cache-Control: private, max-age=60`, `Referrer-Policy: strict-origin-when-cross-origin` on the SPA. Unknown, revoked, unpublished and removed ⇒ the **same** 404 `{"code":"tour_indisponivel"}`.

| # | Method + path | Body | 2xx | Errors |
|---|---|---|---|---|
| V1 | `GET /api/public/tours/{token}` | — | 200 Manifest | 404 · 429 |
| V2 | `POST /api/public/tours/{token}/visitas` | `{"referrer":"<document.referrer or ''>","dispositivo":"desktop|mobile|tablet|desconhecido"}` | 201 `{"visita_id":"uuid"}` — the server keeps only the referrer **host** | 404 · 429 |
| V3 | `POST /api/public/tours/{token}/visitas/{visita_id}/eventos` (works with `navigator.sendBeacon`, `text/plain` JSON) | `{"fotos_vistas":n,"duracao_s":n,"whatsapp_clicado":bool}` (monotonic: only grows) | 204 | 404 (visit of another token) · 429 |
| V4 | `POST /api/public/tours/{token}/leads` | `{"visita_id":"uuid?","nome":"…","telefone":"…","email":"…?","consentimento":true,"turnstile_token":"…","website":""}` (`website` = honeypot, must be empty) | 201 `{"recebido":true}` (no lead id echoed) | 404 · 422 (missing required field per `lead_form.campos`, invalid phone, `consentimento` false) · 403 `verificacao_falhou` (Turnstile) · 409 `formulario_inativo` · 429 |

```jsonc
// Manifest (V1) — ONLY what a visitor needs; never org ids, user ids, versions, paths, token of other links
{"titulo":"…","imovel":{"codigo":"ONE1234","titulo":"…|null","bairro":"…|null","cidade":"…|null"},
 "marca":{"nome":"…","logo_url":"…signed|null","cor_primaria":"#…","cor_secundaria":"#…"} | null,
 "contato":{"whatsapp":"5511…|null","mensagem":"Olá! Vi o tour virtual do imóvel ONE1234 …","nome":"…|null"},
 "lead_form":{"ativo":true,"campos":{…},"gatilho_pct":null,"turnstile_site_key":"…","aviso_privacidade_url":"…"},
 "autorotacao":{…},"foto_inicial_id":"uuid",
 "fotos":[{"id":"uuid","nome":"Sala","web_url":"…signed","preview_url":"…signed","thumb_url":"…signed",
           "vista_inicial":{"yaw":0,"pitch":0},
           "links":[{"foto_id":"uuid","pin":{"yaw":1.2,"pitch":-0.1},"chegada":{"yaw":-0.4,"pitch":0}}],
           "pontos_info":[{"tipo":"texto|link","titulo":"…","conteudo":"…","posicao":{"yaw":…,"pitch":…}}]}],
 "expira_em":"<signed URL expiry, ISO>"}
```
`links[].chegada` is computed by the server from the pair row (D-T5: `normalise(pin_destino.yaw + π)`, pitch 0, or the target's start view when the flag is set) so the viewer never re-derives the rule. Only photos with `status='pronta'` appear; a link to a non-ready photo is dropped. The FE re-fetches V1 before `expira_em` (signed URLs TTL 1 h).

**Lead side effects (V4, D-T9).** In one request (the imóvel is already in `imovel_registry` — the tour's FK guarantees it, so the `registrar_imovel` step of the portal ingests is not needed here): `leads_service.create_lead` with source `tour-virtual`, `codigo_imovel`, contact fields (fires the existing `lead_novo` notice) → `vincular_lead_seguro` → `tour_visitas.lead_id` set when `visita_id` belongs to this token. Dedupe follows whatever the lead pipeline already does for single leads (to be confirmed in S5; never a second dedupe rule here).

## 3 · Deprecations

None (new surface).
