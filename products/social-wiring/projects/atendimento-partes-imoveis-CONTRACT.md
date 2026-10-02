# atendimento-partes-imoveis — CONTRACT (Wave A, authoritative for Wave B)

> Spec: `atendimento-partes-imoveis-PROJECT.md` (decisions D1-D6 are closed). This file pins every endpoint
> Wave B builds or changes. FE and BE slices build to THIS file; a mismatch is a contract bug — surface it
> (`noctus.dev.surface_to_tech_lead`), never work around it. Migrations 179-184 (same folder as
> `backend/migrations/`) are part of the contract: column names below are the real ones.
> Every "EXISTING" shape below was EXTRACTED from code at tip `06a15f6f4` (file:line cited), not recalled.

## 0 · Conventions (apply to every endpoint unless the row says otherwise)

| Topic | Rule (source) |
|---|---|
| Card routes (`/api/clientes/{cliente_id}/...`) | Raw dict response, NO `{"data":…}` envelope. Lists are `{"items":[…],"total":n}` (+ extras). Auth `auth=Depends(get_current_user_org)` → `user, org_id = auth_parts(auth)` (`card_hub/auth.py`); DB `client=Depends(get_card_hub_client)`. (`card_hub/router.py:1-8`) |
| `/api/certidoes/*` and `/api/leads` | Legacy envelope `{"data": …}` via `success_response` (`noctusai_lib/primitives/responses.py:31`). `/api/leads` uses `get_current_user_org_unified`. Do NOT mix: a route keeps the envelope of the router it lives in. |
| `/api/imoveis/...`, `/api/empresas/...` | Raw dict / `{"items","total"}` (house, see `imoveis_router.py:129`). Org via `coerce_org_uuid(raw_org)`; DB via `get_imovel_hub_client`. |
| Errors | `AppException` family → `{"error":{"code","message","details"?}}`. `NotFoundError`=404 `NOT_FOUND`, `ValidationError_`=**400** `VALIDATION_ERROR`, `ConflictError`=409 `CONFLICT`, Pydantic body errors = **422** `VALIDATION_ERROR`. Custom codes below use `AppException(code=…, message=…, status_code=…, details=…)` (precedent `AmbiguousAtendimento`, `card_hub/services.py:85`). Legacy certidões routes raise `HTTPException(detail=str)` → rendered into `error.message`. |
| Inbound bodies | `StrictHttpModel` (`extra="forbid"`): unknown field ⇒ 422. (`noctusai_lib.api`) |
| Atendimento resolution | Card routes accept optional `atendimento_id`; absent ⇒ `resolve_atendimento_id` (single open) else **409 `AMBIGUOUS_ATENDIMENTO`** `details:{"atendimentos":[ids]}`. Reads that have nothing to show return empty (never 409) — mirror `compradores_service.listar`. Party-aware reads use `resolve_atendimento_id_incluindo_partes`. |
| IDs | UUID strings. `codigo` (imóvel) is ALWAYS canonical on the wire: `upper(btrim())` = `imovel_registry.codigo_canonical` (`busca_service.canonical`). |
| Dates | `YYYY-MM-DD` strings for DATE; ISO-8601 for timestamps. Money = JSON number (BRL), never string. |
| pt-BR | Every user-visible `message` below is the exact copy to ship. |
| Reads | Every list read is batched (no N+1) and paginated through `table_reads.in_batched_rows` / `iter_paged_rows` — PostgREST silently caps at 1 000 rows. |

### 0.1 Shared object: `ImovelResumo`
Produced by `busca_service._imovel_out` (EXISTING keys: `codigo, titulo, empreendimento, logradouro, numero, complemento, bairro, cidade, uf, cep, foto_destaque, corretores[], captacao, ativo_no_vista, origem, registrado, fonte`).
**Additive keys (BE-imoveis adds in `busca_service`, `_MIRROR_FIELDS`/`_SNAP_MAP`; every consumer may rely on them after Wave C):**
`categoria, valor_venda, valor_locacao, dormitorios, suites, vagas, area_total, area_privativa, area_construida` (nullable numbers/str; registry fallback via `snap_categoria, snap_valor_venda, snap_valor_locacao, snap_dormitorios, snap_area_total`; the rest `null` when only the registry knows the código) **plus two derived keys**:
- `endereco: str|null` — `"{logradouro}, {numero} — {bairro}, {cidade}/{uf}"`, each missing part dropped with its separator; `null` if nothing.
- `valor: number|null` + `valor_tipo: "venda"|"locacao"|null` — `valor_venda` if present else `valor_locacao`.
The whole `imovel` object is NEVER null in list rows (FK guarantees a registry row); an unresolved mirror yields `fonte:"registry"` with nulls.

### 0.2 Shared object: `ImovelLinhaPessoa` (rows in interesses / propriedades)
`{ id, codigo, origem, created_at, created_by|null, imovel: ImovelResumo }` (+ endpoint-specific extras named per endpoint).

---

## 1 · Certidões per party (BE-certidoes · FE-certidoes-tab)

Routes live in NEW `app/modules/card_hub/certidoes_partes_router.py` (`router = APIRouter()`, no prefix; mounted under `/api/clientes` by the Wave C0 patch §10). Paths shown are final.

### 1.1 `GET /api/clientes/{cliente_id}/certidoes/partes?atendimento_id=`
Replaces (does NOT remove) `GET …/certidoes/matriz`. **EXISTING `matriz` response is untouched and stays served** (`certidoes_matriz_service.montar_matriz`, `card_hub/router.py:1079`): `{atendimento_id, data_levantamento, linhas[], colunas[], celulas{linha.chave→coluna.id→cell}, totais{coluna.id→{nao_constam,constam,pendente}}}`; matriz cell = `{status, texto, resultado_id, consulta_id, numero, emitida_em, validade_ate, analise_ia, erro_mensagem}`; matriz linha = `{tipo|null, chave, id|null, linha:"5.n", rotulo, custom}`. The old FE keeps working until FE-certidoes-tab ships; retiring it is out of scope (D6).

**Response 200 (raw dict):**
```
{
  "atendimento_id": str|null,            // null ⇒ no single atendimento: partes=[] , linhas = the fixed 13
  "data_referencia": "YYYY-MM-DD",       // today (server date) — the date idade_dias/stale are measured at
  "max_dias": int,                       // politica.certidao_max_dias (contrato_gerador/politica.py:126, default 30) — import it, NEVER a literal
  "linhas": [ {tipo|null, chave, id|null, linha, rotulo, custom} ],   // SAME shape/semantics as matriz.linhas (fixed 5.1-5.13 + this card's custom rows 170)
  "partes": [ Parte ]
}
Parte = {
  "chave": "c:<cliente_id>" | "e:<empresa_id>",
  "kind": "pessoa" | "empresa",
  "tipo_pessoa": "PF" | "PJ",
  "rotulo": "COMP n" | "VEND n" | "EMP n",
  "lado": "comprador" | "vendedor" | null,     // null only for derived EMP columns
  "papel": str,                                 // "" for derived EMP
  "titular": bool,
  "nome": str,                                  // nome_oficial||nome | razao_social||nome_fantasia
  "documento": str|null,                        // digits only: CPF(11) | CNPJ(14)
  "cliente_id": str|null, "empresa_id": str|null,   // exactly one non-null
  "parte_id": str|null,                         // atendimento_partes.id; null for titular and derived EMP
  "totais": {"nao_constam":int,"constam":int,"pendente":int,"vencidas":int},  // per column over non-N/A cells; vencidas = cells with stale_para_contrato=true
  "celulas": { "<linha.chave>": Celula }        // one entry per linha, incl. N/A
}
Celula = {
  "status": "nao_constam"|"constam"|"pendente"|"na",   // same _status_da_celula rules as matriz (certidoes_matriz_service.py:_NAO_CONSTAM/_CONSTAM)
  "texto": str,                                  // "Não constam"|"Constam"|"Pendente"|"N/A"
  "tipo": str|null,                              // registry tipo (null for custom rows)
  "resultado_id": str|null, "consulta_id": str|null,
  "status_processamento": "pendente"|"processando"|"na_fila"|"sucesso"|"erro"|null,   // certidao_resultados.status; null when no resultado
  "resultado": "negativa"|"positiva"|"positiva_com_efeito_de_negativa"|"nao_emitida"|"negativa_com_homonimos"|null,
  "numero": str|null,
  "emitida_em": "YYYY-MM-DD"|null, "validade_ate": "YYYY-MM-DD"|null,
  "idade_dias": int|null,                        // (data_referencia - emitida_em).days; null when emitida_em null
  "stale_para_contrato": bool,                   // idade_dias is not null AND idade_dias >= max_dias  (SAME predicate as derivacao.py:1452)
  "arquivo_url": str|null,                       // OPAQUE storage handle (not fetchable); fetch via existing GET /api/certidoes/resultados/{id}/url
  "tem_arquivo": bool,
  "arquivo_nome": str|null,
  "origem": "api"|"ia"|"manual"|null,            // certidao_resultados.resultado_origem
  "confirmado": bool,                            // confirmado_em IS NOT NULL
  "analise_ia": str|null, "erro_mensagem": str|null,
  "segunda_via": bool,  // C0: the Receita refused a NEW certidão → this is its 2ª via; emitida_em is the ORIGINAL date
  "pcen": null | {titulo, mensagem, explicacao[], validade_ate, vencida, ciente, ciente_em, duvida_em, acoes}
         // Receita "positiva com efeitos de negativa" 2ª via ONLY (owner 2026-10-01): judged by its PRINTED validity, not the 30-day age;
         // the operator acknowledges via POST …/certidoes/resultados/{id}/ciencia-pcen {acao:"entendi"|"duvida"}
}
```
Rules (pinned):
- **Party set & labels.** `partes` = `partes_service.listar_partes` rows (§2.1) for BOTH lados, titular first (= `COMP 1`); `COMP n`/`VEND n` numbered per lado by `ordem` (PF and PJ share the numbering); then derived `EMP n` columns = `empresas_service.listar(...).items[*].empresa` with `exige_certidoes=true` that are NOT already a PJ party (same filter as `resolver_colunas`, `certidoes_matriz_service.py:~175`). Titular is `titular:true`, `parte_id:null`, `lado:"comprador"`, `papel:"comprador"`.
- **Cell selection.** Party-scoped: read `certidoes_por_cliente` / `certidoes_por_empresa` (EXISTING readers, `certidoes/service.py:3076/3103`, unchanged shape) — NOT by `atendimento_parte_id`, so a certidão follows the person across deals. Per `tipo` (or `linha_customizada_id` for custom rows): winner = greatest `emitida_em`; tie / null ⇒ greatest `created_at`. (The matriz rule "newest created_at wins" is REPLACED here.)
- N/A rules unchanged: `fgts_regularidade` N/A on PF; `serasa` N/A on PJ; custom rows never N/A.
- `atendimento_id` query param optional; resolution per §0 using `resolve_atendimento_id_incluindo_partes`; **ambiguous ⇒ 200 with `atendimento_id:null, partes:[]`** (read, never 409 — same as `montar_matriz`).
- Errors: 404 `NOT_FOUND` unknown `cliente_id` (via `ensure_cliente`).

### 1.2 `POST /api/clientes/{cliente_id}/certidoes/partes/{kind}/{alvo_id}/emissao` — solicitar emissão (all or selected)
`kind ∈ pessoa|empresa` (path literal; else 404), `alvo_id` = cliente_id | empresa_id of a party of the resolved atendimento (or the titular).
Body (`StrictHttpModel`): `{ "tipos": list[str]|null = null, "atendimento_id": UUID|null = null }` — `null` ⇒ every AUTOMATED tipo applicable to the party — the `registry.CERTIDOES_CONFIG` set WITHOUT `tjsp` (identical to `criar_consulta` with `incluir_tjsp=false`; TJSP is never auto-requested here). `tipos` entries must be in `CERTIDOES_CONFIG` tipos.
- **201** raw dict `{ "consulta_id": str, "resultados": [ {"resultado_id": str, "tipo": str, "status_processamento": "pendente"} ] }`.
- **State after:** ONE new `certidao_consultas` row (`tipo_documento` cpf|cnpj, `documento` digits, `nome`, `data_nascimento`/`genero`/`rg`/`nome_mae`/`nome_pai` copied from the cliente when present, `created_by=user.id`, status `pendente`, `total_certidoes=len(tipos)`) with `cliente_id` | `empresa_id` set, and `atendimento_parte_id` set when the party has a `parte_id` (same fields `vincular-parte/-cliente/-empresa` write); one `certidao_resultados` row per tipo (`status:"pendente"`); `processar_consulta` scheduled via `BackgroundTasks`. **Never mutates an existing resultado** — old cells stay as history; the new one wins by `emitida_em` when it lands (and a failed new one does NOT shadow the old: selection is by `emitida_em`, and an `erro` row has `emitida_em null`, so a dated old cell still wins).
- Errors: 404 `NOT_FOUND` (party not on this atendimento: `"Parte não encontrada neste atendimento."`); 409 `AMBIGUOUS_ATENDIMENTO`; 422 `DOCUMENTO_AUSENTE` `"Informe o CPF/CNPJ da parte antes de solicitar certidões."`; 422 `TIPO_INVALIDO` `"Tipo de certidão inválido: {tipo}."`; 422 `TIPO_NAO_AUTOMATICO` `"{rotulo} é registrada manualmente — envie o PDF na célula."` (serasa, tjsp_*, fgts_regularidade, custom); 422 missing credentials = the EXISTING `check_required_credentials` message + `" Configure em Configurações → Chaves de API."` (`routers/certidoes.py:~474`). Pre-flight credentials BEFORE any write (same as `criar_consulta`).
- Idempotency: none (each call is a real, billed emission request). FE must disable the button while pending.
- Fix bundled in BE-certidoes (spec §3.1): Receita/PGFN request a NEW emission (replace `preferencia_emissao="2via"`, `registry.py:225`, with the value verified in InfoSimples docs; update `test_certidoes_service.py:294`). FE contract unaffected.

### 1.3 `POST /api/clientes/{cliente_id}/certidoes/resultados/{resultado_id}/reemitir` — re-emitir one cell
`resultado_id` must belong (via its consulta) to a party of this card (cliente/empresa linked to the atendimento) — else 404 `NOT_FOUND`. Body: `{}` (empty `StrictHttpModel`).
- **201** same shape as 1.2 with a single-element `resultados`. Creates a NEW consulta + NEW resultado for the same party and tipo (same rules/state as 1.2); the original resultado is untouched.
- Errors: 404; 422 `TIPO_NAO_AUTOMATICO` (manual/custom tipos: `"{rotulo} é registrada manualmente — envie o PDF na célula."`); 422 `DOCUMENTO_AUSENTE`; credentials 422 as 1.2.

### 1.4 `POST /api/clientes/{cliente_id}/certidoes/celulas` — ensure an uploadable cell (empty cell → resultado)
Body: `{ "kind": "pessoa"|"empresa", "alvo_id": UUID, "linha_chave": str, "atendimento_id": UUID|null }` (`linha_chave` = `linha.chave`: a fixed tipo or a custom-row uuid).
- Returns the existing winner cell's resultado if one exists for (party, linha) → **200** `{"resultado_id","consulta_id","criado":false}`; else creates a manual-origin placeholder (same mechanics as `POST /api/certidoes/consultas/manual`, one resultado, `status:"pendente"`) → **201** `{"resultado_id","consulta_id","criado":true}`. Linked like 1.2. N/A combos (`fgts`×PF, `serasa`×PJ) ⇒ 422 `CELULA_NAO_APLICAVEL` `"Esta certidão não se aplica a este tipo de parte."`.
- Rationale: keeps the upload on the EXISTING route (no new `UploadFile` route ⇒ no `max_body_path_overrides` edit, `main.py:539` already covers it).

### 1.5 Upload to a cell (EXISTING — unchanged route)
`POST /api/certidoes/resultados/{resultado_id}/upload` — multipart `file` (PDF only), legacy envelope. Request: `file` (UploadFile). **Response `{"data": {…resultado fields…, …update_data}}`** with `status:"processando"` while the background read runs (`routers/certidoes.py:1032`). Errors: 422 `"Apenas arquivos PDF são aceitos."`, 422 `"Arquivo vazio."`, 404 `"Resultado não encontrado"`. **Behaviour change (BE-certidoes, spec §3.1):** re-upload onto a confirmed (locked) resultado clears `numero/emitida_em/validade_ate` (+ `resultado`) and re-extracts; the lock protects a human edit of THAT file only. Poll: re-`GET …/certidoes/partes` (FE polls while any cell has `status_processamento ∈ {pendente,processando,na_fila}`).
Other EXISTING cell actions FE-certidoes-tab reuses unchanged: `PATCH /api/certidoes/resultados/{id}` (body `ResultadoPatch`: `numero ≤100, emitida_em date, validade_ate date, resultado ∈ {negativa,positiva,positiva_com_efeito_de_negativa,nao_emitida,negativa_com_homonimos}`, all optional; `{"data": resultado}`), `GET /api/certidoes/resultados/{id}/url?intent=view|download` → `{"data":{"url","expires_at"}}` (404 `"Nenhum arquivo para este resultado"`), `GET /api/certidoes/resultados/{id}/transcricao[/pdf]`.

### 1.6 Adicionar certidão custom row (EXISTING — unchanged)
`POST /api/clientes/{cliente_id}/certidoes/matriz/linhas` body `{nome: str 1..200}` → **201** the row (`certidao_matriz_linhas_customizadas`: `{id, org_id, cliente_id, nome, ordem, excluida_em, created_at, created_by, updated_at}`); `PATCH …/linhas/{linha_id}` body `{nome}` → row; `DELETE …/linhas/{linha_id}` → 204 (soft). Custom rows stay keyed by the CARD's `cliente_id` (always a PF; PJ columns share them — no schema change, see 179 header). The reader in 1.1 reuses `linhas_customizadas_ativas`.

### 1.7 Certidão → party profile feed (BE-certidoes, internal — no endpoint)
After `_derive_estrutura`, fill-empty/conflict-on-disagree through the existing quinteto provenance (`*_origem/_documento_id/_em/_confirmado_*`) + `campo_conflitos`: PF → `clientes.nome_oficial`, `cpf`, `data_nascimento`; PJ → `empresas.razao_social`, `situacao_cadastral`, `data_situacao_cadastral`. Register the source in `proveniencia/fontes.py::FONTES_REGISTRO` and `contrato_gerador/validacao_extracao.py::REGISTRO`; include in `proveniencia/linhagem.py`. No response shape changes.

---

## 2 · Parties (BE-partes · FE-leads-partes)

New files `card_hub/partes_service.py`, `partes_schemas.py`, `partes_router.py` (`router = APIRouter()`, no prefix, mounted under `/api/clientes`, §10).

### 2.1 `GET /api/clientes/{cliente_id}/partes?atendimento_id=` — ALL parties, both lados, titular included
Service contract (BE-certidoes imports it): `partes_service.listar_partes(client, org_id: UUID, cliente_id: UUID, *, atendimento_id: UUID|None) -> tuple[str|None, list[dict]]` returning `(atendimento_id, items)`; ambiguous ⇒ `(None, [])`.
**200:** `{ "items": [ParteItem], "total": n, "atendimento_id": str|null }`
```
ParteItem = {
  "parte_id": str|null,            // null = titular
  "titular": bool,
  "rotulo": "COMP n"|"VEND n",
  "lado": "comprador"|"vendedor",
  "papel": str,
  "ordem": int,
  "tipo_pessoa": "PF"|"PJ",
  "cliente_id": str|null, "empresa_id": str|null,
  "nome": str, "documento": str|null,       // digits
  "observacao": str|null,
  "cliente": {…_CLIENTE_RESUMO keys…}|null, // EXACT keys of compradores_service._CLIENTE_RESUMO (compradores_service.py:155)
  "empresa": {"id","razao_social","nome_fantasia","cnpj","situacao_cadastral"}|null
}
```
Ordering: comprador lado first (titular `COMP 1`, then partes by `(ordem, created_at)`), then vendedor lado; labels assigned in that order per lado.

### 2.2 `GET /api/clientes/{cliente_id}/compradores?atendimento_id=&lado=` (EXISTING — shape frozen)
Unchanged: `{items:[{id, atendimento_id, cliente_id, lado, papel, ordem, observacao, created_at, cliente:{…_CLIENTE_RESUMO}|null}], total, atendimento_id, lado}` (`compradores_service.listar`, `:187`). **PJ rows are NOT returned here** (existing consumers assume `cliente_id` non-null); PJ is visible only in 2.1. Titular still not in `items`.

### 2.3 `POST /api/clientes/{cliente_id}/compradores` — add party (PF or PJ) with lado/papel (EXTENDED)
**EXISTING body `CompradorCreateBody`** (`card_hub/schemas.py:262`): `cliente_id UUID|null, nome str≤255|null, celular str≤32|null, papel str|null, observacao str≤2000|null, atendimento_id UUID|null, lado str|null`. **New body `ParteCreateBody` (BE-partes, in `partes_schemas.py`; Wave C0 swaps the route to it) = the same fields PLUS** `empresa_id: UUID|null`, `cnpj: str 11..18|null`, `razao_social: str ≤255|null`.
- Exactly ONE of `{cliente_id, nome, empresa_id, cnpj}` ⇒ else **400** `VALIDATION_ERROR` `"Informe exatamente um de: cliente_id, nome, empresa_id, cnpj."` (replaces the 2-way message at `compradores_service.py:~268`).
- `cnpj`: validated with `noctusai_lib.integrations.documents.cnpj`; invalid ⇒ 400 `"CNPJ inválido."`; find-or-create the `empresas` row by normalized CNPJ in this org (reuse the empresa creation primitive `empresas_service.adicionar_manual` already uses — do not write a second one); `razao_social` fills a newly created row.
- `papel`: validated against `PAPEIS_POR_LADO[lado]` (unchanged). For a PJ party `conjuge` ⇒ 400 `"Uma empresa não pode ser cônjuge."`.
- **201** body = `ParteItem` (2.1) of the created row (for PF this is a superset of today's `_out`: keep the old keys `id, atendimento_id, cliente_id, lado, papel, ordem, observacao, created_at, cliente` too).
- **State after:** one `atendimento_partes` row (`cliente_id` XOR `empresa_id`, per 179 CHECK `atendimento_partes_pessoa_xor_empresa`), `ordem` = max+1 within lado, `created_by`; PF link also writes `clientes.vinculado_a_cliente_id/vinculo_origem` exactly as today (`_vincular`); PJ writes no cliente link. No certidão rows are created (certidões are requested via 1.2).
- Errors: 409 `CONFLICT` `"Esta pessoa já é parte deste atendimento."` / `"Esta empresa já é parte deste atendimento."`; 400 `"O titular já é parte deste atendimento — adicione outra pessoa."` (unchanged); 404 unknown `cliente_id`/`empresa_id`; 409 `AMBIGUOUS_ATENDIMENTO`; 400 invalid papel (unchanged text).
- Strictness: `extra="forbid"` (unchanged).
- Deprecations: none.

### 2.4 `PATCH /…/compradores/{parte_id}` body `{papel: str 1..64}` and `DELETE /…/compradores/{parte_id}` → 204 (EXISTING, unchanged)
Both must tolerate PJ `parte_id`s (`cliente_id` null): PATCH `conjuge` on PJ ⇒ 400 as above; DELETE removes the junction row only — certidões, empresa and cliente rows are NOT deleted (party-scoped history survives).

### 2.5 `GET /api/clientes/{cliente_id}/partes/lookup?documento=<cpf|cnpj>&atendimento_id=` — registration lookup by documento
`documento`: any punctuation; normalized to digits; 11 ⇒ CPF, 14 ⇒ CNPJ (check-digit validated with `integrations.documents.cpf/cnpj`).
**200** (a lookup miss is NOT a 404):
```
{
  "documento": str(digits), "tipo_documento": "cpf"|"cnpj",
  "encontrado": "cliente"|"empresa"|null,
  "cliente": {"id","nome","nome_oficial","cpf","celular","email"}|null,
  "empresa": {"id","razao_social","nome_fantasia","cnpj","situacao_cadastral"}|null,
  "ja_no_atendimento": bool,              // already titular/parte of the resolved atendimento
  "atendimentos": [ {"id","titulo","etapa":{"id","nome"}|null,"status","arquivado":bool,"lado","papel","titular":bool,"parte_id":str|null} ],  // every atendimento this person/empresa is on (titular OR party), newest first; excludes none
  "certidoes": {
    "max_dias": int, "data_referencia": "YYYY-MM-DD",
    "itens": [ {"tipo","rotulo","resultado_id","emitida_em","validade_ate","idade_dias","stale_para_contrato":bool,"resultado"} ],  // latest per tipo by §1.1 selection; only tipos that have a dated resultado
    "tipos_vencidos": [str], "alerta_vencidas": bool,
    "mensagem": str|null                  // when alerta_vencidas: "Há certidões com mais de {max_dias} dias. Re-emita e re-analise antes de usar no contrato."
  }
}
```
- Errors: **400** `VALIDATION_ERROR` `"CPF inválido."` / `"CNPJ inválido."` / `"Informe um CPF ou CNPJ válido."` (wrong length). Org-scoped; never returns another org's rows.
- Read-only; no writes.

---

## 3 · Atendimento imóveis (BE-imoveis · FE-leads-partes)

New files under `app/modules/imovel_hub/`: `atendimento_imoveis_service.py`, `atendimento_imoveis_router.py` (`router = APIRouter()`, paths below, registered via `imovel_hub.register()`'s `routers=[…]`, §10). DB: `social_wiring.atendimento_imoveis` (181).

### 3.1 `GET /api/clientes/{cliente_id}/atendimento-imoveis?atendimento_id=`
**200** `{ "items": [Item], "total": n, "atendimento_id": str|null, "imovel_pendente": bool }`; `Item = { id, codigo, origem:"lead"|"manual"|"campanha"|"negociacao", principal:bool, em_negociacao:bool, created_at, created_by|null, imovel: ImovelResumo }`. `em_negociacao` = `codigo == atendimento_negociacao.imovel_codigo`. Order: principal first, then `created_at`. Live rows only (`deleted_at IS NULL`). `imovel_pendente` = zero live rows (DERIVED — no stored flag, no column). Ambiguous ⇒ `{items:[],total:0,atendimento_id:null,imovel_pendente:false}`.

### 3.2 `POST /api/clientes/{cliente_id}/atendimento-imoveis`
Body: `{ "codigo": str 1..64, "principal": bool=false, "origem": "manual"|"campanha"="manual", "atendimento_id": UUID|null }` (strict; `origem:"lead"|"negociacao"` ⇒ 422 — system-only values).
- **201** `Item`. `codigo` canonicalized; must exist in `imovel_registry` (the FE picker `ImovelCodigoPicker` registers new ones first via `POST /api/imoveis/{codigo}/registrar`, EXISTING `imovel_hub/router.py:165`).
- **State after:** one live `atendimento_imoveis` row; `principal:true` ⇒ any other live principal of the atendimento is demoted FIRST (partial unique index `uq_sw_atendimento_imoveis_principal` is the backstop); a previously soft-deleted (atendimento, código) row is REVIVED (deleted_at null, origem/principal updated) instead of inserting. If the atendimento had no live imóvel the new row becomes principal regardless. Does NOT touch `atendimento_negociacao.imovel_codigo`.
- Errors: 404 `NOT_FOUND` `"Imóvel {codigo} não encontrado. Selecione um imóvel do catálogo ou cadastre-o."`; 409 `CONFLICT` `"Este imóvel já está vinculado ao atendimento."`; 409 `AMBIGUOUS_ATENDIMENTO`.

### 3.3 `PUT /api/clientes/{cliente_id}/atendimento-imoveis/{id}/principal` (no body)
**200** `Item` (now `principal:true`); demotes the previous principal. 404 `NOT_FOUND` if `id` isn't a live row of one of this cliente's atendimentos. Idempotent.

### 3.4 `DELETE /api/clientes/{cliente_id}/atendimento-imoveis/{id}` → 204
Soft delete (`deleted_at=now()`). If it was principal, the oldest remaining live row becomes principal.
Errors: 409 `IMOVEL_EM_NEGOCIACAO` `"Este imóvel está em negociação neste atendimento — altere a negociação antes de removê-lo."`; 409 `ULTIMO_IMOVEL` `"O atendimento precisa de pelo menos um imóvel."`; 404.

### 3.5 Invariant service hook (no endpoint)
`atendimento_imoveis_service.garantir_vinculo(client, org_id, atendimento_id, codigo, *, origem)` — idempotent upsert-by-read (never `upsert()`, Mock no-op). **Single writer of `atendimento_negociacao.imovel_codigo` is `card_hub/negociacao_service`** (also reached by `roteiros_service.registrar_proposta` via `negociacao_service`): BE-imoveis adds the call there so `imovel_codigo ∈ junction` always (`origem="negociacao"`; if the código already is linked by lead it is upgraded to `negociacao`). Service-enforced, no DB trigger.
`atendimento_imoveis_service.vincular_lead(client, org_id, *, lead_id: UUID|None=None, meta_ads_lead_id: str|None=None)` — reads the lead's `codigo_imovel_norm` (leads: 062, meta: 180), ensures registry row (`registrar_imovel(origem="lead")`, `dados_service.py:295`), links `origem="lead"` (principal if none) AND writes the cliente interesse (§4.1, `origem="lead"`, `lead_id|meta_ads_lead_id`). Called by EVERY ingest path (manual `POST /api/leads`, `meta_ingest_service`, OLX, imovelweb) and by the clientes backfill sweep so a late cliente attach still lands the interesse.

### 3.6 `POST /api/leads` — código required for manual create (EXISTING route, CHANGED)
EXISTING body `LeadCreate` (`modules/leads/schemas.py:82`, strict): `data_entrada: date` (required), `codigo_raw, codigo_imovel, empreendimento, regiao: str|null`, `origem_id: UUID|null`, `tipo_lead: str="desconhecido"`, `cliente_nome, contato, contato_tipo: str|null`, `corretor_id: UUID|null`, `anuncio_tier, status, observacoes: str|null`, `follow_up_data: date|null`, `follow_up_nota: str|null`. Response today: `{"data": LeadOut}` (201), `_out(row, refs)`.
**Change:** `codigo_imovel` becomes **required, non-blank** (`str`, `min_length=1` after strip) on this route ONLY (importers/ingest use services, not this route). Errors:
- missing/blank ⇒ **422** `VALIDATION_ERROR`, message `"Informe o imóvel do lead."` (field validator message), field `codigo_imovel`.
- unknown (not in `imovel_registry` after `canonical()`) ⇒ **422** custom `IMOVEL_DESCONHECIDO` `"Imóvel {codigo} não está cadastrado. Selecione um imóvel do catálogo."` (`details:{"codigo":…}`); nothing is written.
**Response (201) `{"data": LeadOut + {"atendimento_id": str|null, "imoveis": [codigo,…]}}`** — the two additive keys come from the spawned card (migration 034 trigger + `attach_lead_now`).
**State after:** `leads` row (`codigo_imovel` stored canonical, `codigo_imovel_norm` derived by trigger 062, `imovel_ref_id` set), spawned atendimento, `atendimento_imoveis` row `origem="lead"` `principal=true`, `cliente_imovel_interesses` row `origem="lead"` for the attached cliente. **Inbound/ingest without a resolvable código** (webhook/portal/Meta without REF): accepted unchanged and surfaces as `imovel_pendente` (3.1) — never dropped.
`PATCH /api/leads/{id}` changing `codigo_imovel`: NOT in scope (junction is not rewritten) — provisional, see §11.

---

## 4 · Interesses / propriedades / interessados / similares / person page (BE-imoveis · FE-pessoa-interesses-roteiro)

Files: `imovel_hub/interesses_service.py`, `proprietarios_service.py`, `similares_service.py`, `pessoa_service.py`; routers `interesses_router.py`, `imovel_relacionamentos_router.py`, `pessoa_router.py` (each `router = APIRouter()` with full paths below; registered through `imovel_hub.register()`).

### 4.1 Interesses of a cliente — DB `cliente_imovel_interesses` (182)
- `GET /api/clientes/{cliente_id}/interesses` → **200** `{ "items": [Item], "total": n }`; `Item = ImovelLinhaPessoa + { "lead_id": str|null, "meta_ads_lead_id": str|null }`, `origem ∈ lead|manual|campanha|roteiro|permuta`; `imovel` carries the spec'd row fields: `codigo, foto_destaque, endereco, complemento, valor, valor_tipo` (+ the rest of `ImovelResumo`). Live rows, `created_at DESC`. 404 unknown cliente.
- `POST /api/clientes/{cliente_id}/interesses` body `{ "codigo": str 1..64, "origem": "manual"|"campanha"|"permuta" = "manual" }` (strict; `lead`/`roteiro` ⇒ 422) → **201** `Item`. Revives a soft-deleted (cliente, código). Errors: 404 `"Imóvel {codigo} não encontrado. Selecione um imóvel do catálogo ou cadastre-o."`; 409 `CONFLICT` `"Este imóvel já está na lista de interesses."`.
- `DELETE /api/clientes/{cliente_id}/interesses/{interesse_id}` → 204 (soft delete). 404 if not this cliente's live row. Removing an interesse never touches lead/atendimento_imoveis rows.
- Origem `roteiro` is RESERVED (no writer in v1; §11).

### 4.2 Imóveis owned (proprietários) — DB `imovel_proprietarios` (183)
- `GET /api/clientes/{cliente_id}/propriedades` and `GET /api/empresas/{empresa_id}/propriedades` → **200** `{ "items": [ImovelLinhaPessoa], "total": n }` (`origem ∈ manual|matricula|atendimento`).
- `POST` (same two paths) body `{ "codigo": str 1..64 }` → **201** item, `origem:"manual"`. 404 unknown imóvel (same text as 4.1); 409 `CONFLICT` `"Este imóvel já consta como propriedade."`; 404 unknown cliente/empresa (org-scoped).
- `DELETE /api/clientes/{cliente_id}/propriedades/{id}` and `/api/empresas/{empresa_id}/propriedades/{id}` → 204 (soft). Only `origem="manual"` rows may be removed; `matricula`/`atendimento` ⇒ 409 `PROPRIEDADE_DERIVADA` `"Esta propriedade foi registrada automaticamente. Corrija a matrícula/negociação de origem."`.
- Imóvel side: `GET /api/imoveis/{codigo}/proprietarios` → `{ "items": [ {id, tipo_pessoa:"PF"|"PJ", cliente_id|null, empresa_id|null, nome, documento|null, celular|null, email|null, origem, created_at} ], "total": n }`. Service for the PDF: `proprietarios_service.por_codigos(client, org_id, codigos: list[str]) -> dict[str, list[{"nome": str, "documento": str|None, "tipo_pessoa": str}]]` (canonical-keyed, batched).
- Backfill: 183 covers `origem="atendimento"` (vendedor partes × negociação imóvel). **`origem="matricula"` backfill is NOT in SQL — BE-imoveis ships an idempotent Python backfill** (matrícula owners matched to clientes by normalized CPF, same normalization the matrícula service owns) run once at startup/sweep; rows `origem="matricula"`.

### 4.3 Imóvel interessados — `GET /api/imoveis/{codigo}/interessados?limit=50&offset=0`
`limit 1..200`, `offset ≥0`. **200** `{ "items": [Row], "total": n }` (`total` = full live-interesse count):
```
Row = { "interesse_id", "cliente_id", "nome": str, "telefone": str|null, "email": str|null,
        "origem": "lead"|"manual"|"campanha"|"roteiro"|"permuta",
        "interesse_created_at": ts,
        "lead_created_at": ts|null,            // created_at of the originating lead / created_time of the meta lead
        "ultima_interacao_em": ts|null,        // max(cliente_touches.ocorreu_em) for the cliente
        "tem_atendimento_aberto": bool, "atendimento_aberto_id": str|null }  // an atendimento of this cliente (titular or parte) not arquivado and substituida_por null
```
`nome` = `nome_oficial||nome`; `telefone` = `celular` else phone from `chave_canonica` (E.164 as stored). Sort: `ultima_interacao_em DESC NULLS LAST, interesse_created_at DESC`. Errors: 404 `NOT_FOUND` unknown código (`registrado=false`). Org-scoped; LGPD: returns contact data only to authenticated org users (no new egress).

### 4.4 Imóvel similares — `GET /api/imoveis/{codigo}/similares?limit=10&score_minimo=`
`limit 1..50` (default 10), `score_minimo` float default `SCORE_MINIMO_PADRAO` (45.0). **200**
`{ "items": [ ImovelResumo + { "score": number, "justificativa": str, "reasons": [str], "detalhes": {…}, "score_breakdown": {…} } ], "total": n, "sem_semantica": int }`.
- **Engine (reuse, do not build a second matcher):** `noctusai_lib.domain.real_estate.matching.gerar_matches_para_imovel(origem, [candidatos], score_minimo)` (`seed/lib/backend/noctusai_lib/domain/real_estate/matching.py:629`; scorer `calcular_score_total` `:535`). Scorer dicts via `app.modules.permutas.adapter.ativo_para_scorer({"id": codigo, "natureza": "imovel", "status": "ativo"}, imovel=<imoveis mirror row, adapter.IMOVEL_FIELDS>)`; candidates relabelled with `adapter.como_oferta(...)` (`permutas/adapter.py:283`) so specs/region gates engage. NB `adapter.listar_ativos_para_scorer` lists only `permuta_ativos` — NOT the catalog — so the candidate pool is built from the `imoveis` mirror (same `ativo_para_scorer` mapping): same `uf`+`cidade` as the target, `status` active, excluding the target, paged with `iter_paged_rows`, hard cap 2 000 candidates. A target with no mirror row (sold/unlisted) ⇒ **200** `{items:[],total:0,sem_semantica:0}` plus header-free `"aviso": "Imóvel fora do catálogo — sem base para comparar."` as an extra key `aviso`.
- `reasons` = `justificativa.split(". ")` filtered non-empty. Items best-first by `score`. `sem_semantica` = count of scored pairs where `falta_vetor_bilateral(...)` is true (same meaning as `permutas.service.gerar_matches`). Nothing is persisted (no `permuta_matches` writes).
- One-click "add to an interessado's list" = `POST …/interesses` (4.1) with `origem:"manual"`.
- Errors: 404 unknown código.

### 4.5 Person page payload — `GET /api/clientes/{cliente_id}/resumo`
(EXISTING `GET /api/clientes/{cliente_id}` stays: `{**cliente, atendimentos:[titular-only rows], touch_count}` — `clientes_router.py:902`.) **200**:
```
{
  "cliente": {id, nome, nome_oficial, cpf, celular, email, estado_civil, ...the _CLIENTE_RESUMO keys...},
  "papeis": [ "lead"|"comprador"|"vendedor"|"proprietario" ],   // derived: lead = has touches or is titular; comprador = titular or lado comprador; vendedor = lado vendedor party; proprietario = ≥1 live imovel_proprietarios
  "contatos": {"celular": str|null, "email": str|null, "chave_canonica": str|null},
  "atendimentos": [ {"id","titulo","etapa":{"id","nome"}|null,"status","arquivado":bool,"titular":bool,"lado","papel","parte_id":str|null,"imovel_pendente":bool,"imoveis":[codigo],"created_at"} ],   // every atendimento the person is on, newest first
  "contagens": {"interesses": int, "propriedades": int, "roteiros": int, "atendimentos": int}
}
```
404 `NOT_FOUND` unknown cliente. FE orders sections by `papeis` (D3); `/clientes/:id` and `/vendedores/:id` call this same endpoint.

---

## 5 · Roteiro (BE-roteiro · FE-pessoa-interesses-roteiro)

Files: `card_hub/roteiros_service.py`, `card_hub/roteiro_pdf_service.py`, NEW `card_hub/roteiro_pdf_template.py`. DB: `roteiros.data_visita` (184).

### 5.1 `POST /api/clientes/{cliente_id}/roteiros` — create from ordered códigos + date (EXISTING, CHANGED)
EXISTING body `RoteiroCreateBody` (`card_hub/schemas.py:118`): `imoveis: list[str] (min 1, visiting order)`, `titulo: str|null`, `atendimento_id: UUID|null`. **New body (BE-roteiro defines `RoteiroCreateBodyV2` in `roteiros_service`-adjacent `roteiro_schemas.py`; C0 swaps it in):** `imoveis: list[str] (1..50)`, **`data_visita: date` (required)**, `titulo: str|null`, `atendimento_id: UUID|null`. Past dates are allowed (provisional, §11).
- **201** roteiro out = EXISTING `_ROTEIRO_FIELDS` **plus `data_visita`**: `{ id, atendimento_id, titulo, data_visita: "YYYY-MM-DD", created_at, visitas: [Visita], contagem:{total,realizadas,nao_realizadas,pendentes} }`; `Visita = {id, roteiro_id, codigo, ordem, status, observacao, feedback_em, created_at, proposta_em, proposta_por, proposta_aceita_em, proposta_aceita_por, imovel: ImovelResumo}` (`roteiros_service.py:~78-93,207`).
- **State after:** one `roteiros` row + one `visitas` row per código, `ordem` = array index, `status:"pendente"`. Interesses are NOT touched (the FE only offers códigos from the interesses list).
- Errors: 422 `VALIDATION_ERROR` `"Informe a data da visita."` (missing/invalid `data_visita`); 400 `"imóvel repetido no roteiro: X, Y"` (EXISTING `_validar_codigos`); 404 `NOT_FOUND` unknown código; 409 `AMBIGUOUS_ATENDIMENTO`.
- `GET /api/clientes/{cliente_id}/roteiros` (EXISTING) items now carry `data_visita` (`null` for legacy rows). `PATCH …/roteiros/{roteiro_id}` body becomes `{titulo?: str|null, data_visita?: date}` (explicit `data_visita:null` ⇒ 422 `"Informe a data da visita."`). PUT `…/ordem` (body `{visita_ids: [UUID] (complete ordered set)}`, 400 on mismatch), visita routes, DELETE: unchanged.

### 5.2 `GET /api/clientes/{cliente_id}/roteiros/{roteiro_id}/pdf` — PDF fetch (EXISTING path, new content)
`200 application/pdf` raw bytes, `Content-Disposition: attachment; filename="<roteiro_pdf_service.nome_arquivo(roteiro)>"` — name now includes `data_visita` (`roteiro-<slug>-<YYYY-MM-DD>.pdf`; `roteiro` without date ⇒ no date part). 404 `NOT_FOUND` when the roteiro is not this cliente's. **Always 200 when the roteiro exists** — a failed photo fetch renders the text `"Sem foto"` in that page; it never fails the PDF.
Renderer: **`noctusai_lib.integrations.documents.html_pdf.render_html_pdf(html: str, *, deterministic=False) -> bytes`** (owner-mandated path; replaces reportlab). Signature: `roteiro_pdf_service.gerar(roteiro: dict, *, cliente_nome: str|None, proprietarios_por_codigo: dict[str, list[dict]] | None = None, fotos_por_codigo: dict[str, str] | None = None) -> bytes`; `proprietarios_por_codigo` shape = §4.2 `por_codigos`; `fotos_por_codigo` = `codigo → data: URI` built by `roteiro_pdf_service.carregar_fotos(imoveis)` (first photo of each imóvel, `foto_destaque`/`fotos[0]`, httpx fetch with timeout 5 s, size cap 3 MB, failures ⇒ missing key). Pages: header (cliente, título, `data_visita` as dd/mm/yyyy, "Imóvel i de N") then ONE imóvel per page, in `visitas.ordem`: dados técnicos (código, categoria, endereço+complemento, bairro/cidade/UF, valor, dormitórios/suítes/vagas, áreas), foto (data URI), proprietário(s) (names from `proprietarios_por_codigo`, else `"—"`), `Visita realizada ☐` + `Assinatura: ________`, `Gerou proposta? ☐ Sim ☐ Não`, `Proposta:` ruled lines, `☐ Permuta ☐ Financiamento ☐ FGTS`. Technical fields come from the additive `ImovelResumo` keys (§0.1); a missing key renders `"—"`.

---

## 6 · FE type + hook contract (what every FE slice codes against)

TS interfaces mirror the JSON above 1:1 (snake_case keys kept; no camelCase mapping). Each FE slice defines the types for ITS endpoints in its OWN new `src/types/*.ts` file; no two slices define the same interface (table in §9). Cross-slice component contracts (exact names/props):
- FE-certidoes-tab exports `components/card/certidoes/CertidoesPartesTab.tsx` → `export function CertidoesPartesTab(props: { clienteId: string; atendimentoId?: string | null }): JSX.Element`.
- FE-pessoa-interesses-roteiro exports `components/interesses/ImovelInteressesList.tsx` → `export function ImovelInteressesList(props: { clienteId: string; atendimentoId?: string | null }): JSX.Element` (checkbox rows → "Gerar roteiro" → ordering dialog + date → `POST …/roteiros` → PDF), and `pages/PessoaPage.tsx` (default export, used by both person routes).
- FE-leads-partes wires both into `ClienteCardDialog.tsx` (§9 shared-file rules).

---

## 7 · Migrations (this PR folder; NOT applied)

| # | File | Adds |
|---|---|---|
| 179 | `179_atendimento_partes_pj_e_certidoes_por_parte.sql` | `atendimento_partes.empresa_id` + `cliente_id` nullable + CHECK xor + unique (atendimento, empresa); certidão party-read indexes |
| 180 | `180_meta_ads_leads_codigo_imovel.sql` | `meta_ads_leads.codigo_imovel/_norm` + trigger (fills from `answers->>'REF'`) + backfill + registry registration |
| 181 | `181_atendimento_imoveis.sql` | junction + backfill (lead + negociação) incl. registry registration |
| 182 | `182_cliente_imovel_interesses.sql` | interesses + backfill from every historical lead/meta lead via `cliente_touches` |
| 183 | `183_imovel_proprietarios.sql` | proprietários + vendedor-parte × negociação backfill |
| 184 | `184_roteiros_data_visita.sql` | `roteiros.data_visita DATE` (nullable legacy) + index |

`imovel_pendente` is DERIVED (no column). Applying is the tech-lead's decision (prod shared with dev).

---

## 8 · Existing code that BREAKS on a null `atendimento_partes.cliente_id` (BE-partes must audit — fix-on-contact)
`compradores_service.listar` (`str(r["cliente_id"])`, `:~225`) must skip/filter PJ rows (`.not_.is_("cliente_id","null")` or in-Python filter); `empresas_service.pessoas_do_card`, `documento_checklist_service`, `certidoes` linkage (`vincular_parte` resolves `cliente_id` off the parte), `contrato_gerador/carregador` readers of partes. Scope the audit with `noctus.graph.neighbors`/refs on `atendimento_partes`; fix in the same slice, tests assert PJ rows don't crash PF-only readers.

---

## 9 · Slice ownership (file-disjoint) — Wave B

Rule: a slice edits ONLY its listed files. Shared files have ONE owner; others get their addition delivered as an exact patch applied in **Wave C0** (§10). New files are namespaced per slice. Paths are under `products/social-wiring/`.

| Slice | OWNS (create/edit) | Endpoints / duty |
|---|---|---|
| **BE-certidoes** | `backend/app/modules/card_hub/certidoes_partes_service.py` · `certidoes_partes_router.py` · `certidoes_partes_schemas.py` (NEW) · `backend/app/modules/certidoes/service.py` · `registry.py` · `schemas.py` · `routers/certidoes.py` (only if the bug fixes need it) · `backend/app/modules/card_hub/proveniencia/fontes.py` · `proveniencia/linhagem.py` · `contrato_gerador/validacao_extracao.py` (REGISTRO entry only) · tests `backend/tests/**/test_certidoes_*` (new `test_certidoes_partes_*`) | §1.1-§1.4 + Receita new-emission fix + parser `emissao_data` + manual-PDF emission-date line + Crednet age gate + re-upload clears locked fields + party feed (§1.7). Must keep `certidoes_por_*` shapes and the legacy `matriz` endpoint working. |
| **BE-partes** | `backend/app/modules/card_hub/partes_service.py` · `partes_router.py` · `partes_schemas.py` (NEW) · `compradores_service.py` · `empresas_service.py` (PJ-party awareness only) · `documento_checklist_service.py` (null-safe only) · tests `test_partes_*`, `test_compradores_*` | §2.1-§2.5; §8 audit; exports `listar_partes` (§2.1) |
| **BE-imoveis** | `backend/app/modules/imovel_hub/` NEW: `atendimento_imoveis_service.py`, `atendimento_imoveis_router.py`, `interesses_service.py`, `interesses_router.py`, `proprietarios_service.py`, `similares_service.py`, `imovel_relacionamentos_router.py`, `pessoa_service.py`, `pessoa_router.py` · EDIT `imovel_hub/busca_service.py` (additive keys §0.1) · `imovel_hub/__init__.py` (`register()` `routers=[…]` list) · `backend/app/modules/card_hub/negociacao_service.py` (hook §3.5 only) · `backend/app/modules/leads/routers/leads.py` · `leads/schemas.py` (`LeadCreate.codigo_imovel` required) · `leads/services/leads_service.py` · `leads/services/meta_ingest_service.py` · `backend/app/modules/portal_leads/**` (OLX/imovelweb ingest hooks) · `clientes_service` call sites for the backfill sweep (`app/services/clientes_service.py` — hook only) · Python backfill for `origem="matricula"` | §3, §4, §3.6 |
| **BE-roteiro** | `backend/app/modules/card_hub/roteiros_service.py` · `roteiro_pdf_service.py` · `roteiro_pdf_template.py` (NEW) · `roteiro_schemas.py` (NEW) · tests `test_roteiros_*`, `test_roteiro_pdf_*` | §5.1-§5.2 |
| **FE-certidoes-tab** | `frontend/src/components/card/certidoes/**` (NEW, incl. `CertidoesPartesTab.tsx`) · `frontend/src/hooks/useCertidoesPartes.ts` (NEW) · `frontend/src/types/certidoesPartes.ts` (NEW) · `frontend/src/components/CertidoesPartePanel.tsx` (edit allowed: stop defaulting empty `emitida_em` to today, spec §3.1) · tests alongside | consumes §1; shows stale warning + "re-emitir"; D4 |
| **FE-pessoa-interesses-roteiro** | `frontend/src/pages/PessoaPage.tsx` (NEW) · `frontend/src/components/interesses/**` (NEW: `ImovelInteressesList`, `AdicionarInteresseDialog`, `OrdenarRoteiroDialog`, `ImovelBuscaTypeahead`, `ProprietariosSection`) · `frontend/src/components/imovel/ImovelInteressadosCard.tsx` · `ImovelSimilaresCard.tsx` (NEW) · `frontend/src/pages/ImovelDetalhes.tsx` (mount the two cards) · `frontend/src/components/card/RoteirosSection.tsx` · `CriarRoteiroDialog.tsx` (date + ordering) · `frontend/src/hooks/usePessoa.ts`, `useInteresses.ts`, `usePropriedades.ts`, `useImovelRelacionamentos.ts`, `useRoteiros.ts` (NEW) · `frontend/src/types/pessoa.ts`, `interesses.ts`, `roteiros.ts` (NEW) · **`frontend/src/App.tsx`** (routes `/clientes/:id`, `/vendedores/:id` → `PessoaPage`; `/clientes/revisao` must stay declared BEFORE `/clientes/:id`; no nav entry) | §4, §5 FE |
| **FE-leads-partes** | `frontend/src/components/card/ClienteCardDialog.tsx` + `cardSubpages.ts` (wiring §below) · `AdicionarCompradorDialog.tsx` (PF/PJ toggle, CPF/CNPJ lookup, stale warning) · `frontend/src/pages/leads/components/LeadFormDialog.tsx`, `NovoLeadClienteDialog.tsx` (required imóvel via existing `ImovelCodigoPicker.tsx`, unchanged) · `frontend/src/components/card/AtendimentoImoveisSection.tsx` (NEW) · `frontend/src/hooks/usePartes.ts`, `useAtendimentoImoveis.ts` (NEW) · `frontend/src/types/partes.ts`, `atendimentoImoveis.ts` (NEW) · tests alongside | §2, §3 FE |

**Shared-file rules (the only multi-slice collisions):**
- `card_hub/router.py`, `card_hub/schemas.py`, `backend/app/main.py`: **owned by nobody in Wave B** — the tech-lead applies §10 (C0). Slices test their new routers by mounting `router` in a local `FastAPI()` under `/api/clientes` (or `/api/imoveis`).
- `frontend/src/hooks/useCardHub.ts`, `frontend/src/types/index.ts`: **frozen** — every slice adds NEW hook/type files instead.
- `ClienteCardDialog.tsx`: owner FE-leads-partes. It must (a) render `CertidoesPartesTab` for the `certidoes` subpage (replacing `CertidoesMatrizSection`), (b) render `<AtendimentoImoveisSection/>` on `geral`, (c) render `ImovelInteressesList` above/inside `RoteirosSection` for `roteiros`. Until FE-certidoes-tab / FE-pessoa land those three imports don't exist — FE-leads-partes codes against the exact signatures in §6 and the tech-lead lands it LAST in FE order.
- `imovel_hub/busca_service.py`: BE-imoveis only; BE-roteiro/BE-partes never edit it — they read the additive keys through plain dict access with a `None`-safe fallback so they stay green before BE-imoveis merges.

**Landing order (Wave C):** BE-imoveis → BE-partes → BE-certidoes → BE-roteiro → C0 patch → FE-pessoa → FE-certidoes-tab → FE-leads-partes. BE-certidoes' router imports `partes_service` (BE-partes); its service takes the resolved `partes` list as an argument so unit tests need no import of it.

---

## 10 · Wave C0 — integration patch (tech-lead, after BE slices land; exact content)

1. `card_hub/router.py`: after the existing `router.include_router(...)` block add
   `from app.modules.card_hub.partes_router import router as partes_router`,
   `from app.modules.card_hub.certidoes_partes_router import router as certidoes_partes_router`;
   `router.include_router(partes_router)`; `router.include_router(certidoes_partes_router)`.
   Route-order hazard (module docstring): new literals `/{cliente_id}/partes`, `/{cliente_id}/partes/lookup`, `/{cliente_id}/certidoes/partes…` are ≥3 segments with a distinct 2nd segment — no collision with `/{cliente_id}` or `/tags`; `partes/lookup` MUST be declared before any `/partes/{x}` catch-all inside `partes_router`.
2. `POST …/compradores` handler: body type `CompradorCreateBody` → `ParteCreateBody`; pass `empresa_id=body.empresa_id, cnpj=body.cnpj, razao_social=body.razao_social` to `compradores_svc.adicionar`.
3. `create_roteiro_route`: body `RoteiroCreateBody` → `RoteiroCreateBodyV2`; pass `data_visita=body.data_visita` to `roteiros_svc.criar`. `patch_roteiro_route`: `RoteiroPatchBody` → V2 (`titulo`, `data_visita`); pass `updates.get("data_visita", ...)`. `roteiro_pdf_route`: build `proprietarios_por_codigo = proprietarios_service.por_codigos(client, org_id, [v["codigo"] for v in roteiro["visitas"]])` and `fotos_por_codigo = roteiro_pdf_svc.carregar_fotos(imoveis)`, then `gerar(roteiro, cliente_nome=…, proprietarios_por_codigo=…, fotos_por_codigo=…)`.
4. `imovel_hub/__init__.py` `register()`: `routers=[router, atendimento_imoveis_router, interesses_router, imovel_relacionamentos_router, pessoa_router]` (BE-imoveis owns this edit — listed here only for completeness). `/api/imoveis/{codigo}/interessados|similares|proprietarios` are ≥3 segments ⇒ no clash with `GET /api/imoveis/{codigo}` or `/busca`; `/api/empresas/{id}/propriedades` is 3 segments ⇒ no clash with the empresas router's 2-segment `/{empresa_id}` routes.
5. `main.py`: **no `_MAX_BODY_PATH_OVERRIDES` change** — no new `UploadFile` route in this project (§1.4 reuses `/api/certidoes/resultados/*/upload`, already covered at `main.py:539`).
6. Gates on the MERGED tip: `noctus.dev.gate_sweep`, one E2E contract check per new endpoint (status + exact field names above), `noctus.dev.scan_wiring product=social-wiring`.

---

## 11 · Provisional decisions made while authoring (tech-lead may overturn)

1. **Custom certidão rows stay per card `cliente_id`** (no `empresa_id` on `certidao_matriz_linhas_customizadas`): the card is always a PF; PJ columns share its rows. (A first draft widened the table; reverted — needless schema.)
2. **Re-emitir creates a NEW consulta** instead of mutating the old resultado (history + "failed re-emit never shadows a dated cell").
3. **`arquivo_url` is the opaque storage handle** (as every existing certidões response already returns it) + `tem_arquivo`; the fetchable URL stays the signed `GET …/resultados/{id}/url`.
4. **`/compradores` GET stays PF-only**; PJ + titular are in the NEW `/partes` list (avoids null-`cliente` crashes in existing consumers).
5. **`origem="roteiro"` interesse is reserved**, no writer in v1; roteiro creation does not auto-add interesses.
6. **Past `data_visita` allowed** (a visit already done can be registered).
7. **`PATCH /api/leads/{id}` changing `codigo_imovel` does not rewrite the junction/interesse** (out of scope; flagged for a follow-up).
8. **Similares candidate pool = catalog mirror rows in the target's uf+cidade (cap 2 000)** because `listar_ativos_para_scorer` only returns registered permuta ativos.
9. **Ingest linking is service-level (`vincular_lead`) + backfill-sweep reconcile**, not a DB trigger on `atendimentos` insert (trigger 034 ordering vs lead código arrival is unproven). A trigger is the by-construction upgrade (see `scoped-improvement` in the Wave A return).
10. **Migration 180 trigger also derives `codigo_imovel` from `answers->>'REF'`** so no Meta writer can forget it.
