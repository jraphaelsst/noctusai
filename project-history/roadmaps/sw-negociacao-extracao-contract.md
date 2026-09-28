# Negociação/financiamento extraction contract (social-wiring)

> Written 2026-09-25 by the `architect` advisor, read-only, against `origin/dev@da85e0438`. Paths are relative to `products/social-wiring/backend/` unless they start with `seed/` or `frontend/`. The template is `project-history/roadmaps/sw-drive-extraction-P0c-contract.md`: the same D1, D2 and D3 rules, the same Protocol+Fake+Ladder+factory shape, and the same shared conflict writer. Nothing in §H is decided here. Those are owner questions.

## 0. What already exists (verified)

**Data model: every table is keyed by the atendimento (the deal)**
- **`atendimento_negociacao`** (077:124). It has `valor_negociado NUMERIC(14,2)` (:135), a legacy free-text `parcelas` column (:154), and two "what the buyer said" booleans, `financiamento` (:156) and `fgts` (:162). It has **no provenance columns**. Its single writer is `card_hub/negociacao_service._gravar` (:564-613). The editable fields are listed at :84-101.
- **`atendimento_negociacao_parcelas`** (108:176-233).
  - `tipo` ∈ sinal / intermediaria / financiamento / fgts / saldo / direta / permuta (114:224-231).
  - `valor NUMERIC(14,2) NOT NULL` (108:195). Also `vencimento`, `evento`, `forma_pagamento`, `favorecido_id`, `confissao_divida`, `ordem`, and `dispara_corretagem` (114:234).
  - No provenance. CRUD lives in `negociacao_estruturada_service` (`criar_parcela` :774-822). `valor` is in `_PARCELA_CAMPOS_NAO_NULOS` (:116-118).
- **`atendimento_favorecidos`** (108:130-147: nome, cpf_cnpj, banco, agencia, conta, pix), **`atendimento_intermediarios`** (108:268 plus 114:442-488 and 162:83), and **`atendimento_negociacao_termos`** (114:111: posse, itens_integrantes, ad_corpus, corretagem_contratantes/num_parcelas; plus 163:46).
- **`atendimento_financiamento`** (078:59-86).
  - Columns: `situacao` ∈ pendente/aprovado/recusado, and `fgts BOOLEAN NOT NULL DEFAULT false`.
  - Migration 100:176-180 added `agente_financeiro_id` (→ `agentes_financeiros`, which has `codigo_banco`, 100:75) and `numero_proposta`.
  - Written only by hand, through `financiamento_service.atualizar` (:220-271, CAMPOS_EDITAVEIS :85-97).
- **The deal document store already exists: `atendimento_documentos`** (078:114-140).
  - `DocumentoStore(table='atendimento_documentos', owner_col='atendimento_id', prefixo='atendimentos', tipos=TIPOS_DOCUMENTO, max_bytes=25MB, acessos_table=…)` (`financiamento_service.py:74-83`).
  - Types are validated in code (no CHECK): `TIPOS_ESCRITURA` and `TIPOS_FGTS` (:46-63). It is LGPD-logged, `categoria_lgpd` defaults to `'financeiro'`, and `retencao_ate` is anchored at deal close (`documento_retencao.ANCORAS`, `SUPERFICIES` :61; platform rows 079:190-204).
  - **It has no `extracao_*` columns.** The `atendimento_documento_acessos.acao` CHECK allows only view, download and delete (078:178).
  - Routes are `/api/clientes/{cliente_id}/financiamento[/documentos…]` (`card_hub/router.py:1113-1202`). The deal is resolved through `resolve_atendimento_id` (titular only).

**Generator gates (`contrato_gerador/derivacao.py`)**
- Switches (:589-609): `tem_financiamento` means a parcela with `tipo='financiamento'` exists. `tem_fgts` = tem_financiamento ∧ `d.financiamento.fgts`, where fgts comes from the **078** table, not 077.
- Negociação checks (:1150-1216):
  - `valor_negociado` falta; parcelas falta.
  - Exactly one sinal (`MAIS_DE_UM_SINAL`).
  - Per parcela: valor, and vencimento or evento.
  - Favorecido with conta/pix, banco/agência, and forma_pagamento, for `TIPOS_PAGOS_A_FAVORECIDO={sinal,intermediaria,direta,saldo}` (:75).
  - `EVENTO_CITA_FINANCIAMENTO`; Σ parcelas == valor [Q15].
- `_financiamento` (:1258-1277): the financiamento row must exist and must not be `recusado`. `PARCELA_FGTS_SEPARADA` blocks, per [Q6]: FGTS is part of the financiamento parcela.
- What gets printed (`frases.texto_parcela` :303-340):
  - Financiamento parcela: "…FGTS e financiamento imobiliário" or "…recursos de financiamento imobiliário e/ou moeda corrente".
  - Intermediária with no vencimento: "por ocasião da assinatura do Contrato de Financiamento Imobiliário". **`agente_financeiro`, `numero_proposta` and the bank's rates and term are never printed.**
- Loading: `carregador.py:534`, `:552-567`, `:609-641`. `DadosContrato` (dados.py:480+) has **no `atendimento_id`**.

**D2 gate and provenance registries**
- `validacao_extracao`:
  - `TABELAS` :100-107; `CampoValidavel` :129-170; `_quinteto` :173-199; `REGISTRO` :363-366; `coletar` :517-633.
  - `documentos_de_origem` :635-670 knows only the cliente, imóvel, matrícula and empresa tables.
  - `_filtro_linha` :867-871 filters by `id`, or by `codigo` for the imóvel.
  - `_patch_rejeite` :883-891 sets the value columns to NULL.
  - `listar_conflitos` :730.
- `proveniencia/fontes.py`:
  - `Entrada` :22-49 and `Dominio = cliente|imovel|empresa` :53.
  - `TABELA_ENTRADA` :334-339 has no `atendimento_documentos`.
  - **`MANUAL_APENAS` :361-375 still lists `negociacao_valor`, `negociacao_parcelas`, `negociacao_favorecidos`, `negociacao_termos`, `financiamento` and `intermediarios_*`.**
- Shared conflict writer `app/services/campo_conflitos.py`: descriptors `ConflictTable(table, owner_col)` :69-90 for CLIENTE, IMOVEL and EMPRESA; `registrar_conflito` :113. A fourth table is one more descriptor, not another copy of the code.
- D3: the single policy lives in `app/services/extracao_retentativa.py` (:26-40). **`too_many_vision_pages` is a PERMANENT error there.** There are **already 4 hand-rolled sweeps**:
  - `identidade_extracao_service` :1660/:1719
  - `imovel_hub/matricula_extracao_service` :239
  - `imovel_hub/documentos_service` :807
  - `empresas/sweep_service` :38-80

**Seed facts that constrain the design**
- `transcription.py:523-531`: when more pages need vision than `max_vision_pages`, it returns `error="too_many_vision_pages"`. It **refuses the whole document; it does not read the first N pages**. The ladder's `max_pages` (ladder.py:68-110 → media `real_adapter.py:115,519-522`, default 3) is a spend cap, not a page selector. So a 25-page, image-only financing contract today either errors (cap < 25) or gets 25 vision calls (cap `None` → `MAX_VISION_PAGES=40`, :115). **Page targeting does not exist yet. Building it is a seed change.**
- There is a money parser, `seed/.../domain/texto_ptbr.parse_brl` (:207), and a forward renderer for amounts in words, `reais_por_extenso` (:161). Together they give a deterministic "valor por extenso" cross-check without writing a new parser.
- No doc type for ITBI, bank proposta, financing contract or DPS exists anywhere. There is a cliente-level `'proposta'` type, "Propostas comerciais" (057:96), which is a misfile hazard for the bank proposta.

**FE**
- The `financiamento` tab is "Financiamento/Escritura" (`frontend/src/components/card/cardSubpages.ts:96`). It holds `FinanciamentoPanel.tsx` (`Secao` :296 and a **local `Slot` :342**) and `NegociacaoEstruturadaPanel.tsx` (`ParcelasSection` :302, `CompletudeCard` :271).
- The shared single-doc slot `card/DocumentoTipoSlot.tsx` (:58-86, P0c H7) exists. FinanciamentoPanel does not use it yet.

## A. Doc types, and where they are uploaded

All five documents are **deal facts**. They go into the existing `atendimento_documentos` store and are uploaded on the **Financiamento/Escritura tab**. None of them go on a person or on the imóvel. The imóvel page stays the source of truth for inscrição and matrícula (owner rule R3). The ITBI guide only cross-checks them.

| tipo_documento | Group (tab section) | Extract? | Notes |
|---|---|---|---|
| `guia_itbi` | Escritura | yes | Usually a 1-page scan. The layout varies by município: parse by label synonyms, never by position. |
| `comprovante_itbi` | Escritura | **no** (stored for the archive only) | Payment proof. The contract prints only who pays ITBI (`modelo_texto.py:144/148`). Recommended decision: store, don't extract (§H10). |
| `proposta_financiamento` | Financiamento (new section, shown when the deal has a financiamento parcela or `financiamento.situacao` is set) | yes | JPG/photo. Distinct name from the cliente `'proposta'` (057:96). |
| `contrato_financiamento` | Financiamento | yes, **targeting the Quadro Resumo** (§C3) | 25 image-only pages. **Measure the 883 file size first.** If it is over 25 MB, raise the per-type cap (as empresas did to 30 MB). |
| DPS | — | **never** | It is **not added to any `tipos` tuple**, so the upload is refused by construction. Storage policy: §H8. |

Add a `TIPOS_NEGOCIACAO` tuple next to `TIPOS_ESCRITURA`/`TIPOS_FGTS` and put it in `STORE.tipos`. The `_documento_out` "grupo" mapping (:118) becomes derived from the tuple membership, never from name patterns. Add retention platform rows (superficie `atendimento`, anchor `encerramento`). The day counts are an owner question (§H9).

## B. Field map (document → DB target). Precedence is D1: fill-empty, else conflict.

"Reading-only" means the value is kept in `atendimento_documentos.extracao_dados` (the whole reading), never promoted to a column.

| Fact | Source(s) | DB target | Rule |
|---|---|---|---|
| Valor negociado | contrato_financiamento "VALOR DE COMPRA E VENDA"; guia_itbi "VALOR DA TRANSAÇÃO / DECLARADO"; proposta "VALOR DO IMÓVEL / COMPRA E VENDA" | `atendimento_negociacao.valor_negociado` + quintet | Whichever document is read first fills an empty value. A different later reading ⇒ conflict. Which source is **authoritative** is §H2. 🔴 **Never** map "valor de avaliação", "valor venal" or "base de cálculo" into it. They stay reading-only; each is a documented trap. |
| Financiamento parcela valor | contrato: VALOR FINANCIADO + RECURSOS FGTS; proposta: valor financiado (+FGTS if printed) | `atendimento_negociacao_parcelas` row `tipo='financiamento'`, `valor` + row provenance | [Q6] one parcela = financiado + FGTS (confirm, §H3). No financiamento parcela ⇒ INSERT one (ordem = max+1, same rule as `criar_parcela` :795-803). Exactly one with NULL valor ⇒ fill. Equal ⇒ no-op. Different ⇒ conflict. ≥2 financiamento parcelas ⇒ `aviso='varias_parcelas_financiamento'`, touch no parcela. |
| FGTS used | contrato "RECURSOS DO FGTS" > 0 | `atendimento_financiamento.fgts` (078 table; `derivacao` reads it) | Fill-empty is judged by `fgts_origem IS NULL`, not by the value. A NOT NULL boolean's `false` is indistinguishable from "unset". |
| Agente financeiro | contrato/proposta bank name + code (341 = Itaú) | `atendimento_financiamento.agente_financeiro_id` | Lookup only: exactly one active `agentes_financeiros` row with that `codigo_banco` ⇒ fill-empty. None or ambiguous ⇒ `aviso='agente_financeiro_nao_cadastrado'`. Auto-creating a registry row is §H7. |
| Número da proposta | proposta | `atendimento_financiamento.numero_proposta` | Fill-empty. Vision-read ⇒ confiança `baixa`. |
| Situação do financiamento | — | unchanged | Whether a signed contrato implies `aprovado` is §H6. Nothing is written until decided. |
| Recursos próprios | — | **derived, never stored**: `valor_negociado − Σ(financiamento parcelas)` | Shown in the UI as "a distribuir". Its only use is the §C4 arithmetic guard against the Quadro's printed value. |
| Sinal / intermediária split | no document | manual (stays in `MANUAL_APENAS`) | Offering "intermediária = remainder" as a derived suggestion is §H4. |
| Favorecido bank data | no document (see §H5 for the Quadro's seller credit account) | manual | — |
| Bank loan term (months), rates, amortization system, contract nº, date | contrato/proposta | reading-only | 🔴 The bank's "prazo" (months of amortization) is **not** the parcela's "prazo of N days from CCV signature". Never map it. |
| ITBI alíquota, valor ITBI, vencimento, valor venal, base de cálculo, valor financiado (SFH) | guia_itbi | reading-only | Cross-check inputs (§C4). |
| ITBI compradores/vendedores (nome, CPF), inscrição, matrícula | guia_itbi | reading-only | Cross-checks against deal partes and `imovel_dados` (§C4). The imóvel is never written from here. |
| Intermediação (corretagem, contratantes, parcelas, intermediários), ad corpus, itens integrantes, posse | no document | manual | Unchanged. |

**`fontes.py` changes:**
- `Dominio` += `"atendimento"`. Add `Entrada.ATENDIMENTO_CARD_UPLOAD` and `TABELA_ENTRADA['atendimento_documentos']`.
- Add three `Fonte` entries: `guia_itbi`, `proposta_financiamento`, `contrato_financiamento`. Their `campos` must be ⊆ `CAPACIDADES`.
- `ROTULOS_TIPO_DOCUMENTO` += all four tipos.
- `MANUAL_APENAS`: remove `negociacao_valor`. Replace `financiamento` with `financiamento_situacao` (plus whatever §H6 decides). Keep `negociacao_parcelas`, `negociacao_favorecidos`, `negociacao_termos` and `intermediarios_*`. `test_fontes.py`'s REGISTRO sweep must stay exhaustive.

## C. Migration `171_negociacao_extracao_documentos.sql`

The number comes from `noctus.dev.scaffold_migration` at build time; it is 171 today. Forward-only and idempotent, same header and APPLIED.md posture as 167.

1. **`atendimento_documentos`**: add the 167 empresa_documentos extraction set.
   - `extracao_status` CHECK (pendente, processando, ok, sem_dados, erro), plus `extracao_em`, `extracao_fonte`, `extracao_erro`, and `extracao_tentativas int not null default 0`.
   - `extracao_descartada_em`, `extracao_descartada_por`, `extracao_dados jsonb`, `extracao_aviso text`.
   - Pending-extraction partial index (167:227 shape).
2. **`atendimento_documento_acessos`**: widen the `acao` CHECK with `'extract'`, as 109 did.
3. **`atendimento_negociacao`**: add the `valor_negociado_` quintet (`_origem`, `_documento_id` → `atendimento_documentos ON DELETE SET NULL`, `_em`, `_confirmado_por`, `_confirmado_em`). Shape 153:60-79.
4. **`atendimento_negociacao_parcelas`**: add row provenance `origem`, `documento_id` (→ `atendimento_documentos`, SET NULL), `extraido_em`, `confirmado_por`, `confirmado_em`.
   - **`ALTER COLUMN valor DROP NOT NULL`**, keeping `CHECK (valor IS NULL OR valor >= 0)`. This is a relaxation; no data is deleted.
   - Reason: D2 reject (`_patch_rejeite`) empties value columns, and an extracted parcela must survive rejection with a NULL valor. Derivação already treats `valor is None` as falta (:1171). The manual create API keeps requiring `valor`.
5. **`atendimento_financiamento`**: `fgts_` quintet, `numero_proposta_` quintet, `agente_financeiro_` quintet (153 shape).
6. **`atendimento_campo_conflitos`**: copy the `empresa_campo_conflitos` shape (167:299+, JSONB values, `documento_id_proposto`, polymorphic `fonte_tabela/fonte_id`), keyed by `atendimento_id` with ON DELETE CASCADE.
   - Pending-only unique index `(atendimento_id, campo) WHERE status='pendente'`.
   - `campo` vocabulary: `valor_negociado` · `parcela.<id>.valor` · `financiamento.fgts` · `financiamento.numero_proposta` · `financiamento.agente_financeiro_id`.
7. RLS as 075/167: `*_select_own_org` plus `*_service_role`, no authenticated writes. Retention platform rows for the four new tipos: `ON CONFLICT … WHERE org_id IS NULL DO NOTHING`, with values from §H9.

**Manual writers must stamp provenance (same commit):**
- `negociacao_service` (valor), `negociacao_estruturada_service` (parcela valor create/update) and `financiamento_service.atualizar` (fgts, numero_proposta, agente) stamp `*_origem='manual'` and null `*_confirmado_*` whenever they change a provenance-tracked value. This is the `clientes_service.update_cliente` convention.
- Without it, a human edit to a machine-pending value stays "pending" and blocks generation.

## D. Seed extractors (`seed/lib/backend/noctusai_lib/integrations/documents/`)

The template is `cartao_cnpj.py` (:98-716): a frozen fields dataclass, a pure `parse_*(text, source)`, the Protocol, a Fake with `result=`, a Ladder extractor, a factory `make_*_extractor(*, real, org_id, provider, …)`, and `_temper`. The prompt uses `RÓTULO: valor` lines, and the pure parser does the rest.

1. **`money.py`** (small, shared, pure):
   - `ValorLido{valor: Decimal|None, extenso: str|None, extenso_confere: bool|None, confianca}` and `ler_valor(rotulo_linha)`, reusing `texto_ptbr.parse_brl`, with a tolerant pre-normaliser for "R$1.234,56" / "1.234,56" / OCR spaces.
   - `extenso_confere` = normalized(`reais_por_extenso(valor)`) == normalized(printed extenso). This is the money analogue of a check digit.
2. **`guia_itbi.py`**:
   - Fields: `valor_transacao`, `valor_venal`, `base_calculo`, `valor_financiado_sfh`, `aliquota_pct`, `valor_itbi`, `vencimento`, `inscricao_imobiliaria`, `numero_matricula`, `compradores[(nome, cpf, cpf_valido)]`, `vendedores[…]`, `municipio`, plus `confiancas`, `rotulos`, `source`, `aviso`, `error`.
   - Labels come from a **synonym table per canonical field**, as data, so a new município's layout is extended in one place.
3. **`financiamento_imobiliario.py`**: one module, two readers sharing one Quadro Resumo vocabulary.
   - Fields: `documento: Literal['contrato','proposta']`, `banco_nome`, `banco_codigo`, `numero_contrato`, `numero_proposta`, `data_documento`, `valor_compra_venda`, `valor_avaliacao`, `valor_financiado`, `valor_fgts`, `valor_recursos_proprios`, `prazo_meses`, `taxa_nominal_aa`, `taxa_efetiva_aa`, `sistema_amortizacao`, `compradores[…cpf_valido]`, `vendedores[…]`, `paginas_lidas: tuple[int,...]`, `quadro_encontrado: bool`, `conta_credito_vendedor` (read only; use per §H5), plus the standard tail.
   - Factories `make_contrato_financiamento_extractor(..., janela_paginas=4, max_paginas_visao=8)` and `make_proposta_financiamento_extractor(...)`.
   - Evidence is one bank (Itaú). The synonym table is bank-agnostic by construction, and Itaú is the only calibrated entry. Say so in the docstring.
4. **Page targeting (a new seed capability, required):**
   - Add `paginas: Optional[Sequence[int]]` to `DocumentTranscriber.transcribe` and `DocumentTextLadder.to_text`. It selects which pages are **eligible**. Text-layer pages stay free; vision is applied only to eligible pages that lack text.
   - `too_many_vision_pages` must then be judged against the eligible set, not the whole document.
   - The contract extractor runs deterministically:
     - pass 1: pages 1..4;
     - parse; stop if `quadro_encontrado`, meaning the "QUADRO RESUMO" anchor plus ≥3 of {compra e venda, financiado, FGTS/recursos próprios, prazo} are present with values;
     - otherwise pass 2: pages 5..8;
     - hard stop at 8 vision pages per attempt, never the whole document.
   - Nothing found ⇒ `error='quadro_resumo_nao_encontrado'`, which the SW side adds to `ERROS_PERMANENTES` (a retry cannot move the quadro). `paginas_lidas` is recorded.
   - Calibrate K=4 on 883 in P1 by measuring the quadro's real page index. Do not assume it.
5. **Fabrication guards inside the pure parser (lesson: vision invented values for masked Cartão CNPJ boxes):**
   - The prompt demands `RÓTULO: [ILEGÍVEL]` / `[EM BRANCO]`. Those tokens map to `None`. A value not anchored to its own label line is discarded, never borrowed from a neighbouring box.
   - A value read by vision is capped at `baixa`. It is raised to `media` only if a deterministic check corroborates it:
     - `extenso_confere is True`; or
     - the Quadro sum holds: `valor_financiado + valor_fgts + valor_recursos_proprios == valor_compra_venda`, to the cent. A sum mismatch ⇒ `aviso='quadro_resumo_soma_divergente'` and every money field `baixa`.
     - Never `alta` from vision.
   - Invariants that null the offending field and set an aviso on failure: `valor_financiado ≤ valor_compra_venda`, `valor_financiado ≤ valor_avaliacao` when both are present, `0 < aliquota_pct ≤ 10`, and `valor_itbi ≈ base_calculo × aliquota` (±R$1).
   - CPF/CNPJ go through `cpf.is_valid`/`cnpj.is_valid`. A failed check ⇒ `*_valido=False`, `baixa`. The value is never corrected.
   - **DPS tripwire:** if the transcription carries DPS markers ("DECLARAÇÃO PESSOAL DE SAÚDE", a health questionnaire), the parser returns `error='documento_sensivel_dps'` with **no fields and no text**. The SW side never persists that transcription.
6. `capacidades.py`: add `guia_itbi`, `proposta_financiamento`, `contrato_financiamento` using the canonical names above. `__init__.py`: lazy entries plus exports.

## E. SW wiring

1. **`financiamento_service`**: the upload stamps `extracao_status='pendente'` when `fontes.FONTES[tipo]` exists, then schedules a background task, `negociacao_extracao_service.extrair(doc)`, in a new module `card_hub/negociacao_extracao_service.py`.
   - The extractor factory routes on `fontes.FONTES[tipo].extrator`, the same seam as `deps._build_identity_extractor`.
   - Access is logged with `acao='extract'`.
2. **`negociacao_extracao_service.aplicar_leitura`**, strictly in this order:
   - (a) Write `extracao_dados` (full reading), `_fonte` and `_aviso`, but **not yet `status='ok'`**.
   - (b) **Belongs-to-this-deal check.** At least one CPF on the document (`cpf_valido`) must equal a comprador or vendedor CPF on the deal. If none match ⇒ `aviso='documento_de_outro_negocio'`, apply nothing. This is the `cnpj_divergente` analogue.
   - (c) Cross-document checks against the other extracted docs of this deal (ITBI transação vs contrato compra e venda; ITBI financiado vs contrato financiado; ITBI inscrição/matrícula vs `imovel_dados`). A mismatch ⇒ an aviso on this document, plus a conflict **only** where a DB column is involved. The imóvel is never written.
   - (d) Apply the §B map under D1, through `campo_conflitos.registrar_conflito(ATENDIMENTO, …)` (the new descriptor `ConflictTable('atendimento_campo_conflitos','atendimento_id', has_documento_id_proposto=True)`) and `notificar_conflitos`.
   - (e) Only now set `extracao_status='ok'|'sem_dados'`. An exception in (b)–(d) ⇒ `erro` plus `extracao_erro`, never a false `ok`. **Lesson G6:** Crednet stamped ok before its side effects crashed.
   - A conflict resolver (accept or reject a proposed value) follows the empresas `dados_service` shape; it lives in the same module.
3. **D3 retries, and the sweep formalization (the recurrence rule).**
   - A fifth hand-rolled sweep is forbidden (N=4 already, §0). Extract `app/services/extracao_varredura.py`: candidates = stuck, never-started and retryable-error rows, parametrized by `(table, owner_col, colunas, extrair_fn)`, with retries judged by `extracao_retentativa`.
   - The atendimento sweep uses it. Migrate `empresas/sweep_service` onto it in the same slice, since it has the identical shape.
   - Mark the three other sweeps `NOC-REMEDIATE[dry-extracao-varredura]`.
   - Register through `extraction_sweep.make_sweep_job` with a new JOB_ID/CRON.
4. **D2.** Changes in `validacao_extracao`:
   - `ENTIDADE_NEGOCIACAO` (table `atendimento_negociacao`, keyed by `atendimento_id`), `ENTIDADE_PARCELA` (by `id`), `ENTIDADE_FINANCIAMENTO` (by `atendimento_id`). `_filtro_linha` gains the `atendimento_id` key.
   - `REGISTRO` += `_quinteto(NEGOCIACAO,'valor_negociado')`, a parcela `CampoValidavel(valores=('valor',), origem='origem', documento_id='documento_id', em='extraido_em', …)`, and `FINANCIAMENTO` `fgts`/`numero_proposta`/`agente_financeiro` quintets. For `fgts`, reject resets to `false` via `vazio=(('fgts', False),)`.
   - `documentos_de_origem` gets an `atendimento_documentos` branch, and `TABELA_ENTRADA` gets its entry.
   - `coletar` adds these alvos. This needs `DadosContrato.atendimento_id`, filled by `carregador` (it already resolves it at :516).
   - `listar_conflitos` adds `atendimento_campo_conflitos`.
   - A machine-pending negociação value, or an open conflict, therefore blocks `gerar` (409 `EXTRACAO_PENDENTE_VALIDACAO`) exactly like identity values.
5. **Endpoints**, mirroring empresas `router.py` (:141-230). All take `auth=Depends(get_current_user_org)`. `ValidationError_` ⇒ 400 (P0c §I5). Auth tests assert strict `== 401`.
   - `POST /api/clientes/{cliente_id}/financiamento/documentos/{doc_id}/extrair` re-runs extraction. It is refused while the status is pendente or processando.
   - `…/extracao/confirmar` stamps `confirmado_*` on every still-pending value whose `_documento_id == doc_id`.
   - `…/extracao/descartar` sets the discard columns and keeps the reading.
   - `GET /api/clientes/{cliente_id}/negociacao/conflitos`; `POST …/conflitos/{id}/resolver {decisao}`.
   - `obter()` of financiamento adds `extracao_status`, `extracao_dados`, `extracao_aviso` and `extracao_descartada_em` to each document. `obter_estruturada` adds `origem`, `confirmado_em` and `a_distribuir` (the derived remainder) to parcelas.
6. **LGPD.** S2 files `noctus.dev.lgpd_flag` for:
   - bank documents holding income and financing data (categoria `financeiro`);
   - the DPS exclusion;
   - third-party egress: the vision provider sees at most 8 pages of the contract.

## F. FE (`frontend/src`)

- **`FinanciamentoPanel.tsx`**: replace the local `Slot` (:342) with the shared `DocumentoTipoSlot`. That makes it the third consumer; the recurrence rule makes the swap mandatory.
  - Add the `TIPOS_NEGOCIACAO` section.
  - Per slot, show extraction status, the aviso in pt-BR, "Confirmar leitura" / "Descartar" / "Reler", and polling until the status is terminal (P1 G2 lesson; `useCardHub.ts:647-661` pattern).
  - Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
- **`NegociacaoEstruturadaPanel.tsx`**:
  - A provenance badge on `valor_negociado` and on each parcela (from `origem`, pending vs confirmed).
  - A read-only "Recursos próprios a distribuir: R$ X" line.
  - A conflict banner linking to resolve.
  - Parcela rows render `valor = null` as "—, falta".
- `hooks/useFinanciamento.ts`: new mutations (extrair, confirmar, descartar) and `TIPO_LABEL` entries. `hooks/useNegociacao.ts`: conflicts query plus resolve mutation. `lib/documentoTipos.ts` labels.
- **No DPS option in any picker.**

## G. Slices (file-disjoint; migration and APPLIED.md owned by S2)

| Slice | Paths | Tests (acceptance) | Collision |
|---|---|---|---|
| **S1 seed** (engineer-seed) | `seed/lib/backend/noctusai_lib/integrations/documents/{money.py,guia_itbi.py,financiamento_imobiliario.py,capacidades.py,__init__.py,transcription.py,ladder.py}` | `seed/lib/backend/tests/integrations/documents/test_{money,guia_itbi,financiamento_imobiliario,transcription_paginas}.py`, synthetic text only. `paginas=` never visions an ineligible page. The 25-page all-vision case with window 4 makes ≤8 vision calls and never returns `too_many_vision_pages`. `[ILEGÍVEL]` ⇒ None. Sum mismatch ⇒ aviso + baixa. Extenso agreement ⇒ media. Vision never `alta`. Bad CPF DV ⇒ not corrected. DPS text ⇒ `documento_sensivel_dps` with no fields. Existing transcriber tests stay green (default `paginas=None` keeps behaviour byte-for-byte). | 🔴 `transcription.py` is in flight on `feat/sw-p1-fixes-2`, `ladder.py` on `feat/sw-p1-fixes-3`. **Sequence S1 after both integrate** (C3), or rebase before touching those two files. |
| **S2 SW backend** (backend-engineer) | `migrations/171_*.sql`, `migrations/APPLIED.md`, `app/modules/card_hub/{negociacao_extracao_service.py,financiamento_service.py,negociacao_service.py,negociacao_estruturada_service.py,router.py,deps.py,proveniencia/fontes.py}`, `app/services/{campo_conflitos.py,extracao_varredura.py,extracao_retentativa.py,documento_retencao.py}`, `app/modules/empresas/sweep_service.py`, `app/main.py` (body cap) | `tests/modules/card_hub/test_negociacao_extracao.py`: fill-empty for valor/parcela/fgts/proposta; conflict on differing values; `documento_de_outro_negocio` applies nothing; ≥2 financiamento parcelas ⇒ aviso, no write; exception in apply ⇒ `erro`, never `ok`; manual edit stamps `origem='manual'`; D3 cap via the shared sweep; empresas sweep parity unchanged. Routes: auth `== 401`, 400 on a bad tipo, DPS refused. **At least one FK-enforcing realdb test** (`NOCTUS_REALDB_TESTS=1`) covering the `*_documento_id` FKs (P1 G5: the mock hid an FK bug). Fontes REGISTRO sweep exhaustive. | Codes to §D signatures. `feat/sw-p1-fixes-2` touches `empresas/extracao_service.py` (not `sweep_service.py`): C1. |
| **S2b gate** (backend-engineer) | `app/modules/card_hub/contrato_gerador/{validacao_extracao.py,dados.py,carregador.py}`, `tests/modules/card_hub/{test_validacao_extracao*.py,contrato_gerador_fixtures.py}`, `proveniencia/linhagem.py` | A pending extracted valor/parcela/fgts ⇒ `gerar` 409. Accept ⇒ 200. Reject ⇒ valor NULL ⇒ falta `negociacao.parcela.<id>.valor`. Open atendimento conflict blocks. Goldens unchanged for manual-only fixtures. | `derivacao.py`, `frases.py`, `test_contrato_gerador.py` are in flight on `feat/sw-gerar-crash-destino`. S2b must **not** touch them (no derivação change is needed). Merge-tip gate re-run is mandatory. |
| **S3 FE** (frontend-engineer) | `frontend/src/components/card/{FinanciamentoPanel.tsx,NegociacaoEstruturadaPanel.tsx}`, `frontend/src/hooks/{useFinanciamento.ts,useNegociacao.ts}`, `frontend/src/lib/documentoTipos.ts`, `frontend/src/types/{financiamento.ts,negociacaoEstruturada.ts}`, colocated `*.test.tsx` | Slot shows status and stops polling at terminal. No skeleton over data. Confirmar/Descartar call the right routes. Provenance badge. `a_distribuir` line. `valor=null` renders as falta. No DPS in the picker. | `cardSubpages.ts` is touched by `feat/sw-gerar-crash-destino`. S3 must not edit it (no new tab). Codes to the §E5 JSON shapes. |

**Gates on the merged tip:** `noctus.dev.gate_sweep` (social-wiring pytest and vitest, seed-lib, vite build), then `predeploy_check social-wiring`. Migration 171 is applied only by the tech-lead, via `migrate_product`.

**E2E (the P1 protocol: uploads only, never typing an extractable value):**
1. On the `[TESTE P1] 883` card, upload in the Financiamento/Escritura tab: `guia_itbi`, `comprovante_itbi`, `proposta_financiamento`, `contrato_financiamento`.
2. Score against `~/.noctusai/private/answer-keys/883.json`: `valor_negociado`, financiamento parcela valor, `financiamento.fgts`, agente, número da proposta. Record `paginas_lidas`, vision calls and cost per document.
3. Try to upload a DPS: it must be refused.
4. Owner-authorized typing of the manual residue only: sinal/intermediária split and events, favorecido bank data, ad corpus, itens integrantes, intermediação.
5. Resolve D2, generate, and diff with `tests/e2e_contrato/harness.py` against the REV FINAL: the parcelas block and the price must match 100%.
6. Append the scorecard to `project-history/roadmaps/sw-drive-extraction-P1-883-log.md`.

## H. Owner questions (the contract does not decide these)

1. **Timing.** The CCV is normally signed **before** the bank contract and the ITBI guide exist. For live deals, do these documents *source* the CCV values (useful for backfilling closed folders), or only *reconcile* them after signature (conflict when they differ)? The design supports both through D1. The answer decides whether a missing bank document is ever a falta.
2. **Authority for valor negociado** when the documents disagree: financing contract "compra e venda" vs ITBI "valor da transação" vs proposta vs the negotiated CCV price.
3. Confirm [Q6] on the 883 evidence: financiamento parcela = valor financiado **+** FGTS.
4. May the system offer "intermediária = valor − sinal − financiamento" as a derived suggestion (origem `derivado`), or must it stay typed?
5. If the Quadro Resumo prints the seller's credit account, may it fill a favorecido (matched to a vendedor by CPF)?
6. Does a signed financing contract, or a proposta marked approved, set `financiamento.situacao='aprovado'`?
7. When the bank is not in `agentes_financeiros`: auto-create the row, or aviso only?
8. **DPS.** E7 says "every Drive file is stored in SW", but DPS is LGPD art. 11 sensitive health data with no contract purpose. Recommendation: never store it (upload refused; the acervo marks it `excluido_lgpd`). If a DPS reaches a slot misfiled, it is soft-deleted with motivo `dps_lgpd_sensivel` after a human confirms. Confirm, given the delete-no-data rule.
9. Retention days for the four new tipos. The 079 precedent: escritura/pacto 3650, financeiro 730.
10. Confirm `comprovante_itbi` as archive-only (no extraction).

## I. Recommended tech-lead calls (mine; ratify or amend)

- Deal documents live in `atendimento_documentos`. Do not create a new store (`DocumentoStore` reuse; `NOC-REMEDIATE[dry-documento-store]` stays open).
- The fourth conflict table goes through the shared writer as a descriptor. The fifth extraction sweep **must** go through a new shared `extracao_varredura` (recurrence rule).
- `parcelas.valor` becomes nullable. It is the only way to honour D2 reject without deleting a row.
- Page targeting is a seed capability (`paginas=`), not a product workaround. The 25-page cost cap is ≤8 vision pages, deterministic, calibrated on 883.
- Money precision comes from deterministic checks (extenso, Quadro sum, cross-document equality), never from a model's self-reported confidence.

## Owner answers (2026-09-25), binding on every slice
- H2: valor negociado has NO authoritative document. Any disagreement between contrato de financiamento / guia ITBI / proposta (or with an existing value) ⇒ conflict for a human.
- H4: YES, offer intermediária = valor − sinal − Σ financiamento as a derived suggestion (origem `derivado`, D2-pending).
- H5: YES, the seller credit account printed in the Quadro Resumo fills a favorecido, matched to a vendedor by CPF (D1 + D2).
- H6: YES, a signed contrato de financiamento sets `financiamento.situacao='aprovado'` (with provenance).
- H7: YES, auto-create the `agentes_financeiros` row (nome + código do banco) when missing, logged.
- H8: DPS is NEVER stored: upload refused by construction; the acervo marks it excluded-LGPD.
- Owner's framing: "everything we can automate to make our RE agents' and my jurídico's life easier". Prefer automating a derivable fact, always under D1/D2.
- H1 (owner, confirmed): a missing bank/ITBI/proposta document is NEVER a falta for the CCV; first arrival fills, later ones reconcile. (Was: re-asked in plain words; the D1 design (first document fills, later ones reconcile via conflict) holds either way. A missing bank document is NOT a falta for the CCV until the owner says otherwise.
- H3, H9, H10 use the architect's defaults unless the owner overrides (H3 financiamento parcela = financiado + FGTS, to be checked on 883; retention per the 079 precedent; comprovante_itbi archive-only).
