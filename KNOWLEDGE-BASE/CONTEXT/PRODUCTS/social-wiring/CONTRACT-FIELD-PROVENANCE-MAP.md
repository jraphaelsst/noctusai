# Contract field provenance map — F5 instrument generator (`card_hub/contrato_gerador`)

> Verified live 2026-09-17. Home: `CONTEXT/PRODUCTS/social-wiring/` — this is a
> per-product DATA-PROVENANCE map tightly coupled to social-wiring's own schema
> (`atendimento_negociacao_termos`, `imovel_dados`, `matricula_ato_detalhes`,
> `certidao_consultas`…) and to one product's UI (`/clientes`, `/matriculas`,
> `/certidoes`, `/imoveis`, `/configuracoes`), same shape as the sibling
> `INTEGRATIONS-MULTI-ACCOUNT.md` in this folder — **not** `PATTERNS/backend/`,
> which is reserved for cross-product-reusable seams (`photo-editing-seed.md`
> documents a DI+adapter shape other products can consume; this doc has no
> such reusable shape — it is an inventory of ONE product's field wiring).

## 0 · Executive summary

The generator (`products/social-wiring/backend/app/modules/card_hub/
contrato_gerador/`) is deployed; its 6 spec §1.3 variants pass end-to-end with
synthetic fixtures (`derivacao.py`/`contexto.py` are pure functions over
`DadosContrato` — see that module's own docstring). **In production it has
generated zero contracts**, and this map's finding is that the root cause is
**not** missing storage — migrations 114–118 gave every field spec §6.1 named
"MISSING" a real column (see `dados.py`'s module docstring, verified below
row-by-row) — the root cause is that **no extracted suggestion has ever been
promoted into the confirmed table the generator reads**:

- 30 matrícula act-detail suggestions (`matricula_ato_detalhes`, migration 115), **0 confirmed** via `PUT /api/matriculas/atos/{ato_id}/detalhes`.
- 130 certidão results, 21 with an AI-suggested `resultado` (a verdict), **0 confirmed** via `PATCH /api/certidoes/resultados/{resultado_id}`.
- `imovel_dados` — **0 rows**. No imóvel has ever had `PATCH /api/imoveis/{codigo}/dados` called on it, so `matricula_numero`/`numero_registro_imoveis`/`situacao_onus`/`titulo_aquisitivo_texto`/`onus_credor` are all unset for every deal.
- 0 of 8 matrícula extractions are linked to an imóvel's contract selection (`GET/PUT /api/matriculas/contratos/{contrato_id}/atos`).
- 0 of 1 393 `clientes` rows have a confirmed CPF **or** RG **or** endereço. CPF/RG have an extraction+confirm path (migration 097) that has simply never been clicked; endereço has **no extraction path at all** — see row `p.endereco` below. *(2026-09-22: migration 153 added one — comprovante de endereço; and D1 now fills every empty identity field from any read, machine-pending for the validation gate.)*
- All 5 genuine matrículas carry literal `**bold**` Markdown markers in `texto_extraido` with `formatacao='[]'` — the contract quotes that text VERBATIM by design (`{{r imovel.descricao_matricula }}`, a docxtpl rich-text slot). `NOC-REMEDIATE[transcricao-formatacao-backfill]` understates scope: this is 100% of the real (non-fixture) corpus, not 5 stray rows.

**Finding: the spec (`products/social-wiring/contracts/f5-template-spec.md`,
2026-09-15) is itself already stale on ~30 of its "MISSING" rows.** Six
backend slices (migrations 114–118, landed after the spec) gave real storage
to spec §6.1 items #1–3 (permuta parcela type + multi-asset + per-imóvel act
role), #6 (`juros_am`/`confissao.garantia`), #8 (título-aquisitivo confirmed
text), #11–14 (ônus/posse detail, imóvel-level certidões), #15 (a real
`negativa_com_homonimos` enum value, migration 116 — §2.5's "MISSING" note is
stale), #17 (previous-owner rule, `titulo_service.antigos_proprietarios`),
#18 (titular certidões, migration 116), #21–26 (intermediário qualification,
favorecido↔intermediário link, corretagem payer/marcos/rescisão %, org
settings), and switches §1.1 `ad_corpus`/`tem_itens_integrantes`/
`tem_declaracao_partes` (all three now real `derivar_switches` outputs, none
guessed). `derivacao.py`'s own module docstring says this outright: *"NOTHING
HERE IS 'NOT IN THE SYSTEM' ANY MORE… a gap is now always an un-filled FORM,
never a missing column."* Two items remain genuinely absent by design —
procurador/inventariante qualification wording (`PAPEIS_SEM_REDACAO`) and two
stored-but-unwritten clauses (`onus_quitacao='ja_quitado'`,
`obrigacoes_vendedor`, `permuta_obrigacoes_entrega` — stored, no clause text
exists for them in any sample contract). See §4 for the full ranked gap list.

## 0a · File → contract coverage after the 2026-09-22 extraction wave (authoritative)

> Supersedes the "0 confirmed / never promoted" picture above for everything a
> DOCUMENT can supply. Roadmap + owner decisions:
> `project-history/roadmaps/sw-extraction-contract-gate-2026-09.md`
> (migrations 153 identity · 154 imóvel · 155 certidões · 156 validation ledger).

**Write policy (owner D1).** An extracted value fills an EMPTY contract column directly,
with provenance (`<campo>_origem` = source document tipo / `ia` / `api` / `sugerido`,
`_documento_id`, `_em`), unconfirmed. A column a human set (`origem='manual'`) or an
earlier extraction set to a different value is never overwritten: a conflict row
(`cliente_campo_conflitos` / `imovel_campo_conflitos`) opens and an admin is notified.
A human edit always stamps `manual` and is never re-prompted. Failed extractions retry
automatically at most 2× (D3), then stay `erro` for a human.

**Validation gate (owner D2).** "Gerar versão" first calls
`GET /api/clientes/{id}/contratos/{contrato_id}/validacao-extracao`: every
contract-feeding value that is machine-set and unconfirmed is listed with its source
document; per-field ✓/✗ plus accept-all / reject-all. Accept stamps
`_confirmado_por/_em`; reject clears value + provenance (the field becomes `faltando`;
an inline input writes it back as `manual`). Every decision is appended to
`social_wiring.extracao_validacoes` (the refinement ledger). Open conflicts on contract
fields also block. The backend refuses `gerar` with 409 `EXTRACAO_PENDENTE_VALIDACAO`
while anything is pending — the FE cannot bypass it. Registry:
`card_hub/contrato_gerador/validacao_extracao.py` (derived from what `carregador.py`
loads; a test keeps the two in lockstep).

<!-- AUTOGEN:fontes-secao-0a:begin -->
<!-- DO NOT EDIT BY HAND — regenerate via `app.modules.card_hub.proveniencia.linhagem.bloco_secao_0a()` (pinned by `tests/modules/card_hub/test_proveniencia_kb_sync.py`). -->

| Tipo de documento | Domínio | Campos reivindicados | Extrator | Origens gravadas | Entradas |
|---|---|---|---|---|---|
| RG (`rg`) | cliente | `cpf`, `data_casamento`, `data_nascimento`, `estado_civil`, `genero`, `nacionalidade`, `nome`, `profissao`, `regime_bens`, `rg`, `rg_orgao` | `noctusai_lib.integrations.documents.factory.make_identity_extractor` | `rg` | `cliente_card_upload`, `parte_painel_upload` |
| CPF (`cpf`) | cliente | `cpf`, `nome` | `noctusai_lib.integrations.documents.factory.make_identity_extractor` | `cpf` | `cliente_card_upload`, `parte_painel_upload` |
| CNH (`cnh`) | cliente | `cpf`, `data_casamento`, `data_nascimento`, `estado_civil`, `genero`, `nacionalidade`, `nome`, `profissao`, `regime_bens`, `rg`, `rg_orgao` | `noctusai_lib.integrations.documents.factory.make_identity_extractor` | `cnh` | `cliente_card_upload`, `parte_painel_upload` |
| Certidão de casamento (`certidao_casamento`) | cliente | `conjuge`, `cpf`, `data_casamento`, `data_emissao`, `data_nascimento`, `estado_civil`, `genero`, `nacionalidade`, `nome`, `profissao`, `regime_bens`, `rg`, `rg_orgao` | `noctusai_lib.integrations.documents.factory.make_identity_extractor` | `certidao_casamento` | `cliente_card_upload`, `parte_painel_upload` |
| Certidão de nascimento (`certidao_nascimento`) | cliente | `cpf`, `data_casamento`, `data_emissao`, `data_nascimento`, `estado_civil`, `genero`, `nacionalidade`, `nome`, `profissao`, `regime_bens`, `rg`, `rg_orgao` | `noctusai_lib.integrations.documents.factory.make_identity_extractor` | `certidao_nascimento` | `cliente_card_upload`, `parte_painel_upload` |
| Comprovante de endereço (`comprovante_endereco`) | cliente | `endereco` | `noctusai_lib.integrations.documents.address.find_endereco` | `comprovante_endereco` | `cliente_card_upload`, `parte_painel_upload` |
| Matrícula do imóvel (`matricula`) | imovel | `numero_matricula` | `noctusai_lib.integrations.documents.matricula.find_matricula` | `ia`, `manual`, `matricula` | `imovel_page_upload`, `matriculas` |
| Guia do IPTU (`guia_iptu`) | imovel | — | `app.modules.imovel_hub.documentos_service.extrair_estrutura` | `ia`, `manual` | `imovel_page_upload` |
| CND de IPTU (`cnd_iptu`) | imovel | — | `app.modules.imovel_hub.documentos_service.extrair_estrutura` | `ia`, `manual` | `imovel_page_upload` |
| CND de condomínio (`cnd_condominio`) | imovel | — | `app.modules.imovel_hub.documentos_service.extrair_estrutura` | `ia`, `manual` | `imovel_page_upload` |

**Manual-only — no document carries it (by design, not a gap):** `assinatura_data`, `certidao_pj_situacao_cadastral`, `confissao`, `contrato_modelo`, `financiamento`, `intermediarios_comissao`, `intermediarios_qualificacao`, `matricula_atos_selecionados`, `negociacao_favorecidos`, `negociacao_parcelas`, `negociacao_termos`, `negociacao_valor`, `org_dados_cadastrais`, `parte_email`, `parte_papel_no_card`, `permuta_ativo_endereco`, `permuta_termos`, `politica_constantes`, `posse`, `testemunhas`.
<!-- AUTOGEN:fontes-secao-0a:end -->

**Proof harness.** `products/social-wiring/backend/tests/e2e_extracao/` — a fictional
document set (text-layer and scan variants) with an answer key (`esperado.json`) and
`verificar.py`, which scores a live DB field by field (value + provenance).

## 1 · How to read the table

- **status** ∈ `extracted_and_confirmable` (an extractor writes a suggestion;
  a named UI action promotes it to the confirmed column the generator reads)
  · `extracted_but_no_promotion_path` (a suggestion exists but nothing writes
  it to where `carregador.py` reads — a real bug) · `manual_entry_only` (a
  human types it directly into a form; no extractor exists) ·
  `no_source_yet` (spec §6.1 leftover with no storage and no UI at all).
- **clause** cites `products/social-wiring/contracts/f5-template-spec.md`
  §2.x (the ordered clause skeleton) — **not reproduced verbatim** here (that
  file is gitignored, sits beside real signed samples, and carries personal
  data in its own worked examples; this doc cites section numbers and
  boilerplate-only excerpts, never a value from a real contract).
  §2.1 = header/qualification (before the first numbered clause).
- **extractor code path** and **confirmed storage** are `file:line` as of
  this branch's HEAD; re-verify before citing in a ticket — line numbers
  drift.
- Every table.column below is schema `social_wiring` (`app/modules/*/migrations` under `products/social-wiring/backend/migrations/`) unless stated.
- A row's placeholder name matches spec §3 where the implementation agrees
  with the spec; where the shipped code diverges (composes a value spec §3
  modelled as structured data into one pre-formatted string instead), the row
  says so — the CODE is source of truth, not the spec (CLAUDE.md §1).

## 2 · The provenance table

### Contrato / assinatura (spec §3 rows 1–8; clauses §2.13/§2.15/§2.17)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `assinatura.data` / `assinatura_data` | §2.17 | none — operator judgment call | — | `atendimento_contratos.assinatura_data` (migration 114) | `PATCH /api/clientes/{cliente_id}/contratos/{contrato_id}` (`card_hub/router.py:1320`); falls back to "today" (`service.hoje`) when unset, and an explicit value in the generate-request body wins over both | `manual_entry_only` |
| `assinatura.local` | §2.17 | none — org configuration | — | `org_dados_cadastrais.endereco_cidade` | `PUT /api/settings/imobiliaria` (`settings_router.py:1592`) | `manual_entry_only` |
| `assinatura.plataforma_nome` / `assinatura.plataforma_url` | §2.13 | none — org configuration | — | `org_dados_cadastrais.plataforma_assinatura_nome` / `_url` (migration 117) | `PUT /api/settings/imobiliaria` | `manual_entry_only` |
| `foro.comarca` | §2.17 | derived, not extracted | `contexto.py:386` (`{cidade}/{uf}` of `imovel.endereco`) | derived at render time from `imovel_dados`/`imoveis` — no independent storage | (none — always derived; the imóvel address rows below feed it) | `extracted_and_confirmable` (via the imóvel address rows) |
| `cl.<key>.ORD` / `cl.<key>.ref` (16 keys) | §4 | derived | `numeracao.py::numerar_clausulas` | none — pure function of the switches | — | n/a (derivation, not a data field) |
| `par(<key>)` | §2.0 | derived | `numeracao.py::ContadorParagrafos` | none | — | n/a (derivation) |
| switches `tem_*`, `a_vista`, `ad_corpus` | §1.1 | derived | `derivacao.py:284 derivar_switches` | none — computed from the rows below every render; `ad_corpus` reads `atendimento_negociacao_termos.ad_corpus` (migration 114, tri-state) | `PUT /api/clientes/{cliente_id}/negociacao/termos` (`negociacao_estruturada_router.py:67`) sets `ad_corpus`/`itens_integrantes`/etc.; the rest derive from parcelas/financiamento/intermediários | `extracted_and_confirmable` for `ad_corpus`; the rest `manual_entry_only` (derived from manually-entered parcela types) |
| `modalidade_assinatura` → `tem_assinatura_digital` (migration 157) | §2.13/§2.17 | none — operator choice per contract | — | `atendimento_contratos.modalidade_assinatura` (`digital` default \| `fisica`) | `PATCH /api/clientes/{cliente_id}/contratos/{contrato_id}`; going `fisica` under a live envelope is 409 `CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO` | `manual_entry_only` — `fisica` drops the §2.13 clause (numbering re-flows) and swaps the §2.17 closing/signature block |
| `vias` (física) | §2.17 | derived | `contexto.py::montar_contexto` — one per signer (`len(vendedores)+len(compradores)`), min 2, `numero_com_extenso(…, largura=2)` | none | — | n/a (derivation) |
| `V_assinantes_fisicos` / `C_assinantes_fisicos` (`s.nome`, `s.documento`), `linha_assinatura` (física) | §2.17 | derived from the partes rows | `frases.py::assinante_fisico` / `documento_linha` (NOME upper + "CPF …"; no e-mail); `frases.LINHA_ASSINATURA` | none (reads the partes' `nome_oficial`/`cpf`) | — | `manual_entry_only` (via the partes rows) |
| `testemunhas_fisicas` (`t.nome`, `t.documento`) (física) | §2.17 | derived from the testemunhas rows | `frases.py::testemunha_documento_linha` ("CPF … / RG …", or just the one present) | `org_testemunhas.{nome,cpf,rg}` | same endpoints as the Testemunhas rows | `manual_entry_only` — the física block is the ONE place a witness CPF is printed (beside the RG) |
| `contrato.modelo` (check only) | — | none | `derivacao.py:321 modelo_derivado` | `atendimento_contratos.modelo` | `PATCH /api/clientes/{cliente_id}/contratos/{contrato_id}`; `_contrato` only **warns** on mismatch (`MODELO_DIVERGENTE`), never blocks | `manual_entry_only` |

### Imóvel objeto (spec rows 9–18; clause §2.2)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `imovel.titulo_curto` | §2.2 | derived from `imoveis`/`imovel_dados` | `contexto.py:164` | `imoveis.empreendimento` + `imovel_dados` address (`complemento`) | catalog listing form (`/imoveis`) | `manual_entry_only` |
| `imovel.cidade` / `imovel.uf` / `imovel.endereco_curto` | §2.2/§2.7/§2.8/§2.12 | none | `carregador.py:200 _endereco(catalogo)` | `imoveis.cidade`/`uf`/`logradouro`/`numero` (the catalog listing) | `/imoveis` catalog edit form | `manual_entry_only` |
| `imovel.descricao_matricula` (`{{r … }}` rich-text slot) | §2.2/§2.3 (permuta) | matrícula document (AI transcription) | `matriculas/estrutura_service.py:364 criar_extracao_de_documento` → text lands in `matricula_extracoes.texto_extraido` + `formatacao` | act selection: `atendimento_contrato_matricula_atos` (migration 115) — **not** the raw extraction; the CONTRACT'S selection of specific atos | `PUT /api/matriculas/contratos/{contrato_id}/atos` (`definir_selecao_route`, `matriculas/router.py:572`) | `extracted_and_confirmable`, but see gap (ii) below — the 5 real extractions' `formatacao='[]'` while `texto_extraido` still carries literal `**bold**` markers, so the confirmed selection quotes Markdown verbatim |
| `imovel.inscricao_municipal` | §2.2 | guia IPTU / CND IPTU (structured read) · matrícula `cadastro_municipal` abertura block | `imovel_hub/documentos_service.extrair_estrutura` (status/retry, migration 154) + `matriculas/preenchimento_service` (seed `find_inscricao_municipal`) → D1 writer `imovel_hub/campos_extraidos_service` | `imovel_dados.prefeitura_cadastro_imobiliario` (+ `_origem/_documento_id/_em/_confirmado_*`, migration 154) | validation gate (§0a) · conflict decide `PUT /api/imoveis/{codigo}/conflitos/{id}/decidir` · manual `PATCH /api/imoveis/{codigo}/dados` (stamps `manual`) | `extracted_and_confirmable` (2026-09-22) |
| `imovel.matricula_numero` | §2.2 | matrícula document | `imovel_hub/matricula_extracao_service` (text layer or vision — D1 dropped the text-layer-only rule) + `matriculas/preenchimento_service` after transcription → `campos_extraidos_service` | `imovel_dados.numero_matricula` (+ quintet) | validation gate (§0a) · conflict decide `PUT /api/imoveis/{codigo}/conflitos/{id}/decidir` · manual `PATCH /api/imoveis/{codigo}/dados` (stamps `manual`) | `extracted_and_confirmable` (2026-09-22) |
| `imovel.cartorio` | §2.2 | matrícula header | seed `find_cartorio` via `matriculas/preenchimento_service` → `campos_extraidos_service` | `imovel_dados.numero_registro_imoveis` (+ quintet, migration 154) | validation gate (§0a) · conflict decide `PUT /api/imoveis/{codigo}/conflitos/{id}/decidir` · manual `PATCH /api/imoveis/{codigo}/dados` (stamps `manual`) | `extracted_and_confirmable` (2026-09-22) |
| `imovel.em_condominio` | §2.12 | derived | `contexto.py:168` (`EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO and bool(imoveis.empreendimento)`, `politica.py`) | none — pure function of `imoveis.empreendimento` | (office policy toggle, `politica.py`, not per-deal) | `extracted_and_confirmable` (via the catalog's `empreendimento` field) |
| `titulo_aquisitivo` (spec's `titulo_aquisitivo.texto`) | §2.2 | matrícula act text (AI suggestion) | `matriculas/titulo_service.py:155 obter_titulo` (suggests off the selected atos) | `imovel_dados.titulo_aquisitivo_texto` (migration 115) — **the operator's CONFIRMED wording only; the generator never falls back to the suggestion** (`dados.py:206` comment) | `PUT /api/matriculas/imoveis/{codigo}/titulo-aquisitivo` (`confirmar_titulo_route`, `matriculas/router.py:634` → `titulo_service.py:212 confirmar_titulo`) | `extracted_and_confirmable` — **0 confirmed** across the corpus per §0 |
| `itens_integrantes` | §2.2 | none — free text | — | `atendimento_negociacao_termos.itens_integrantes` (migration 114) | `PUT /api/clientes/{cliente_id}/negociacao/termos` | `manual_entry_only` |

### Partes / qualificação (spec rows 19–32; clause §2.1)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `p.nome` (`clientes.nome_oficial`) | §2.1 | RG/CIN/CNH/certidão de casamento (text layer → vision) | `identidade_extracao_service.CAMPOS` (`item_key="nome_oficial"`) via `extrair_identidade` — D1 (migration 153): any read fills an EMPTY field machine-pending (`_confirmado_em` NULL); a differing value → `cliente_campo_conflitos` + admin notification, never an overwrite (the old `sobrescreve=True` overwrite is retired) | `clientes.nome_oficial` | validation gate (accept/reject) · AI suggestion confirm for a human-cleared field (`confirmar_sugestao`) · manual `PATCH /api/clientes/{cliente_id}` | `extracted_and_confirmable` |
| `p.nacionalidade_flex` | §2.1 | CIN/CNH/certidão (label `NACIONALIDADE`, per spouse on a certidão) · matrícula qualificação | `CAMPOS` `item_key="nacionalidade"` — D1 (migration 153): any read fills an EMPTY field machine-pending (`_confirmado_em` NULL); a differing value → `cliente_campo_conflitos` + admin notification, never an overwrite; `brasileira`/`brasileiro` compare as the same fact | `clientes.nacionalidade` | validation gate · manual `PATCH` | `extracted_and_confirmable` |
| `p.estado_civil_flex` | §2.1 | certidão de casamento/nascimento (AI; shared by BOTH spouses of a certidão) | `CAMPOS` `item_key="estado_civil"` — D1 (migration 153): any read fills an EMPTY field machine-pending (`_confirmado_em` NULL); a differing value → `cliente_campo_conflitos` + admin notification, never an overwrite | `clientes.estado_civil` (canonicalised by `documento_checklist_service.completude_contratual`) | validation gate · manual `PATCH` | `extracted_and_confirmable` |
| `p.profissao` | §2.1 | certidão de casamento (per spouse, label-anchored — seed `profession.py`) · fichas · matrícula qualificação | `CAMPOS` `item_key="profissao"` (migration 153) — D1 (migration 153): any read fills an EMPTY field machine-pending (`_confirmado_em` NULL); a differing value → `cliente_campo_conflitos` + admin notification, never an overwrite | `clientes.profissao` (+ quintet from 137) | validation gate · manual `PATCH` | `extracted_and_confirmable` |
| `p.rg` / `p.rg_orgao` | §2.1 | RG/CIN/CNH (AI) · matrícula qualificação | `CAMPOS` `item_key="rg"` and `item_key="rg_orgao_expedidor"` (own quintet, migration 153; `depende_de="rg"` — written only beside the RG it was read with; confirming an RG suggestion carries it) — D1 (migration 153): any read fills an EMPTY field machine-pending (`_confirmado_em` NULL); a differing value → `cliente_campo_conflitos` + admin notification, never an overwrite | `clientes.rg` / `clientes.rg_orgao_expedidor` | validation gate · manual `PATCH` (an issuer edit is held with a deferred RG) | `extracted_and_confirmable` (both) |
| `p.cpf` | §2.1 | RG/CIN/CPF/CNH/certidão (per spouse) | `CAMPOS` `item_key="cpf"` — D1 (migration 153): any read fills an EMPTY field machine-pending (`_confirmado_em` NULL); a differing value → `cliente_campo_conflitos` + admin notification, never an overwrite; punctuation-insensitive compare | `clientes.cpf` | validation gate · manual `PATCH` | `extracted_and_confirmable` |
| `p.email` | §2.1 | none | — | `clientes.email` (migration 068) | `PATCH /api/clientes/{cliente_id}` | `manual_entry_only` |
| `p.genero` / `p.g()` | §2.1 | CIN/RG/CNH `SEXO` (label, table layout, ICAO MRZ) · certidão (grammar per spouse, `baixa`) · matrícula (`m`/`f` → canonical via seed `canonical_gender`) | `CAMPOS` `item_key="genero"` — D1 (migration 153): any read fills an EMPTY field machine-pending (`_confirmado_em` NULL); a differing value → `cliente_campo_conflitos` + admin notification, never an overwrite | `clientes.genero` (`Masculino`/`Feminino`; migration 153 repaired `m`/`f` rows) | validation gate · manual `PATCH` | `extracted_and_confirmable` |
| `p.endereco` / `n.endereco` | §2.1 | `comprovante_endereco` (conta de luz/água/telefone — seed `address.py`, CEP-anchored, labelled + envelope block) | `identidade_extracao_service.aplicar_endereco_ao_cliente` (migration 153): the 7 parts as ONE group with one `endereco_*` quintet; the bill's printed holder must match the cliente or it is a conflict, never a fill; the bill's name/CPF never touch identity fields. `comprovante_residencia` is an `atendimento_documentos` (financing) type — not read | `clientes.endereco_cep/logradouro/numero/complemento/bairro/cidade/uf` | validation gate · conflict accept (`resolver_conflito`, JSON value) · suggestion confirm for a human-cleared group · manual `PATCH` (group-gated) | `extracted_and_confirmable` |
| `n.tipo` (casados/uniao_estavel/individual) | §2.1 | derived | `concordancia.py` (`lado()`; reads `estado_civil` + `conjuge_cliente_id` — the link is now also set from a certidão de casamento naming both spouses, reciprocally, `conjuge_*` quintet, migration 153) | none — pure function of the two fields above | — | `manual_entry_only` (via the two source fields) |
| `n.regime_extenso` | §2.1 | certidão de casamento (AI, `estado_civil`/`regime_bens` share the `CAMPOS` pipeline) | `CAMPOS` `item_key="regime_bens"`, `sobrescreve=False` | `clientes.regime_bens` | AI-suggest+confirm OR manual `PATCH` | `extracted_and_confirmable` |
| `n.lei_6515` (Lei 6.515/77 wording) | §2.1 | certidão de casamento full read (migration 110/117) | `CAMPOS` `item_key="data_casamento"`, `sobrescreve=False` — full-page read (`TIPOS_LEITURA_INTEGRAL`, `identidade_extracao_service.py:140`), NOT the 3-page default | `clientes.data_casamento` (migration 117) | AI-suggest+confirm OR manual `PATCH` | `extracted_and_confirmable` — the spec's own [Q2] (cite Lei 6.515/77 for every casamento, only after 26/12/1977, or never) is still an OPEN office question; `n.lei_6515` itself is not yet computed anywhere in `contexto.py`/`frases.py` — **not wired into any clause text today**, only the gate names it as `faltando` when the date is unset. Storage + gate exist; the clause-text branch does not |
| `V.*`, `C.*` agreement tokens | §2.0 | derived | `concordancia.py::lado` | none — pure function of the party rows above | — | n/a |
| `V.signatarios` / `C.signatarios` (`V_signatarios`/`C_signatarios`) | §2.17 | derived | `frases.py::signatario_linha`, gated by `dados.py:376 PAPEIS_SIGNATARIOS` | none | — | `manual_entry_only` (papel is set when the party is added to the card) |
| procurador/inventariante qualification wording | §2.1 | **genuinely absent** | — | `atendimento_partes.papel` accepts the value, but no wording exists | — | `no_source_yet` — `dados.py:379 PAPEIS_SEM_REDACAO`; `derivacao.py:485` refuses BY NAME rather than rendering blank text |

### Preço / parcelas (spec rows 33–45; clause §2.3)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `preco` | §2.3 | none | — | `atendimento_negociacao_estruturada.valor_negociado` | `PUT /api/clientes/{cliente_id}/negociacao/termos` family (`negociacao_estruturada_router.py`) | `manual_entry_only` |
| `p.num`, `p.tipo`, `p.valor` | §2.3 | none | — | `atendimento_negociacao_parcelas.{tipo,valor,ordem}` | `PATCH /api/clientes/{cliente_id}/negociacao/parcelas/{parcela_id}` (`negociacao_estruturada_router.py:101`) | `manual_entry_only` |
| `p.texto` (spec's `p.momento_texto` + `p.pagamento_texto`, now ONE pre-composed string — see note) | §2.3 | none | derived | `frases.py::texto_parcela` composes `vencimento`/`evento`/`forma_pagamento`/`favorecido_id` into one string at render time — **implementation divergence from spec**: spec modelled `momento_texto`/`pagamento_texto` as two placeholders; the shipped template has one `{{ p.texto }}` per parcela row | `PATCH .../negociacao/parcelas/{parcela_id}` | `manual_entry_only` |
| `p.splits[]` (spec #39, a parcela split across favorecidos) | §2.3 | — | — | — | — | `no_source_yet` — `atendimento_negociacao_parcelas.favorecido_id` is still ONE column; `PermutaImovel`/`Termos` did not touch this. Confirmed still open in spec §6.1 #4 |
| `p.juros_am` (direct parcelas) | §2.3 | — | — | — | — | `no_source_yet` (spec §6.1 #6, still open — distinct from confissão's `juros_am`, which IS stored) |
| `fav.nome` / `fav.cpf_cnpj` / `fav.banco_texto` | §2.3 | none | — | `atendimento_negociacao_favorecidos.{nome,cpf_cnpj,banco,agencia,conta,pix}` | `PATCH /api/clientes/{cliente_id}/negociacao/favorecidos/{favorecido_id}` (`negociacao_estruturada_router.py:164`) | `manual_entry_only`; `conta_tipo`/`pix_tipo` still `no_source_yet` (spec §6.1 #7) |
| `p_ref.*`, `multa_rescisoria` | §2.3/§2.9 | derived | `contexto.py:120` / `:383` | none | — | n/a |
| `ad_corpus` | §2.3 | none | — | `atendimento_negociacao_termos.ad_corpus` | `PUT .../negociacao/termos` | `manual_entry_only` |

### Confissão (spec rows 46–49; clause §2.4)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `confissao.parcelas_nums` / `.total` | §2.4 | derived | `contexto.py:369` | none — Σ of parcelas with `confissao_divida=true` | (flag set per-parcela below) | n/a |
| `p.confissao_divida` (per-parcela flag) | §2.4 | none | — | `atendimento_negociacao_parcelas.confissao_divida` | `PATCH .../negociacao/parcelas/{parcela_id}` | `manual_entry_only` |
| `confissao.juros_am` | §2.4 | none | — | `atendimento_negociacao_termos.confissao_juros_am` (migration 114) | `PUT .../negociacao/termos` | `manual_entry_only` — was spec §6.1 #6, now stored |
| `confissao.garantia_texto` | §2.4 | none | — | `atendimento_negociacao_termos.confissao_garantia` (migration 114) | `PUT .../negociacao/termos` | `manual_entry_only` — was spec §6.1 #6, now stored |

### Permuta (spec rows 50–55; clauses §2.3/§2.6/§2.7/§2.8)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| the permuta parcela's `tipo` (spec §6.1 #1) | §2.3 | none | — | `atendimento_negociacao_parcelas.tipo = 'permuta'` (CHECK widened, migration 114) | `PATCH .../negociacao/parcelas/{parcela_id}` | `manual_entry_only` — was `no_source_yet` at spec time, now closed |
| multiple permuta assets (spec §6.1 #2) | §2.3 | none | — | `atendimento_parcela_permuta_ativos` join table (migration 114) — a parcela links N `permuta_ativos` | `PATCH .../negociacao/parcelas/{parcela_id}` (the link array) | `manual_entry_only` — was `no_source_yet`, now closed |
| per-imóvel act role (spec §6.1 #3) | §2.3 | matrícula document, per permuta imóvel | `matriculas/estrutura_service.py::obter_selecao` `['permutas']`, keyed by `permuta_ativo_id`, `papel='permuta'` (migration 115) | `atendimento_contrato_matricula_atos` rows with `papel='permuta'` | `PUT /api/matriculas/contratos/{contrato_id}/atos` (same endpoint as the objeto imóvel, now supports a per-ativo role) | `extracted_and_confirmable` — was `no_source_yet`, now closed |
| `permuta.imoveis[].{endereco_curto,inscricao_municipal,matricula_numero,cartorio}` | §2.3/§2.7 | matrícula/catalog | `carregador.py:231 _permuta_imoveis` | `imovel_dados` of the ativo's linked imóvel, OR `permuta_ativos`' own address snapshot (migration 101) when the ativo is NOT a catalog listing | `PATCH /api/imoveis/{codigo}/dados` when catalog-linked; the ativo's own snapshot has no documented write endpoint in this pass — see gap list (iii) | `manual_entry_only` |
| `permuta.proprietarios_nomes` | §2.3 | none | — | `permuta_ativos.proprietario_nome` (a snapshot, migration 101) | not found in this pass — likely set at ativo creation only; no PATCH route located | `manual_entry_only` |
| `permuta.posse_prazo` / `posse_marco_texto` (spec §6.1 #12) | §2.7 | none | — | `atendimento_negociacao_termos.permuta_posse_prazo_dias` / `.permuta_posse_marco` / `.permuta_posse_marco_parcela_id` (migration 114) | `PUT .../negociacao/termos` | `manual_entry_only` — closed since spec |
| `permuta.obrigacoes_entrega` | §2.7 | none | — | `atendimento_negociacao_termos.permuta_obrigacoes_entrega` (migration 114) | `PUT .../negociacao/termos` | `manual_entry_only` — **stored, but no clause in `modelo_texto.py` prints it**; see gap (ii) |
| `permuta.despesas_texto` (who pays deed/ITBI per imóvel) | §2.8 | — | — | — | — | `no_source_yet` — the shipped `tributos` clause (§2.8, `modelo_texto.py:137`) hard-codes "as despesas… serão suportadas pela parte que o recebe" for the permuta branch; there is no per-deal override field. Spec §6.1 #13 still open |
| `permuta.onus_quitados[]` | §2.6 | — | — | — | — | `no_source_yet` — `Termos.onus_quitacao` has no `'ja_quitado'`-for-permuta branch wired into `modelo_texto.py`; `derivacao.py:611` explicitly BLOCKS (`ONUS_QUITACAO_SEM_REDACAO`) rather than printing this |

### Ônus (spec rows 56–58; clause §2.6)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `onus.fonte_texto` (spec's `onus.ato_ref`) | §2.6 | matrícula act selection | `carregador.py:176-186` reads `imovel_dados.onus_fonte` → resolves against `estrutura_service.listar_atos` | `imovel_dados.onus_fonte` (JSONB `{extracao_id, atos:[{ato_id}]}`, migration 099/115) | `PATCH /api/imoveis/{codigo}/dados` (`onus_documento_id` in `ImovelDadosPatchBody`) — **the exact write path for `onus_fonte`'s ato list was not located in this pass**; likely a matrículas-side action, not `ImovelDadosPatchBody` (that schema only carries `onus_documento_id`, not an ato array) — flagged in the gap list as needing verification | `extracted_but_no_promotion_path` — a confirmed HTTP promotion step could not be located in this pass; see gap list (ii) #9 |
| `onus.credor` | §2.6 | matrícula act text (AI suggestion) | `matriculas/titulo_service.py:230 obter_onus_credor` | `imovel_dados.onus_credor` (migration 115) — confirmed wording only | `PUT /api/matriculas/imoveis/{codigo}/onus-credor` (`confirmar_onus_credor_route`, `matriculas/router.py:665` → `titulo_service.py:289`) | `extracted_and_confirmable` — was spec §6.1 #11, now closed; **0 confirmed** (part of the 30 act-detail suggestions in §0) |
| `onus.quitacao` / `onus.prazo_dias` | §2.6 | none | — | `atendimento_negociacao_termos.onus_quitacao` (enum `compradores_prazo`/`interveniente_quitante`/`parcela`/`ja_quitado`) / `.onus_prazo_dias` (migration 114) | `PUT .../negociacao/termos` | `manual_entry_only` — was spec §6.1 #11, now closed; `'ja_quitado'` is accepted by the CHECK but has NO clause text (gap ii) |

### Certidões (spec rows 59–69; clause §2.5)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `certidoes.grupos[]` (per-parte result set) | §2.5 | 3rd-party certidão APIs (10 auto) + 3 manual-upload types (`serasa`, `tjsp_esaj`, `tjsp_eproc` — `registry.py:154-156`) | `certidoes/service.py:1182 processar_consulta` → `:781 _derive_estrutura` → `:697 _analyze_estrutura_with_ai` (AI reads the fetched/uploaded document) | `certidao_resultados.{resultado,numero,emitida_em,validade_ate}` per `certidao_consultas` row | `PATCH /api/certidoes/resultados/{resultado_id}` (`confirmar_ou_corrigir_resultado`, `routers/certidoes.py:1023` → `service.py:2145 confirmar_resultado`) — **an EMPTY body is a valid confirmation** ("I reviewed the AI-suggested values and they are correct"); always stamps `resultado_origem='manual'` + who + when | `extracted_and_confirmable` — **0 of 130 confirmed** (21 have an AI verdict) |
| `g.em_nome_de` / person vs company routing | §2.5 | derived | `derivacao.py:347 indice_certidoes`, `:364 grupos_pj` | `certidao_consultas.consulta_tipo_documento` (`cpf`/`cnpj`) + `.consulta_nome` | set at consulta creation, `POST /api/certidoes/consultas` (`routers/certidoes.py:310`) | `manual_entry_only` |
| `g.sufixo` ("Baixada" PJ status label) | §2.5 | Receita Federal situação cadastral | none automated — `SituacaoCadastralPatch` (`certidoes/schemas.py:87`) is explicitly a **human's manual entry** of `situacao_cadastral`/`data_situacao` | `certidao_consultas.consulta_situacao_cadastral` / `.consulta_data_situacao` (migration 116) | `PATCH /api/certidoes/consultas/{consulta_id}/situacao-cadastral` (`atualizar_situacao_cadastral_route`, `routers/certidoes.py:923`) | `manual_entry_only` — was spec §6.1 #16, now closed as a manual field (never automated) |
| `i.numero` / `i.emitida_em` | §2.5 | as `certidoes.grupos[]` above | same | `certidao_resultados.numero` / `.emitida_em` | same `PATCH /resultados/{resultado_id}` | `extracted_and_confirmable` |
| `i.sistema` (E-SAJ/E-PROC) | §2.5 | derived | `derivacao.py` label table (`tjsp_esaj`→"E-SAJ", `tjsp_eproc`→"E-PROC") | none — derived from `tipo` | — | n/a — **also resolves spec [Q8]**: the registry now carries `tjsp` (API) as DISTINCT from `tjsp_esaj`/`tjsp_eproc` (manual upload types, `registry.py:105,155,156`) — three separate `tipo`s, not one document under two names |
| `certidoes.apresentantes_texto` | §2.5 | derived | `derivacao.py:420 pessoas_certificadas` + `contexto.py:250` | none | — | n/a |
| `certidoes.grupos_imovel[]` (matrícula/IPTU/condominial CND) | §2.5 | imóvel documents (AI structured extraction, migration 118) | `imovel_hub/documentos_service.py:581 extrair_estrutura` (per uploaded document: `guia_iptu`, `carne_condominio`, matrícula certidão) | `imovel_documentos.{tipo,numero,emitida_em,validade_ate,resultado,inscricao_imobiliaria,confirmado}` | `PATCH /api/imoveis/{codigo}/documentos/{documento_id}/extracao` (`patch_documento_extracao_route`, `imovel_hub/router.py:196` → `documentos_service.py:677 confirmar_extracao`; body `ImovelDocumentoExtracaoPatchBody`, an EMPTY body is also a valid confirmation here) | `extracted_and_confirmable` — was spec §6.1 #14, now closed; read back via `GET /api/imoveis/{codigo}/certidoes` (`documentos_service.py:723`) |
| `certidoes.pendencias[]` | §2.5 | derived | `contexto.py:235-247` | none — derived from the rows above plus `nao_emitida` results | — | n/a |
| `prazo_pendencias` / `prazo_esclarecimentos` | §2.5 | none | — | `prazo_pendencias`: contract override `atendimento_contratos.prazo_pendencias_dias` (migration 114) → office default `org_dados_cadastrais.prazo_pendencias_padrao_dias` (migration 117) → literal `10`. `prazo_esclarecimentos`: `politica.py::prazo_esclarecimentos_dias`, an OFFICE-WIDE constant, not per-deal | `atendimento_contratos.prazo_pendencias_dias` via `PATCH .../contratos/{contrato_id}`; org default via `PUT /api/settings/imobiliaria` | `manual_entry_only` |
| previous-owner certidões (spec §6.1 #17) | §2.5 | last compra-e-venda act on the matrícula | `matriculas/titulo_service.py:336 antigos_proprietarios` (reads `data_registro` + `transmitentes` off the selected atos) | derived — no independent table; the transmitentes names come straight off the matrícula act text | the antigo proprietário must then be added as a `partes` row (`vendedor` lado) to be qualified + certified like any signatory | `extracted_and_confirmable` — was `no_source_yet` at spec time, closed by migration 115; `derivacao.py:412 exige_antigo_proprietario` gates on a 5-year window (`politica.antigo_proprietario_janela_anos`) |
| titular certidões (spec §6.1 #18) | §2.5 | as `certidoes.grupos[]` | `certidoes/service.py:2084 certidoes_por_cliente` (vs `:2064 certidoes_por_parte` for a non-titular party) | same `certidao_resultados`, reached by `cliente_id` instead of `atendimento_parte_id` (migration 116) | same `PATCH /resultados/{resultado_id}` | `extracted_and_confirmable` — was `no_source_yet`, closed |

### Posse (spec rows 70–74; clause §2.7)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `posse.prazo`, `posse.marco_texto` | §2.7 | none | — | `atendimento_negociacao_termos.posse_prazo_dias` / `.posse_marco` (`assinatura`\|`parcela`\|`protocolo_registro`) / `.posse_marco_parcela_id` (migration 114) | `PUT .../negociacao/termos` | `manual_entry_only` — was spec §6.1 #12, now closed |
| `posse.condicao_frase` | §2.7 | derived | `derivacao.py:244 parcelas_antes_de` + `frases.py::condicao_posse_frase` | none | — | n/a |
| `posse.prorrogacao_dias` + `compensacao_*` | §2.7 | — | — | — | — | `no_source_yet` — NOT covered by migration 114's `Termos`; still absent from `dados.py`. The shipped `modelo_texto.py` also has NO prorrogação paragraph at all (spec §2.7 modelled one, `03`'s divergence) — a second gap on top of the missing field |
| `posse.multa_diaria` | §2.7 | none — office setting, same value for every contract incl. permuta | — | `org_dados_cadastrais.posse_multa_diaria` (migration 117) | `PUT /api/settings/imobiliaria` | `manual_entry_only` — was spec §6.1 #12/[Q12], now closed and answered ("yes, a fixed office default, permuta included") |

### Rescisão / resolutiva (spec rows 75–77; clauses §2.9/§2.15)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `rescisao.encargo_texto` [Q4] | §2.9 | — | — | — | — | `no_source_yet`, **and now also office-answered a different way than spec envisioned**: `contexto.py:381` hard-codes ONE fixed wording ("multa + custos comprovadamente gerados") for every contract — the honorários/custos/nenhum enum spec §3 row 75 described was never built; [Q4] is answered by product decision, not by a stored field |
| `rescisao.cura_frase` (spec's `rescisao.cura_dias`) | §2.9 | none — office-wide policy, not per-deal | — | `politica.py::rescisao_cura_dias` | office-wide constant (code change), not a UI form | `manual_entry_only` (in the loose sense — it's a deploy-time constant, not a per-contract entry) |
| `resolutiva_notificacao_email` | §2.15 | none — office-wide policy | — | `politica.py::resolutiva_notificacao_email` | same as above | `manual_entry_only` |

### Intermediação / corretagem (spec rows 78–86; clause §2.16)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `org.*` (office's own intermediário qualification) | §2.16 | none | — | `org_dados_cadastrais.{razao_social,nome_fantasia,cnpj,creci_pj,responsavel_nome,responsavel_creci,email,endereco_*}` | `PUT /api/settings/imobiliaria` | `manual_entry_only` |
| `intermediacao.qualificados[]` (external intermediário) | §2.16 | none | — | `atendimento_intermediarios.{pessoa_tipo,documento,email,endereco_*,representante_nome,representante_cpf}` (migration 114) | `PATCH /api/clientes/{cliente_id}/negociacao/intermediarios/{intermediario_id}` (`negociacao_estruturada_router.py:208`) | `manual_entry_only` — was spec §6.1 #21, now closed |
| `corretagem.splits[]` (favorecido↔intermediário link) | §2.16 | none | — | `atendimento_intermediarios.favorecido_id` (migration 114) | same `PATCH .../intermediarios/{id}` | `manual_entry_only` — was spec §6.1 #22, now closed |
| `corretagem.total` | §2.16 | derived | `contexto.py:326-341` | none — Σ of `intermediarios.valor` (percentual × `valor_negociado`, or `valor_fixo`) | — | n/a |
| `corretagem.contratantes_texto` (payer) | §2.16 | none | — | `atendimento_negociacao_termos.corretagem_contratantes` (`vendedores`\|`compradores`\|`partes`, migration 114) | `PUT .../negociacao/termos` | `manual_entry_only` — was spec §6.1 #23-adjacent, now closed |
| `corretagem.parcelamento_texto` / `marcos_texto` | §2.16 | none | — | `atendimento_negociacao_termos.corretagem_num_parcelas` (migration 114) / `atendimento_negociacao_parcelas.dispara_corretagem` per-parcela flag (migration 114) | `PUT .../negociacao/termos` + `PATCH .../negociacao/parcelas/{id}` | `manual_entry_only` — was spec §6.1 #23, now closed |
| `corretagem.pct_rescisao` | §2.16 | derived — **answered differently than spec envisioned** | `contexto.py:346` (`frases.pct_simples(d.pct_comissao)`) | `atendimento_negociacao.pct_comissao` | reuses the deal's commission %; [Q5] is answered "always the deal's %", so the separate `pct_corretagem_rescisao` field spec §6.1 #24 imagined was never built | `manual_entry_only` (via `pct_comissao`) |

### Testemunhas (spec rows 87–89; clause §2.17)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `testemunhas[].nome` / `.rg` | §2.17 | none | — | `org_testemunhas.{nome,rg}` | `POST/PATCH /api/settings/imobiliaria/testemunhas[/{testemunha_id}]` (`settings_router.py:1687`/`:1729`) | `manual_entry_only` — RG is hard-required (§5.1), never CPF |
| `testemunhas[].email` [Q14 revisited] | §2.17 | none | — | `org_testemunhas.email` (migration 143) | same endpoints | `manual_entry_only` — optional; printed beside the name when present, and is what `assinatura_service.enviar` resolves a `papel='testemunha'` signatário's e-mail from. `org_testemunhas.cpf` stays a separate, OPTIONAL field (validated mod-11 when present, never required, never printed) — see the F5 clause template's `RG {{ t.rg }}` line; this row corrects the prior entry here, which had the code's then-current (and since-fixed) CPF-printing defect backwards from spec §2.17/§5.1's own already-written "nome + rg" answer |

### Financiamento (spec row 90; validation only, no clause text)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `financiamento.existe` / `.situacao` / `.fgts` | gate only | none | — | `atendimento_financiamento.{situacao,fgts}` | `PATCH /api/clientes/{cliente_id}/financiamento` (`card_hub/router.py:1168`) | `manual_entry_only` |

### Declaração / misc (spec rows 91–92; clauses §2.11/§2.2)

| placeholder | clause | source document type | extractor code path | confirmed storage | confirm/promote step | status |
|---|---|---|---|---|---|---|
| `tem_declaracao_partes` | §2.11 | none — office policy | — | `politica.py::tem_declaracao_partes` | deploy-time constant | `manual_entry_only` |
| `obrigacoes_vendedor` (05's deck) | §2.2 | none | — | `atendimento_negociacao_termos.obrigacoes_vendedor` (migration 114) | `PUT .../negociacao/termos` | `manual_entry_only` — **stored, but `modelo_texto.py` has no clause paragraph that prints it** (see gap ii); `derivacao.py:1077` only **warns** `OBRIGACOES_VENDEDOR_SEM_REDACAO` when it is filled |

## 3 · Appendix — literal template-token inventory (keeper ground truth)

The keeper in §6 does **not** re-derive the 92-row table above (a markdown
table is not a stable parse target). It derives a flat SET of literal
dotted-attribute tokens straight out of the two files that actually decide
what the generator prints:

1. `contrato_gerador/modelo_texto.py` — `ast.parse` finds the module-level
   `TEMPLATE = r"""…"""` assignment and lifts its string value (a real
   Python-AST read, not a text grep); a regex then collects every
   `root.attr[.attr…]` token inside a Jinja `{{ … }}` or `{% … %}` /
   `{%p … %}` block. As of this branch that is **100 distinct dotted
   tokens** (`loop.index`/`loop.last` excluded — Jinja builtins, not data).
2. `contrato_gerador/contexto.py::montar_contexto` — `ast.parse` finds the
   function's own `return {…}` dict literal and lifts its top-level STRING
   keys (`imovel`, `certidoes`, `preco`, `confissao`, `posse`, `permuta`,
   `onus`, `corretagem`, `assinatura`, `foro`, `testemunhas`, `rescisao`,
   `multa_rescisoria`, `titulo_aquisitivo`, `itens_integrantes`,
   `V`/`C`/`V_qualificacao`/`C_qualificacao`/`V_signatarios`/
   `C_signatarios`, `p_ref`, `prazo_pendencias`, `prazo_esclarecimentos`,
   `resolutiva_notificacao_email`, plus the pure-machinery keys `cl`/`par`/
   `brl`/`dias`/`pct_extenso` which the keeper drops — they are formatting
   helpers, not data placeholders).
3. `contrato_gerador/derivacao.py::derivar_switches` — `ast.parse` finds
   that function's `return {…}` dict literal and lifts its keys (the 14
   `tem_*`/`a_vista`/`ad_corpus` switches), because they are spread with
   `**sw` into the same top-level context `montar_contexto` returns.

**Named limitation** (per this brief's own escape hatch): a full Jinja-AST
parse (walking `jinja2.Environment().parse()`'s node tree) would also catch
bare single-token variables used OUTSIDE a dotted chain (`preco`,
`titulo_aquisitivo`, `multa_rescisoria`, `ad_corpus`, `itens_integrantes`)
and loop-bound aliases (`p`, `s`, `g`, `q`, `t`, `d`, `i`) without a
hand-written stoplist. `jinja2` is already a runtime dependency of
`seed/lib/backend` (`pyproject.toml:81`) but is **not** a declared
dependency of `mcp/noctusai` itself (`mcp/noctusai/pyproject.toml` has no
`jinja2` entry) — adding it there to do a full template-AST parse would be a
new cross-package dependency for one keeper, and risks exactly the
declared-imports drift `check_seed_declared_imports` exists to catch.
Instead, list (2) + (3) above close the "bare top-level name" gap **without
a hand-maintained stoplist**, by reading the two dict literals that are
themselves the authoritative closed set of top-level names — the union of
(1)+(2)+(3) is not a 100%-complete Jinja parse, but every name it misses
(a loop-local alias inside a `{% for %}` body, e.g. `s.valor` used only
through `frases.split_corretagem`'s own return string) is a name that never
reaches `modelo_texto.py` as a literal dotted token in the first place — so
nothing in (1) is silently dropped by (2)/(3) being narrower.

The keeper requires this doc to enumerate every token from (1) ∪ (2) ∪ (3) —
literally, as a backtick-quoted cell in the table below. This is the exact
set the keeper re-derives at check time (140 tokens as of this branch;
machine-regenerable by rerunning the same `ast.parse` + regex pass); a row
disappearing from this table when the code still emits the token is exactly
the drift the keeper exists to catch. `no_source_yet` rows in §2/§4 do not
have a token here because the missing field is either not yet wired into the
template at all (`posse.prorrogacao_dias`, `permuta.despesas_texto`) or is
consumed only via a pre-composed string built in `contexto.py`/`frases.py`
(`certidoes.grupos[].itens[]` as plain strings, `corretagem.qualificados[]`
as plain strings) rather than as a further dotted attribute access — those
pre-composed strings are themselves covered by the `certidoes.grupos` /
`corretagem.qualificados` rows already in the table.

| token | §2 group |
|---|---|
| `C` | Partes / qualificação |
| `C.ART` | Partes / qualificação |
| `C.NOME` | Partes / qualificação |
| `C.aos` | Partes / qualificação |
| `C.art` | Partes / qualificação |
| `C.estes` | Partes / qualificação |
| `C.g` | Partes / qualificação |
| `C.pelos` | Partes / qualificação |
| `C.pl` | Partes / qualificação |
| `C.plural` | Partes / qualificação |
| `C_qualificacao` | Partes / qualificação |
| `C_signatarios` | Partes / qualificação |
| `V` | Partes / qualificação |
| `V.ART` | Partes / qualificação |
| `V.NOME` | Partes / qualificação |
| `V.aos` | Partes / qualificação |
| `V.art` | Partes / qualificação |
| `V.dos` | Partes / qualificação |
| `V.estes` | Partes / qualificação |
| `V.g` | Partes / qualificação |
| `V.pelos` | Partes / qualificação |
| `V.pl` | Partes / qualificação |
| `V_qualificacao` | Partes / qualificação |
| `V_signatarios` | Partes / qualificação |
| `a_vista` | Contrato / assinatura (§1.1 switches) |
| `ad_corpus` | Contrato / assinatura (§1.1 switches) |
| `assinatura` | Contrato / assinatura |
| `assinatura.data_extenso` | Contrato / assinatura |
| `assinatura.local` | Contrato / assinatura |
| `assinatura.plataforma_nome` | Contrato / assinatura |
| `assinatura.plataforma_url` | Contrato / assinatura |
| `certidoes` | Certidões |
| `certidoes.apresenta` | Certidões |
| `certidoes.apresentantes_texto` | Certidões |
| `certidoes.grupos` | Certidões |
| `certidoes.grupos_imovel` | Certidões |
| `certidoes.pendencias` | Certidões |
| `certidoes.seus_nomes` | Certidões |
| `cl.assinatura_digital.ORD` | Contrato / assinatura |
| `cl.certidoes.ORD` | Contrato / assinatura |
| `cl.confissao.ORD` | Contrato / assinatura |
| `cl.declaracao_partes.ORD` | Contrato / assinatura |
| `cl.foro.ORD` | Contrato / assinatura |
| `cl.intermediacao.ORD` | Contrato / assinatura |
| `cl.irretratabilidade.ORD` | Contrato / assinatura |
| `cl.irretratabilidade.ref` | Contrato / assinatura |
| `cl.mora.ORD` | Contrato / assinatura |
| `cl.objeto.ORD` | Contrato / assinatura |
| `cl.objeto.ref` | Contrato / assinatura |
| `cl.onus.ORD` | Contrato / assinatura |
| `cl.posse.ORD` | Contrato / assinatura |
| `cl.posse.ref` | Contrato / assinatura |
| `cl.preco.ORD` | Contrato / assinatura |
| `cl.preco.ref` | Contrato / assinatura |
| `cl.registro.ORD` | Contrato / assinatura |
| `cl.resolutiva.ORD` | Contrato / assinatura |
| `cl.tributos.ORD` | Contrato / assinatura |
| `cl.vistoria.ORD` | Contrato / assinatura |
| `confissao` | Confissão |
| `confissao.garantia_texto` | Confissão |
| `confissao.juros_am` | Confissão |
| `confissao.parcelas_nums` | Confissão |
| `confissao.total` | Confissão |
| `corretagem` | Intermediação / corretagem |
| `corretagem.contrata` | Intermediação / corretagem |
| `corretagem.contratadas_texto` | Intermediação / corretagem |
| `corretagem.contratantes_texto` | Intermediação / corretagem |
| `corretagem.contratantes_texto_cap` | Intermediação / corretagem |
| `corretagem.empresas_texto` | Intermediação / corretagem |
| `corretagem.marcos_texto` | Intermediação / corretagem |
| `corretagem.parcelamento_texto` | Intermediação / corretagem |
| `corretagem.pct_rescisao` | Intermediação / corretagem |
| `corretagem.qualificados` | Intermediação / corretagem |
| `corretagem.splits` | Intermediação / corretagem |
| `corretagem.total` | Intermediação / corretagem |
| `d.letra` | Certidões |
| `d.texto` | Certidões |
| `foro` | Contrato / assinatura |
| `foro.comarca` | Contrato / assinatura |
| `g.em_nome_de` | Certidões |
| `g.itens` | Certidões |
| `g.num` | Certidões |
| `g.sufixo` | Certidões |
| `g.titulo` | Certidões |
| `imovel` | Imóvel objeto |
| `imovel.cartorio` | Imóvel objeto |
| `imovel.cidade` | Imóvel objeto |
| `imovel.descricao_matricula` | Imóvel objeto |
| `imovel.em_condominio` | Imóvel objeto |
| `imovel.endereco_curto` | Imóvel objeto |
| `imovel.inscricao_municipal` | Imóvel objeto |
| `imovel.matricula_numero` | Imóvel objeto |
| `imovel.titulo_curto` | Imóvel objeto |
| `imovel.uf` | Imóvel objeto |
| `itens_integrantes` | Imóvel objeto |
| `multa_rescisoria` | Rescisão / resolutiva |
| `onus` | Ônus |
| `onus.credor` | Ônus |
| `onus.fonte_texto` | Ônus |
| `onus.prazo_dias` | Ônus |
| `onus.quitacao` | Ônus |
| `onus.quitacao_texto` | Ônus |
| `p.num` | Preço / parcelas |
| `p.texto` | Preço / parcelas |
| `p_ref` | Preço / parcelas |
| `p_ref.financiamento` | Preço / parcelas |
| `p_ref.permuta` | Preço / parcelas |
| `p_ref.sinal` | Preço / parcelas |
| `parcelas` | Preço / parcelas |
| `permuta` | Permuta |
| `permuta.endereco_curto` | Permuta |
| `permuta.posse_marco_texto` | Permuta |
| `permuta.posse_prazo` | Permuta |
| `posse` | Posse |
| `posse.condicao_frase` | Posse |
| `posse.marco_texto` | Posse |
| `posse.multa_diaria` | Posse |
| `posse.prazo` | Posse |
| `prazo_esclarecimentos` | Certidões |
| `prazo_pendencias` | Certidões |
| `preco` | Preço / parcelas |
| `rescisao` | Rescisão / resolutiva |
| `rescisao.cura_frase` | Rescisão / resolutiva |
| `resolutiva_notificacao_email` | Rescisão / resolutiva |
| `t.linha` | Testemunhas |
| `t.rg` | Testemunhas |
| `tem_confissao` | Contrato / assinatura (§1.1 switches) |
| `tem_declaracao_partes` | Contrato / assinatura (§1.1 switches) |
| `tem_fgts` | Contrato / assinatura (§1.1 switches) |
| `tem_financiamento` | Contrato / assinatura (§1.1 switches) |
| `tem_intermediacao` | Contrato / assinatura (§1.1 switches) |
| `tem_intermediaria` | Contrato / assinatura (§1.1 switches) |
| `tem_itens_integrantes` | Contrato / assinatura (§1.1 switches) |
| `tem_multa_diaria_posse` | Contrato / assinatura (§1.1 switches) |
| `tem_parcelas_diretas` | Contrato / assinatura (§1.1 switches) |
| `tem_permuta` | Contrato / assinatura (§1.1 switches) |
| `tem_pj_certidoes` | Contrato / assinatura (§1.1 switches) |
| `tem_saldo_devedor` | Contrato / assinatura (§1.1 switches) |
| `testemunhas` | Testemunhas |
| `titulo_aquisitivo` | Imóvel objeto |
| `C_assinantes_fisicos` | Contrato / assinatura (física, migration 157) |
| `V_assinantes_fisicos` | Contrato / assinatura (física, migration 157) |
| `linha_assinatura` | Contrato / assinatura (física, migration 157) |
| `s.documento` | Contrato / assinatura (física, migration 157) |
| `s.nome` | Contrato / assinatura (física, migration 157) |
| `t.documento` | Testemunhas (física, migration 157) |
| `t.nome` | Testemunhas (física, migration 157) |
| `tem_assinatura_digital` | Contrato / assinatura (§1.1 switches) |
| `testemunhas_fisicas` | Testemunhas (física, migration 157) |
| `vias` | Contrato / assinatura (física, migration 157) |

## 4 · Ranked gap list

> **2026-09-22 status (see §0a):** items 1 (identity fields now auto-filled, validated at the gate), 4 (`imovel_dados` auto-filled from the matrícula/IPTU), 6 (markup backfill route + marker-free transcription), 7 (`rg_orgao` now extracted), 9 (`onus_fonte_atos` filled by `preenchimento_service`) and 10 (endereço from comprovante) are CLOSED by migrations 153–156. Items 2/3/5 no longer need a separate office click per suggestion: they surface in the validation modal. The rest stand as written.

Ranked by how many of the 6 spec §1.3 variants (V1–V6) the gap blocks
**today**, given the classification below.

### (i) Extracted, has a promotion path, never confirmed — cheapest fix, blocks ALL 6 variants

1. **CPF/RG/gênero/estado civil/regime de bens/data de casamento** — `identidade_extracao_service.CAMPOS`, 0 of 1 393 `clientes` confirmed. Blocks §5.1's hard-required qualification gate for every signatory in every variant. Fix: an office pass over `POST .../documentos/{id}/extracao/confirmar` per party (or direct `PATCH /clientes/{id}` for the un-extractable fields).
2. **Certidão results** — 21 of 130 have an AI verdict, 0 confirmed. Blocks §5.1's certidões gate for every variant (all 8 sample contracts required all 12 PF types per signatory). Fix: `PATCH /certidoes/resultados/{id}` per result — an empty body suffices when the AI verdict is correct.
3. **Matrícula act-detail suggestions** (título aquisitivo text, ônus credor) — 30 suggestions, 0 confirmed. Blocks `imovel.titulo_curto`'s objeto clause AND, whenever `tem_saldo_devedor`, the ônus clause (V1/V2/V5/V6 in the variant matrix — 5 of 8 sample contracts). Fix: `PUT /matriculas/imoveis/{codigo}/titulo-aquisitivo` + `PUT .../onus-credor` per imóvel.
4. **`imovel_dados` — 0 rows.** Every deal's `numero_matricula`/`numero_registro_imoveis`/`prefeitura_cadastro_imobiliario`/`situacao_onus` is unset. Blocks the objeto clause for every variant, before anything else in this list even matters. Fix: `PATCH /imoveis/{codigo}/dados` once per imóvel (mechanically cheap; the values are already known to the office, just never entered).
5. **Matrícula-to-imóvel act selection** — 0 of 8 extractions linked to a contract's `atos`. Blocks the objeto clause's `{{r imovel.descricao_matricula }}` rich-text slot outright — `derivacao.py:569` refuses generation (`matricula.atos`) with nothing selected. Fix: `PUT /matriculas/contratos/{contrato_id}/atos` per contract.

### (ii) Extracted or manually stored, but the value can NEVER reach the contract today — real bugs, not office backlog

6. **The markdown-markup defect.** All 5 genuine (non-fixture) matrícula extractions carry literal `**bold**`/`__underline__` Markdown syntax IN `texto_extraido`, with `formatacao='[]'` (no structured bold/underline ranges). The objeto clause quotes `imovel.descricao_matricula` through docxtpl's `{{r … }}` RICH-TEXT slot (`contexto.py:83 _descricao_matricula_rica`, `modelo_texto.py:34`) — **the slot is built specifically so a plain string renders EMPTY** (`modelo_texto.py`'s own docstring: "a plain string in a `{{r ... }}` slot renders as EMPTY"). So every real matrícula today either (a) prints literal `**` characters in the generated Word document (if `_descricao_matricula_rica` degrades to a plain string on empty `formatacao` rather than truly using the rich-text path — **this needs runtime verification, not asserted here**), or (b) prints as an empty IMÓVEL paragraph. Either way it is silently WRONG, never a `faltando`/`bloqueio` the gate can name — `derivacao.py:569` only checks `num_atos == 0 or not texto.strip()`, which a non-empty markdown-laden string passes clean. **Blast radius: 100% of real matrículas, every variant** — this is the single highest-leverage bug in the whole system, because unlike (i) it cannot be fixed by an office click; it needs either a backfill that re-derives `formatacao` from the `**`/`__` markers already in `texto_extraido`, or a re-transcription pass. `NOC-REMEDIATE[transcricao-formatacao-backfill]` undercounts this as "5 stray rows" — it is the entire non-fixture corpus.
7. **`onus.credor` sub-fields, `rg_orgao`, `permuta.despesas_texto`.** `rg_orgao` (RG issuing agency) has no extractor at all (only the RG number is in `CAMPOS`) — an office that assumes "we extract RG" will find this one field is always manual, silently. Not a code bug, but a genuine extraction-boundary surprise worth naming next to the real bugs because it looks like (i) from the UI ("RG was AI-suggested, why isn't the órgão?").
8. **`obrigacoes_vendedor` / `permuta_obrigacoes_entrega`.** Both have real storage (migration 114) and a UI form (`PUT .../negociacao/termos`), and `derivacao.py` gates around them (`_contrato` at line ~1069-1078) — but **no clause paragraph in `modelo_texto.py` ever reads either field.** An operator who fills these forms gets a silent no-op: the office types real text, the code only fires an `avisa()` warning that the text "is NOT on the instrument" — easy to miss in a UI that otherwise treats `avisos` as non-blocking. Same class as `Termos.onus_quitacao='ja_quitado'` (§2 Ônus table) — accepted by the CHECK constraint, refused by name at render time with zero clause text to print even if it weren't.
9. **`onus.fonte_texto`'s exact confirm endpoint is unverified in this pass.** `ImovelDadosPatchBody` (`imovel_hub/schemas.py`) carries `onus_documento_id` but no `onus_fonte` ato-array field; `carregador.py` reads `imovel_dados.onus_fonte` as a JSONB `{extracao_id, atos:[...]}` blob. The write path for that specific shape was not located among the routers read in this pass (`imovel_hub/router.py`, `matriculas/router.py`) — either a route exists elsewhere that this map missed, or the field is written only via `imovel_hub/dados_service.py::gravar_fontes_matricula`/`aplicar_matricula_extraida` server-side helpers with no direct HTTP PATCH, in which case it may be `extracted_but_no_promotion_path` for a human, not `extracted_and_confirmable`. **Flagged rather than guessed** — verify before treating row `onus.fonte_texto` as closed.

### (iii) Manual entry only, no extraction possible

10. Party address (`p.endereco`) — the single field in this whole map with **zero** extraction candidate even in principle (no `comprovante de residência` structural read exists anywhere in the codebase). Blocks the header qualification paragraph (§2.1) for every signatory, every variant.
11. Org settings (`org_dados_cadastrais.*`, `org_testemunhas.*`, `politica.py` constants) — one-time office setup, not per-deal; low ranked because it blocks generation only until configured ONCE per org, not once per deal.
12. Negociação/parcelas/favorecidos/intermediários/termos — the entire deal-terms surface is, and always was, manual entry (the office negotiates the deal; there is no document to read it off). Not a gap so much as the correct design — listed for completeness of the map, not as a fix target.

### (iv) No source at all — spec §6.1 leftovers genuinely still open

13. `p.splits[]` (a cash parcela split across multiple favorecidos, contract 02's pattern) — blocks nothing in the CURRENT 8-sample corpus's re-generation except contract 02's own shape, but blocks any FUTURE deal that needs it.
14. `p.juros_am` for direct parcelas (distinct from confissão's `juros_am`, which IS stored).
15. `posse.prorrogacao_dias` + compensation split (contract 03's pattern) — no storage AND no clause paragraph; a genuine double-gap.
16. `rescisao.encargo_texto`'s honorários/custos/nenhum enum — the office instead hard-coded one fixed wording (§2 table), so this is likely CLOSED BY DECISION rather than open; flagged so a future reader doesn't rebuild it unprompted.
17. `n.lei_6515` clause-text wiring — the DATA (`data_casamento`) is stored and gated, but no clause branch in `modelo_texto.py` reads it into the Lei 6.515/77 wording yet. Distinct from a pure `no_source_yet` — it's "has data, missing template branch", same shape as gap (ii) items but scoped as a feature gap rather than a bug (no sample contract regression depends on it).

### The Rodrigo Moraschi Enriquez contract — worked example

Card `8f89279a-0121-4825-a1da-8aa7e51c257d`; matrícula extraction
`fcd9ce4a-f096-4dc2-99d5-1463bceed543` (matrícula 3.917, Alameda Alemanha
lote 14 quadra D, Residencial Euroville, Carapicuíba — the same imóvel
contract 08 of the 8 signed samples describes). **0 segmented atos, literal
markup in `texto_extraido`.** In dependency order, what must happen for
THIS contract to generate:

1. **Segment the matrícula's atos.** `derivacao.py:569` blocks generation
   outright (`matricula.atos`, `bloqueia` MATRICULA_DE_OUTRO_IMOVEL is not
   the failure here — it's the earlier `faltando` check) while
   `matricula_atos` has zero rows linked to this extraction. Run/re-run
   `matriculas/estrutura_service.py::persistir_atos` (normally triggered at
   upload time by `POST /api/matriculas/extrair`) — if it already ran and
   produced zero atos, the extraction's raw `texto_extraido` likely needs
   re-transcription first (gap (ii) #6: markup in the text can also defeat
   the act-boundary regex `estrutura_service.linhas_de_atos` relies on).
2. **Fix the markup.** Before or during step 1, the `**bold**`/`formatacao='[]'`
   defect (gap (ii) #6) must be resolved for this extraction specifically —
   otherwise even a successful act segmentation quotes malformed text in
   the eventual `{{r imovel.descricao_matricula }}` slot.
3. **Select the atos for this contract.** `PUT /api/matriculas/contratos/{contrato_id}/atos` — pick which segmented atos the objeto clause quotes.
4. **Confirm título aquisitivo.** `PUT /api/matriculas/imoveis/{codigo}/titulo-aquisitivo` — the AI suggestion off the now-selected atos, confirmed.
5. **Write `imovel_dados`.** `PATCH /api/imoveis/{codigo}/dados` — `numero_matricula='3.917'`, `numero_registro_imoveis`, `prefeitura_cadastro_imobiliario`, `situacao_onus` (even "livre" must be set explicitly — `derivacao.py:586` treats an unset value as `faltando`, not as "no ônus").
6. **If `situacao_onus` indicates a saldo devedor** (`ONUS_COM_SALDO`): confirm `onus.credor` (`PUT .../onus-credor`) and set `Termos.onus_quitacao` (`PUT .../negociacao/termos`).
7. **Qualify every signatory.** Confirm CPF/RG/gênero/estado civil (AI-suggest+confirm or direct `PATCH /clientes/{id}`) for every vendedor and comprador on the card; enter every party's endereço manually (gap (iii) #10 — no shortcut exists); enter `data_casamento` for any casado party.
8. **Certify every signatory.** All 12 PF certidão types per vendedor (and per comprador if this deal turns out to have `tem_permuta` — card 08's real contract did not), each with a confirmed `PATCH /certidoes/resultados/{id}`.
9. **Enter the deal terms.** `valor_negociado`, parcelas (with a single `sinal`, each with `favorecido_id`+conta/PIX), `posse_marco`/`posse_prazo_dias`, `itens_integrantes`/`ad_corpus` if applicable (08 is `V3 = V1 − itens + ad corpus` per spec §1.3 — `ad_corpus=true`, `itens_integrantes` empty is the EXPECTED shape for this exact card, not a gap).
10. **Confirm the org is configured once**: `razao_social`/`cnpj`/`responsavel_*`/`endereco_cidade`, 2 testemunhas with nome+RG (CPF and e-mail optional — e-mail only matters for sending), signing-platform name/URL, `posse_multa_diaria` — all org-level, done once, not per-deal.
11. Only then does `avaliar()` return `pronto=True` and `service.gerar` can render.

## 5 · Keeper — `check_contract_field_provenance_map`

`mcp/noctusai/tools/noctus/dev/compliance.py::check_contract_field_provenance_map`
(wired `--check-contract-field-provenance-map` in `mcp/noctusai/cli.py`, gated
in `scripts/hooks/pre-commit` whenever `modelo_texto.py`, `contexto.py`,
`derivacao.py`, or this doc itself is staged).

**Derives** the placeholder set per §3 above (AST over `modelo_texto.py`'s
`TEMPLATE` constant + `contexto.py`'s `montar_contexto` return-dict keys +
`derivacao.py`'s `derivar_switches` return-dict keys — zero hand-maintained
literal list on the CODE side). **Compares** against every fenced-table
first-column cell in this doc's §2 (a placeholder column entry) plus every
line of §3's appendix, and fails when a code-derived token has no
corresponding row anywhere in the doc — so a new field cannot be wired into
the F5 template without this map growing a row that declares its
provenance. Severity `high` (a silent-drift class: the exact anti-pattern
CLAUDE.md §1 names — "a hand-maintained list drifts and breaks the fleet").
