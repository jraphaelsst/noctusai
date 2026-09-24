# P0c contract — social-wiring empresas · Serasa Crednet · Cartão CNPJ · derivação

> Authored 2026-09-24 by the `architect` advisor against `feat/sw-extr-drive-foundations`. The tech-lead
> (noctusai-3e) ratified it with the decisions in §H. The spec it implements is
> `sw-drive-extraction-2026-09.md` §E1–E8 + §P0c. **Every slice builds to this text; any deviation is
> surfaced, never improvised.** Paths are relative to `products/social-wiring/` unless prefixed `seed/`.

## A. Migration `167_empresas_crednet_cartao_cnpj.sql`

The file is forward-only and idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`,
`SET search_path = social_wiring, public`). It is not applied by the slice (`migrations/APPLIED.md`).
RLS on every new table follows the `imovel_documentos` shape (075): `*_select_own_org FOR SELECT TO
authenticated USING (org_id = public.current_org_id())` plus `*_service_role FOR ALL TO service_role`.
There are no authenticated write policies; the backend writes with service-role (057:152-160).

1. **`empresas`**
   - Columns: `id uuid pk, org_id uuid not null, cnpj text not null CHECK (cnpj ~ '^[0-9A-Z]{12}[0-9]{2}$'),
     razao_social, nome_fantasia, natureza_juridica, data_abertura date, situacao_cadastral text
     CHECK (NULL or IN ('ativa','baixada','inapta','suspensa','nula')), data_situacao_cadastral date,
     motivo_situacao, uf`.
   - Group provenance: `dados_origem text, dados_documento_id uuid, dados_em timestamptz,
     dados_confirmado_por uuid, dados_confirmado_em timestamptz`, then `created_at, updated_at`.
   - `UNIQUE (org_id, cnpj)`.
   - The regex allows alphanumeric CNPJs (`seed/.../documents/cnpj.py:25`). Check digits are validated in the
     app (`cnpj.is_valid`), not in SQL.
   - `dados_documento_id` → `empresa_documentos(id) ON DELETE SET NULL`, added after that table exists.
2. **`cliente_empresa_participacoes`**
   - Columns: `id, org_id, cliente_id → clientes ON DELETE CASCADE, empresa_id → empresas ON DELETE CASCADE,
     participacao_pct numeric(5,2) CHECK 0..100, desde text, uf text, fonte_documento_id → cliente_documentos
     ON DELETE SET NULL, origem text not null CHECK IN ('serasa_crednet','manual','certidao_consulta'),
     confirmado_por, confirmado_em, created_at`.
   - `UNIQUE (cliente_id, empresa_id)`.
   - Indexes `(org_id, empresa_id)` and `(org_id, cliente_id)`.
3. **`empresa_documentos`** mirrors `imovel_documentos` (075, `DocumentoStore`-backed).
   - Columns: `id, org_id, empresa_id → empresas CASCADE, storage_path, nome_original, mime_type,
     tamanho_bytes >= 0, tipo_documento text not null CHECK IN ('cartao_cnpj'), retencao_ate date (111:165),
     enviado_por, deleted_at, delete_motivo, delete_solicitado_por, created_at`.
   - Extraction status (068:135-149, 072:31): `extracao_status CHECK IN ('pendente','processando','ok',
     'sem_dados','erro'), extracao_em, extracao_fonte, extracao_erro, extracao_tentativas int not null default 0`.
   - Discard (069:53-55): `extracao_descartada_em, extracao_descartada_por`.
   - The reading: `extracao_dados jsonb` (full `CartaoCnpjFields` incl. per-field confiança/rótulo).
   - Indexes: pending-extraction (068:152 shape), `(org_id, empresa_id, created_at desc)`, retention (057:127).
   - Plus **`empresa_documento_acessos`**, copying 109:115-141 (`acao IN ('view','download','delete','extract')`).
4. **`empresa_campo_conflitos`**
   - Copies the `imovel_campo_conflitos` shape (154:150+, JSONB values), keyed by `empresa_id`.
   - Pending-only unique index `(empresa_id, campo) WHERE status='pendente'` (138).
5. **`certidao_consultas`**
   - `ADD COLUMN empresa_id uuid REFERENCES empresas(id) ON DELETE SET NULL`.
   - `CHECK (empresa_id IS NULL OR tipo_documento = 'cnpj')`.
   - Index `(org_id, empresa_id) WHERE excluida_em IS NULL` (161 shape).
6. **`certidao_resultados`**: `ADD COLUMN fonte_cliente_documento_id uuid REFERENCES cliente_documentos(id) ON
   DELETE SET NULL` (the Crednet → certidão 9 provenance).
7. **`clientes`**: `nome_mae` plus its five provenance columns (`_origem, _documento_id → cliente_documentos, _em,
   _confirmado_por, _confirmado_em`), the 153:60-79 shape.
8. **`cliente_documentos`**: `extracao_nome_mae, extracao_nome_mae_confianca, extracao_nome_mae_rotulo`, plus
   `extracao_crednet jsonb` (whole reading; precedent `extracao_conjuges` 153:120).
9. **Document types and retention**
   - `cliente_documento_tipos` row `('serasa_crednet','financeiro',1825,false,true,'Serasa Crednet — relatório
     de crédito (PF)')`, 164:53-62 upsert shape.
   - `documento_retencao_politicas`: widen the `superficie` CHECK (111:142-145) with `'empresa'`.
   - Platform rows `(NULL,'cliente','serasa_crednet',1825,…)` and `(NULL,'empresa','cartao_cnpj',1825,…)`,
     `ON CONFLICT … WHERE org_id IS NULL DO NOTHING` (164:65-70).
10. **Backfill** (idempotent, no deletes), per non-deleted CNPJ consulta:
    - Normalize the CNPJ: `upper(regexp_replace(documento,'[.\-/\s]','','g'))`.
    - `INSERT` empresas `DISTINCT ON (org_id, norm)` (razao_social = consulta.nome,
      `dados_origem='certidao_consulta'`) `ON CONFLICT DO NOTHING`.
    - `UPDATE certidao_consultas SET empresa_id` where it is NULL. `cliente_id`/`atendimento_parte_id` stay
      untouched.
    - `INSERT` participações `(cliente_id, empresa_id, origem='certidao_consulta') ON CONFLICT DO NOTHING`.
    - Malformed CNPJs are skipped and reported with `RAISE NOTICE` and a count.
    - Situação is **not** copied (§H4).

**Storage.** `DocumentoStore(table='empresa_documentos', owner_col='empresa_id', prefixo='empresas', bucket=BUCKET,
tipos=('cartao_cnpj',), acessos_table='empresa_documento_acessos', …)`. Keys are
`{org_id}/empresas/{empresa_id}/{doc_id}` (`app/services/documento_store.py:150-172,281`). The existing storage
policy (057:199-235) matches on the org segment, so no new one is needed.
**Out of scope:** `acervos` / `acervo_itens` (a later slice).

## B. Seed extractors (`seed/lib/backend/noctusai_lib/integrations/documents/`)

Template to copy: `matricula_extractor.py:62-257`. One module holds the fields dataclass, the Protocol, the Fake,
`Ladder*Extractor`, `make_*_extractor`, and `_temper` ("not text layer ⇒ not alta"). `ladder.py`
`DocumentTextLadder.to_text()` → `(text, TextSource, err)`, never raises. `real.py` prompt style: `RÓTULO: valor`,
one per line; the pure parser does the rest (no LLM JSON).

**`serasa_crednet.py`** (all dataclasses `frozen=True`):

```python
class OcorrenciaCrednet:  constam: Optional[bool]; quantidade: Optional[int]; valor: Optional[Decimal]; ultimo_registro: Optional[date]
class ParticipacaoCrednet: razao_social: Optional[str]; cnpj: Optional[str]; cnpj_valido: bool; participacao_pct: Optional[Decimal]
                           uf: Optional[str]; situacao_texto: Optional[str]
                           situacao_em: Optional[date]   # Crednet's "SITUACAO DO CNPJ EM" — NOT a closing date (E2)
                           desde: Optional[str]; confianca: ExtractionConfidence
class CrednetFields: consulta_em: Optional[datetime]; protocolo: Optional[str]; cpf: Optional[str]; cpf_valido: bool
    nome: Optional[str]; nome_mae: Optional[str]; data_nascimento: Optional[date]; cpf_situacao: Optional[str]; cpf_situacao_em: Optional[date]
    pendencias_internas: OcorrenciaCrednet; pendencias_financeiras: OcorrenciaCrednet; protesto_estadual: OcorrenciaCrednet; cheques_sem_fundo: OcorrenciaCrednet
    participacoes: tuple[ParticipacaoCrednet, ...]; confiancas: Mapping[str, ExtractionConfidence]; rotulos: Mapping[str, Optional[str]]
    source: TextSource; aviso: Optional[str]; error: Optional[str]; error_message: Optional[str]
    def ocorrencias_constam(self) -> Optional[bool]  # True any constam · False all four False · None any unreadable
```

Exports:
- `parse_crednet(text, source) -> CrednetFields` (pure).
- `CrednetExtractor` (Protocol).
- `FakeCrednetExtractor` (obviously synthetic values).
- `LadderCrednetExtractor`.
- `make_crednet_extractor(*, real, org_id, provider, max_pages=None)`. `max_pages=None` reads every page;
  participações can sit on page 2.

**`cartao_cnpj.py`**, same shape:
- `CartaoCnpjFields` fields: `cnpj`, `cnpj_valido: bool`, `matriz_filial: Optional[Literal['MATRIZ','FILIAL']]`,
  `data_abertura: Optional[date]`, `razao_social`, `nome_fantasia`, `porte`, `natureza_juridica`.
- `situacao_cadastral: Optional[str]`: normalized lower ∈ the 116 vocab, else None (+ raw in rotulos).
- `data_situacao_cadastral: Optional[date]`: "DATA DA SITUAÇÃO CADASTRAL" (E2).
- Also `motivo_situacao`, `uf`, `emitido_em: Optional[datetime]`, `confiancas`, `rotulos`, `source`, `aviso`,
  `error`, `error_message`.

**Check digits** (inside the pure parser; KB `CONTEXT/PRODUCTS/social-wiring/CERTIDOES-LEVANTAMENTO-LEARNINGS.md` §1):
- Every CPF/CNPJ goes through `cpf.is_valid` / `cnpj.is_valid`.
- Identifiers (cpf, cnpj, protocolo) read on the OCR rung are capped at `baixa`.
- A failed check digit ⇒ `*_valido=False`, `baixa`, `aviso='cpf_digito_invalido'|'cnpj_digito_invalido'`.
  The value is **never corrected**.

**Both documents** are image-only PDFs ("Microsoft: Print To PDF"), so the vision rung always runs. Each gets its
own transcription prompt that preserves labels and table rows.

**Also:**
- `capacidades.py`:
  - `CAPACIDADES['serasa_crednet'] = {nome,cpf,data_nascimento,nome_mae,protocolo,consulta_em,participacoes,ocorrencias}`.
  - `CAPACIDADES['cartao_cnpj'] = {cnpj,razao_social,situacao_cadastral,data_situacao_cadastral,…}`.
- `__init__.py`: lazy entries plus exports.

## C. SW wiring

**Routing today.** `FONTES_REGISTRO` (`proveniencia/fontes.py:132-257`) → `TIPOS_EXTRAIVEIS`
(`identidade_extracao_service.py:139-141`). The upload route schedules `extrair_identidade` when
`deve_extrair(tipo)` (`router.py:620-631`), with `extractor_factory(org, tipo)` (`deps.py:89-184`).
`aplicar_campos_ao_cliente(..., campos=...)` (`:686`) is generic over `campos`.

1. **`fontes.py`**
   - `Dominio` (`:50`) += `"empresa"`.
   - `Fonte('serasa_crednet', dominio='cliente', entradas=_ENTRADAS_CLIENTE_UPLOAD,
     extrator='noctusai_lib.integrations.documents.serasa_crednet.make_crednet_extractor',
     origens={'serasa_crednet'}, campos={'nome','cpf','data_nascimento','nome_mae'}, leitura_integral=True)`.
   - `Fonte('cartao_cnpj', dominio='empresa', entradas={Entrada.EMPRESA_CARD_UPLOAD},
     extrator=…make_cartao_cnpj_extractor, origens={'cartao_cnpj'})`.
   - Both in `ROTULOS_TIPO_DOCUMENTO` (`:265`); `'empresa_documentos'` in `TABELA_ENTRADA`.
   - Drop `certidao_pj_situacao_cadastral` from `MANUAL_APENAS` (`:312-322`).
2. **`deps._build_identity_extractor`**: route on `fontes.FONTES[tipo].extrator` when it is not the identity
   factory; widen `ExtractorFactory` (`:86`). **The upload route is unchanged.**
3. **`extrair_identidade`**: after the blob read and access log (~`:1300`),
   `if tipo == 'serasa_crednet': return await crednet_svc.aplicar_leitura(...)`. The sweep and re-run inherit it.
4. **New `card_hub/crednet_service.py` `aplicar_leitura`**, in order:
   - (a) Write `extracao_status/_fonte`, `extracao_nome/_cpf/_data_nascimento/_nome_mae(+confiança/rótulo)` and
     `extracao_crednet`, before touching the cliente.
   - (b) D1: `aplicar_campos_ao_cliente(..., origem='serasa_crednet', campos=CAMPOS_CREDNET)`, with
     `nome_oficial, cpf, data_nascimento` plus a new `nome_mae` `CampoExtraido`. Conflicts → `notificar_conflitos`.
   - (c) Per participação with `cnpj_valido`, upsert `empresas` by `(org_id,cnpj)`. On insert only: razao_social,
     `dados_origem='serasa_crednet'`, **no situação**. Then upsert the participação (`origem='serasa_crednet'`,
     `fonte_documento_id=doc`, pct, desde, uf), fill-empty. Invalid-CNPJ participações go to
     `extracao_crednet.participacoes_rejeitadas`.
   - (d) `certidoes.service.registrar_serasa_de_crednet(db, org_id, cliente_id, doc, leitura)`.
5. **`registrar_serasa_de_crednet`** (certidão 9, one stored copy per E7)
   - Targets: every `cpf` consulta with `cliente_id=X`, not excluded, normalized `documento` == the CPF.
   - Its `serasa` resultado is filled when empty, or when it is unconfirmed, `resultado_origem='ia'`, has a
     non-null `fonte_cliente_documento_id`, and is older.
   - Values:
     - `arquivo_url = doc.storage_path` (same bucket), `arquivo_nome='serasa_crednet.pdf'`, `status='sucesso'`
     - `numero=protocolo`, `emitida_em=consulta_em.date()`
     - `resultado = 'negativa'` if `ocorrencias_constam() is False`, `'positiva'` if True, **NULL** if None
     - `resultado_origem='ia'`, `fonte_cliente_documento_id=doc.id`
   - Manual or confirmed rows are never overwritten.
   - **No consulta yet ⇒ defer (never create one).** `_fan_out_tipos_manuais` (`routers/certidoes.py:221-257`)
     and `criar_consulta_manual`'s inline fan-out (`:524-543`) call
     `service.aplicar_crednet_pendente(db, org_id, consulta)` after inserting placeholders.
   - **Required safety fix:** `delete_storage_files` (`service.py:~625-651`) and the purge delete only keys whose
     second segment is `certidoes` (`deps.py:53` PREFIXO). Otherwise a consulta purge deletes the cliente's
     Crednet.
6. **Cartão CNPJ**: new module `app/modules/empresas/` (`register, router, documentos_service,
   extracao_service`), shaped like `imovel_hub/documentos_service.py:167-316`.
   - The upload stamps `pendente`; a background task runs `extrair_cartao`.
   - Cartão cnpj ≠ empresa cnpj ⇒ `aviso='cnpj_divergente'`, apply nothing.
   - Otherwise D1 at group level: fill empty fields (`dados_origem='cartao_cnpj'`, `dados_documento_id`,
     `dados_em`, `confirmado_*`=NULL). A differing value ⇒ `empresa_campo_conflitos` + notification, through the
     shared conflict writer (§H6).
   - `porte/matriz_filial/emitido_em` stay only in `extracao_dados`.
   - D3 retries: `MAX_TENTATIVAS=3` in `app/services/extraction_sweep.py`.

## D. API endpoints

Card routes use `auth=Depends(get_current_user_org)`, `user, org_id = _auth_parts(auth)`,
`client=Depends(get_card_hub_client)` (`router.py:590-601`) and return a raw dict. Errors: `NotFoundError`→404,
`ValidationError_`→422, `ConflictError`→409. The deal resolves via `resolve_atendimento_id` (`services.py:118-138`).
`cliente_id` is the titular (always a comprador). Auth tests assert a strict `== 401`.

1. **`GET /api/clientes/{cliente_id}/empresas`** (`card_hub/router.py`, service `card_hub/empresas_service.py`)
   - People considered: titular + all partes (both sides) + every vendedor's `conjuge_cliente_id`.
   - Empty when there is no open atendimento or it is ambiguous (like `compradores_service.listar` `:187-238`).

```json
{"atendimento_id": "uuid|null", "referencia": "YYYY-MM-DD",
 "items": [{"empresa": {"id","cnpj","razao_social","nome_fantasia","natureza_juridica","data_abertura","situacao_cadastral","data_situacao_cadastral","motivo_situacao","uf","dados_origem","dados_confirmado_em"},
   "owners": [{"cliente_id","nome","lado":"vendedor|comprador","papel","participacao_pct","origem","certificando": true}],
   "cartao": {"documento_id|null","extracao_status|null","extracao_descartada_em|null","aviso|null"},
   "exige_certidoes": true, "motivo": "ativa|baixada_menos_5_anos|baixada_5_anos_ou_mais|sem_cartao_cnpj|outra_situacao|sem_socio_certificando",
   "certidoes": {"consulta_ids": ["uuid"], "total": 11, "por_resultado": {"negativa":0,"positiva":0,"positiva_com_efeito_de_negativa":0,"negativa_com_homonimos":0,"nao_emitida":0,"pendente":11}}}]}
```

   - Dedupe by `empresa.id` (E4); `owners[]` merges spouses.
   - `exige_certidoes` = E1 passes ∧ ≥1 owner `certificando` (vendedor, cônjuge, comprador when `tem_permuta`).
2. **`POST /api/clientes/{cliente_id}/empresas`** (manual link) `{cnpj, cliente_id (a participant on this card),
   razao_social?, participacao_pct?}`.
   - 201 returns the row shape.
   - 422 for an invalid CNPJ; 404 when the participant is not on the card.
   - Upserts the empresa and a participação with `origem='manual'`.
3. **`GET /api/empresas/{empresa_id}`**, and **`GET /api/empresas/{empresa_id}/documentos`** →
   `{"items":[{…documento_base,"extracao_status","extracao_dados","extracao_descartada_em"}]}`.
4. **Cartão routes** (mirroring `router.py:590-739`)
   - `POST /api/empresas/{empresa_id}/documentos` (multipart `file`, `tipo_documento='cartao_cnpj'`): 201; 422
     for type, mime or size; 404 for a foreign empresa. Schedules extraction.
   - `POST …/{documento_id}/extrair`: re-run; refused while pendente/processando.
   - `POST …/{documento_id}/extracao/confirmar`: stamps `dados_confirmado_por/_em` (D2).
   - `POST …/{documento_id}/extracao/descartar`: sets `extracao_descartada_*`; the reading is kept.
   - `GET …/{documento_id}/url`: 300 s signed URL, access logged.
   - `DELETE …/{documento_id}` `{motivo}`: 204.
   - `main.py` `_MAX_BODY_PATH_OVERRIDES["/api/empresas/*/documentos"]=30MB`.
5. **Certidões**
   - **`POST /api/certidoes/consultas/{id}/vincular-empresa`** `VincularEmpresaRequest{empresa_id: UUID}` (strict).
     - 404 when the empresa or consulta does not exist.
     - 422 unless `tipo_documento=='cnpj'` and the normalized `documento == empresa.cnpj`.
     - Sets only `empresa_id` and returns `success_response(consulta)`.
     - One linking verb serves automated and manual consultas: `criar_consulta` has no link param; every link
       goes through `vincular-*`.
   - **`GET /api/certidoes/empresas/{empresa_id}/resultados`** (`certidoes_por_empresa`, mirroring
     `service.py:2651-2676`).
   - `_fan_out_tipos_manuais` must skip `serasa` for a `cnpj` consulta (E5; fixes a pre-existing bug).
6. **The cliente upload route is reused unchanged for `serasa_crednet`.**

## E. Derivação (`card_hub/contrato_gerador/`)

- **`derivacao.py:1244-1258`**: delete the `if p.lado != "vendedor":` guard. Missing CPF-set certidões ⇒
  `av.falta` for every certificando (antigo proprietário included, via `conferir_pessoa` `:1381`).
- **Empresa model.**
  - Delete the `grupos_pj` block in `conferir_pessoa` (`:1287-1313`).
  - Replace `grupos_pj/classificar_grupo_pj/grupos_pj_exigidos` (`:646-689`) with
    `classificar_empresa(e, referencia, politica) -> motivo` and
    `empresas_exigidas(d, sw, referencia, politica) -> list[EmpresaExigida]`.
  - Owners = DISTINCT participações of `signatarios(vendedores) ∪ their conjuge_cliente_id ∪
    (signatarios(compradores) ∪ cônjuges if tem_permuta)`.
- **E1 classification.**
  - `ativa`/`inapta` (`SITUACOES_PJ_EXIGIDAS`, `politica.py:45`) ⇒ required.
  - `baixada` ⇒ required iff `ha_menos_de_anos(data_situacao_cadastral, referencia, pj_baixada_janela_anos=5)`.
  - NULL situação ⇒ `sem_cartao_cnpj` + `av.falta(f"empresa.{id}.cartao_cnpj", "Cartão CNPJ — {razão social}",
    "empresas")`.
  - `baixada` without a date ⇒ falta `empresa.{id}.data_situacao_cadastral`.
  - Required ⇒ `conferir(owner, e.certidoes, "cnpj", nome)` once per empresa (E4).
  - **referencia = today** (`contrato_gerador/service.hoje()`), per E1.
- **Data loading.**
  - `dados.py`: `Empresa(id, cnpj, razao_social, situacao_cadastral, data_situacao_cadastral, dados_origem,
    dados_confirmado_em, owners, certidoes)` + `DadosContrato.empresas`.
  - `carregador.py` loads participações → empresas → `certidoes_por_empresa`.
  - `tem_pj_certidoes` (`:591-593`) = `bool(empresas_exigidas(...))`.
- **`contexto.py:285-318`.**
  - CPF groups: the strict `idx[t]` over `tipos_exigidos("cpf")`, no `if t in idx`/`continue`. A miss raises
    `ContextoInconsistente`, never a silent skip.
  - PJ groups: iterate `empresas_exigidas`; `em_nome_de = e.razao_social`; `sufixo = SUFIXO_PJ_BAIXADA` for
    `baixada_menos_5_anos`; `tipos_exigidos("cnpj")` = the 11 of `frases.py:365-378` (E5).
- **`validacao_extracao.REGISTRO`** += `(empresa, dados)`, so a machine-pending Cartão blocks generation (D2).
- **Tests** (`tests/modules/card_hub/test_contrato_gerador.py`)
  - `TestSellerCertidoesNaoExigidas` (`:668-722`) → `TestVendedorCertidoesExigidas`.
  - `TestQ9CertidoesDeEmpresa` (`:622-666`) is rewritten against `d.empresas` with an injected `referencia`,
    covering: ativa missing a type, no cartão, spouses sharing one empresa, permuta comprador required, no
    permuta not required.
  - `:770-778` (previous owner not required) is inverted.
  - `fixtures.certidoes_pj` → `fx.empresa(...)`; re-pin the goldens.

## F. Frontend (`frontend/src`)

- **Empresas tab**
  - `components/card/cardSubpages.ts` += `"empresas"` ("Empresas", `Building2`).
  - `ClienteCardDialog.tsx`: `renders.empresas`, `isEmpty` wired as at `:904-906`.
  - `components/ClienteDetailModal.tsx`: `renderEmpresas={() => id && <EmpresasSection clienteId={id}/>}`, the
    `renderCertidoesDoTitular` pattern at `:775-783`.
- **`hooks/useEmpresas.ts`**
  - `useEmpresasDoCard(clienteId)`, key `["sw","clientes",id,"empresas"]`.
  - `useEmpresaDocumentos(empresaId)`, polling while any doc is pendente/processando (`useCardHub.ts:647-661`).
  - Mutations `useUploadEmpresaDocumento`, `useEmpresaExtracao`, `useAdicionarEmpresa`, all invalidating the
    card key.
  - In `hooks/useCertidoes.ts`: `useResultadosPorEmpresa`, `useVincularEmpresa`.
  - Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
- **Components**
  - `components/card/EmpresasSection.tsx`: row per empresa with owners, situação, closing date, an
    `exige_certidoes`/`motivo` badge, the Cartão slot, and certidões.
  - Cartão slot: see §H7 (a generalized `DocumentoTipoSlot`).
  - `CertidoesPartePanel.tsx` (props `:125-141`) gets an `empresaId` mode: manual consulta
    `tipo_documento='cnpj'` → `vincular-empresa`.
  - No seed upload-slot organ exists (`component_list`/`find_reusable_component` checked).
- **Serasa slot**
  - Backend `documento_checklist_service.ITENS` (`:136-163`) += `{"key":"serasa_crednet","label":"Serasa
    Crednet","documento":"serasa_crednet","documentos":("serasa_crednet",)}`, scoped per §H8.
  - `_extras_do_item` (`:374-389`) emits `documentos` slots for items without `campos_todos`.
  - FE `DocumentoChecklistSection.tsx:230` already routes items with `documentos` to `IdentidadeChecklistRow`.
    Verify it tolerates a missing `faltando`/`dica`.
- **Labels in `lib/documentoTipos.ts`**
  - `TIPO_LABEL_CLIENTE` += `cnh:"CNH"`, `cin:"CIN — Carteira de Identidade Nacional"`,
    `serasa_crednet:"Serasa Crednet"`.
  - New `TIPO_LABEL_EMPRESA = {cartao_cnpj:"Cartão CNPJ"}` + a `rotuloTipo` branch for `superficie==='empresa'`.
  - Mirror in backend `documento_retencao.SUPERFICIES/ANCORAS` (`:59`).

## G. Slices

| Slice | Paths | Tests | Collision |
|---|---|---|---|
| **S1 seed** | `seed/lib/backend/noctusai_lib/integrations/documents/{serasa_crednet.py,cartao_cnpj.py,capacidades.py,__init__.py}` | `seed/lib/backend/tests/integrations/documents/{test_serasa_crednet.py,test_cartao_cnpj.py,test_capacidades.py}`, synthetic text only: invalid digit ⇒ baixa and not corrected; OCR ⇒ never alta; three-state `ocorrencias_constam` | additive (C2) |
| **S2a SW backend** | `migrations/167_*.sql`, `app/modules/empresas/**`, `app/modules/card_hub/{crednet_service.py,empresas_service.py,identidade_extracao_service.py,deps.py,router.py,documento_checklist_service.py,proveniencia/fontes.py}`, conflict-writer module (§H6), `app/modules/certidoes/{service.py,schemas.py,routers/certidoes.py}`, `app/services/{documento_retencao.py,extraction_sweep.py}`, `app/main.py` | `tests/modules/empresas/*` (upload, D1 fill/conflict, cnpj_divergente, auth `== 401`), `test_crednet.py`, `test_empresas_card.py`, vincular-empresa, deferred serasa, purge-prefix guard, fontes tests | owns `fontes.py`; codes to §B signatures |
| **S2b derivação** | `app/modules/card_hub/contrato_gerador/{derivacao.py,contexto.py,dados.py,carregador.py,validacao_extracao.py}`, `tests/modules/card_hub/{test_contrato_gerador.py,contrato_gerador_fixtures.py,test_contrato_gerador_endpoints.py}`, goldens | §E rewrites | `carregador` calls S2a's `certidoes_por_empresa`: code to the agreed signature; gates re-run on the merged tip |
| **S3 FE** | `frontend/src/{components/card/{cardSubpages.ts,ClienteCardDialog.tsx,EmpresasSection.tsx,DocumentoTipoSlot.tsx,CertidaoCasamentoSlot.tsx,DocumentoChecklistSection.tsx},components/{ClienteDetailModal.tsx,CertidoesPartePanel.tsx},hooks/{useEmpresas.ts,useCertidoes.ts},lib/documentoTipos.ts,types/empresas.ts}` | colocated `*.test.tsx`: tab visibility, no skeleton over data, polling stops at terminal, motivo badges, labels | none with BE |

## H. Tech-lead decisions (2026-09-24, noctusai-3e)

1. **Empresa docs engine:** `DocumentoStore` (imóvel sibling). Types via CHECK plus the store tuple.
   `NOC-REMEDIATE[dry-documento-store]` stays open.
2. **E1 reference date = today**, per the owner. The assinatura-date measurement at `derivacao.py:671` is replaced.
3. **Backfilled participações** (`origem='certidao_consulta'`) are kept, so existing deals keep their PJ groups.
4. **Backfill does NOT copy the legacy situação.** The Cartão CNPJ is the only source of truth for the closing
   date (E2; the owner proved the Crednet date wrong on case 883). Existing empresas show
   `faltando: cartao_cnpj` until a Cartão is uploaded. This is the honest state, not a regression.
5. **Serasa with no consulta yet:** defer and link at fan-out. With several consultas, fill every empty serasa
   placeholder. Crednet LGPD-deleted ⇒ the linked resultado's `fonte_cliente_documento_id` goes NULL by FK, and
   `arquivo_url` dangling is marked `NOC-REMEDIATE[crednet-lgpd-delete-cascade]` in
   `certidoes/service.py` (destination: this roadmap P1).
6. **N=3 conflict tables ⇒ formalize now (S2a).** Extract one shared conflict writer (open / dedupe-pending /
   notify) used by cliente (138), imóvel (154) and empresa conflitos. The recurrence rule forbids shipping the
   third copy.
7. **Generalize the upload slot now (S3):** `DocumentoTipoSlot`, consumed by the Cartão CNPJ slot and by the
   refactored `CertidaoCasamentoSlot`.
8. **The Serasa checklist item is scoped to certificandos only:** vendedores, their cônjuges, and compradores
   (+cônjuges) when `tem_permuta`. Hidden for everyone else.
9. The storage prefix is per-store (no owners map); noted.
10. Using a vision-read CNPJ as the join key is **accepted with the mitigations**: check digit; the Cartão CNPJ must
    match (`cnpj_divergente`); participações unconfirmed until D2.
11. Motivos `outra_situacao`, `sem_socio_certificando` are accepted. `inapta` is required. Antigo proprietários'
    empresas are included when the previous owner is required.
12. The group-level provenance limit is accepted. Conflicts are per field in `empresa_campo_conflitos`.
13. **LGPD:** S2a files `noctus.dev.lgpd_flag` for `clientes.nome_mae` and the Crednet (1825 d); Cartão CNPJ
    retention is 1825 d.
14. Fix the pre-existing Serasa placeholder on CNPJ consultas (in S2a).
