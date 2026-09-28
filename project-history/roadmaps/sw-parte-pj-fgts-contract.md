# PJ party ("Pessoa jurídica" switch) + FGTS CRF opt-in contract (social-wiring)

> Written 2026-09-25 by the `architect` advisor, read-only, against `origin/dev@4b9e88e59`. Paths are relative to `products/social-wiring/backend/` unless they start with `seed/`, `frontend/` or `mcp/`. The D1 (fill-empty, else conflict), D2 (a machine-read fact blocks `gerar` until a human confirms it) and provenance-quintet rules from `sw-drive-extraction-P0c-contract.md` apply unchanged. The owner decisions of 2026-09-25 are binding: the PJ switch is approved, the PJ certidão set is 11 items (no Serasa), and the CRF is out of generation by default. Real business calls are in §G only.

## 0. What already exists (verified)

**Parties**
- `atendimento_partes` (073:161-184) has `cliente_id NOT NULL` with `ON DELETE CASCADE`, a free-text `papel`, `ordem`, and `UNIQUE (atendimento_id, cliente_id)` (073:183). `lado` is comprador|vendedor (098:67).
- **The titular has no parte row.** It is a comprador by construction (`carregador.py:519-521`, and the guard in `compradores_service.adicionar` at :242-300).
- **There is no PF/PJ marker anywhere.** Slice D stopped at exactly this point on purpose (`empresas/checklist_service.py:16-27`, SCOPE CUT). The pointer for `feat/sw-empresas-edit-checklist` is `shipped`. It notes that migration 169 was left unused.

**Empresas model (migration 167)**
- `empresas` (167:61-101) has one row per `(org_id, cnpj)`, the Cartão fields, and one `dados_*` group quintet.
- **No address columns** (167:78-90, owner decision 2026-09-24). The stated reason was that no process consumed the address. A PJ party's qualification now does, so this contract supersedes that decision by its own reasoning. Say so in the commit.
- `cliente_empresa_participacoes` (167:131-150) links a person to a company as sócio. Its `origem` is serasa_crednet|manual|certidao_consulta.
- `empresa_documentos.tipo_documento CHECK IN ('cartao_cnpj')` (167:193). The Python side is `empresas/documentos_service.py:25`.
- `empresa_campo_conflitos` (167:~297) exists. The shared conflict writer already has a descriptor for it (`app/services/campo_conflitos.py:90`).
- `certidao_consultas.empresa_id` exists (167:370-378).

**Seed Cartão CNPJ**
- `seed/.../documents/cartao_cnpj.py:541-587` already extracts `logradouro/numero/complemento/cep/bairro/municipio/uf` plus `endereco_mascarado` (:570-580).
- The whole reading is stored in `empresa_documentos.extracao_dados`, but it is never promoted to a column. So the sede of an ativa company is already on disk.

**Generator**
- Qualification:
  - `frases.qualificacao` (:208-230) handles PF only.
  - `texto_pessoa(p, em_nucleo=True)` (:156-176) already omits estado civil.
  - `contexto.py:503-506` builds `V_qualificacao`/`C_qualificacao` from `Pessoa` lists.
  - `concordancia.lado(generos, …)` builds agreement from a gender list.
- **PJ wording already exists twice:** `frases.qualificacao_imobiliaria` (:575-590) and `frases.qualificacao_intermediario` (:593-626, the `pessoa_tipo == "pj"` branch plus `representante_nome/cpf`). A PJ party would be the third, and the recurrence rule makes formalizing it mandatory.
- Certidões:
  - `frases.CERTIDOES` (:370-383) is the 12-row table with PF/PJ columns. Serasa is PF-only. `fgts_regularidade` is **not** in it, so today it is never printed and never required.
  - `tipos_exigidos` (`derivacao.py:649-651`), `indice_certidoes` (:654-669), `conferir(p, certs, tipo_documento, nome_grupo)` (:1384-1430).
  - `conferir_empresas` (:1432+) runs E1 over `_empresas_de_certificandos` (:684-703), `classificar_situacao_pj` (:724-758), `motivo_publico` (:783-802) and `empresas_exigidas` (:805-821).
  - Rendering: `contexto.py:294-330` prints the PF groups, then the E1 PJ groups. `grupos_imovel` is at :333-346.
- Data:
  - `dados.Empresa` (:141-163) has no sede, NIRE or representation fields.
  - `DadosContrato` (:479+) carries `empresas`, `processo_legado` and `modalidade_assinatura`, both read off `atendimento_contratos`.
  - `PAPEIS_SEM_REDACAO` (:544) already refuses to draft for `procurador`. That is the honest-refusal precedent reused below.
- Signatures are data-driven (`modelo_texto.py:205-245`: the `V_signatarios` / `V_assinantes_fisicos` lists), so **no template change is needed** for signers.

**Card surfaces**
- `card_hub/empresas_service.pessoas_do_card` (:77) is the single "who is on this card" source for the Empresas tab and the certidões matriz (`certidoes_matriz_service.py:135-208`, which greys Serasa for EMP columns at :321).
- `listar` (:185) returns `motivo`/`exige_certidoes`, using the vocabulary from `motivo_publico`.

**Certidões**
- `certidoes/registry.py:180-190` defines `MANUAL_TIPOS_CONFIG`, including `fgts_regularidade` with `aplicavel_a=("cnpj",)`. `_fan_out_tipos_manuais` (`routers/certidoes.py:224`) creates its manual placeholder on every CNPJ consulta, and it is matriz row 5.13 (`registry.py:514`).
- **So "addable at any time" already holds.** Only generation changes.

**Contract-level switches**
- `atendimento_contratos` (106:47) plus `processo_legado` (151:54-57, with `_por/_em/_motivo`) and `modalidade_assinatura` (157:53).
- Editable fields are in `contratos_service.py:80-88`; `atualizar` is at :781. `ContratoPatchBody` is at `card_hub/schemas.py:394`.
- FE: `frontend/src/components/card/ContratoModalidadeSection.tsx`.

**FE entry points**
- `AdicionarCompradorDialog.tsx` (194 lines): one dialog for both sides (`variant` at :52-62, component at :94).
- `EmpresasSection.tsx:504-534`: `EmpresaChecklist` and `EmpresaCartaoSlot`.
- `EnviarAssinaturaDialog.tsx:87`: `partesParaSignatarios(compradores, vendedores)` pre-fills the e-signature signers.

**Evidence from the Drive census (41 folders; flags and shape only)**
- **Exactly one real PJ-vendedor deal, 866** (closed). 0 of 40 contracts have a PJ comprador. The other "inscrita no CNPJ" hits are imobiliária/intermediário clauses. The one aditivo hit (873) is not a sale party.
- 866 opening, as a shape:
  `VENDEDORA: <RAZÃO SOCIAL>, pessoa jurídica de direito privado, devidamente inscrita sob CNPJ nº <cnpj> e NIRE <11 dígitos>, com sede na <endereço completo + CEP>, representada neste ato por sua única sócia <nome>, <nacionalidade>, <profissão>, portadora da cédula de identidade RG <rg> e inscrita no CPF/MF <cpf>, com endereço eletrônico: <email> residente e domiciliada na <endereço>.`
  - **No estado civil** for the representante.
  - **No capital social.**
  - Side agreement is feminine singular ("VENDEDORA").
- 866 also qualifies the **sócia's spouse in the preamble**, with an anuência clause ("na qualidade de cônjuge da única sócia e representante legal … expressa concordância e anuência … outorgando plenos poderes"). See §G Q2.
- 866 certidões, in order:
  - The PJ vendedora's group: **12 items, including Serasa**. The owner's 11-item rule supersedes this, so expect that diff at E2E.
  - Then **two PF groups** (the sócia and her spouse), each 12 items.
  - Then **four more PJ groups** of 11 items (their other companies, i.e. E1).
  - Then the documents group: "Visualização da matrícula; **Cartão do CNPJ; Contrato Social**; CNH [da] Sócia Proprietária".
- 866's folder holds a CRF file, but **no contract in any folder lists a CRF** (0 of 40). This is consistent with owner decision 2.
- The 866 contrato social has a text layer (~20k chars). It carries the JUCESP stamp with the **NIRE**, the sede, the sócios and "administração … isoladamente".
- Registry documents found in the census:
  - Contrato social: 3 files (2 text layer, 1 image only), in folders 685, 783 and 866.
  - Junta ficha/certidão: 866, 835 and 783.
- **The answer-key parser has no PJ-party vocabulary.** In 866 it parsed the PJ vendedora as PF partes (`confianca=revisao`, `grupos=[]`). See S5.

## A. Data model and migration

**Decision: the party IS the empresa, in its own table. Do not overload `atendimento_partes`.**
- `atendimento_partes.cliente_id` is NOT NULL and every existing consumer reads each row as a person to qualify:
  - `carregador.py:523-529`
  - `pessoas_do_card`
  - the checklist
  - `partesParaSignatarios`
  - `vincular_parte`
- Overloading it would print the representante as a PF vendedor wherever a consumer was not updated. That is the silent-wrong-contract failure.
- A separate table **fails safe**: a consumer that knows nothing about it simply does not see the PJ party. A PJ-only side then hits the existing "Ao menos um vendedor" falta.
- DRY: the party points at the **existing `empresas` row**, upserted by `(org_id, cnpj)`. The Cartão CNPJ is uploaded and extracted through the existing `empresa_documentos` pipeline. There is no parallel company model.

**Migration `NNN_partes_pessoa_juridica.sql`**
- Take NNN from `noctus.dev.next_migration_number social-wiring` at build time. Expect 172 or later: 171 is being written on `feat/sw-neg-s2-backend`. 169 is an unused gap; do not backfill it.
- Only the tech-lead applies it, via `migrate_product`.

1. **`atendimento_partes_pj`**
   - Columns: `id`, `org_id`, `atendimento_id` (FK atendimentos, ON DELETE CASCADE), `empresa_id` (FK empresas, **ON DELETE RESTRICT**: the Empresas-tab delete must answer 409 with pt-BR copy and not orphan a party), `lado TEXT NOT NULL CHECK IN ('comprador','vendedor')`, `ordem INT NOT NULL DEFAULT 0`, `observacao`, `created_at/by`, `updated_at`.
   - `UNIQUE (atendimento_id, empresa_id)`: the same company cannot sit on both sides of one deal.
   - Index `(org_id, atendimento_id)`. RLS: select own org, plus service role (the 167 pattern).
2. **`atendimento_parte_pj_representantes`**
   - Columns: `id`, `org_id`, `parte_pj_id` (FK, CASCADE), `cliente_id` (FK clientes, CASCADE; the 073 reasoning applies, and a lost representante becomes a visible falta), `ordem`, `created_at/by`.
   - `UNIQUE (parte_pj_id, cliente_id)`.
   - **There is no "qualidade" column.** The power to represent is a fact about the company, read from its documents (item 3). It is not typed per deal.
3. **`empresa_administradores`** (company-level facts, reusable across deals, the same "one row every time" principle as 167)
   - Columns: `id`, `org_id`, `empresa_id` (FK, CASCADE), `nome TEXT NOT NULL`, `cpf TEXT CHECK (cpf ~ '^[0-9]{11}$')` (nullable), `cargo TEXT NOT NULL CHECK IN ('socio_administrador','administrador')`, a quintet (`origem`, `documento_id` FK empresa_documentos ON DELETE SET NULL, `em`, `confirmado_por`, `confirmado_em`), `created_at`.
   - `UNIQUE (empresa_id, cpf)`.
4. **`empresas`: new columns**
   - Sede: `sede_logradouro`, `sede_numero`, `sede_complemento`, `sede_bairro`, `sede_cidade`, `sede_uf`, `sede_cep`, with their own quintet `sede_*`. The sede has two possible sources (Cartão, contrato social/ficha), so it cannot share `dados_*`.
   - Registry facts: `nire TEXT CHECK (nire ~ '^[0-9]{11}$')`, `administracao TEXT CHECK IN ('isolada','conjunta')`, `socios_quantidade INT CHECK (>0)`, with one quintet `registro_*`.
   - **No capital column.** 866 does not print it. The value stays in `extracao_dados`.
5. **`empresa_documentos.tipo_documento` CHECK** widens to `('cartao_cnpj','contrato_social','ficha_cadastral')`. Add retention platform rows for the two new tipos (superficie `empresa`, same days as the 167 `cartao_cnpj` row).
6. **`atendimento_contratos`**: add `incluir_crf_fgts BOOLEAN NOT NULL DEFAULT false`, `incluir_crf_fgts_por UUID`, `incluir_crf_fgts_em TIMESTAMPTZ`. See §D.
7. **No backfill.** No PJ party exists yet. When a PJ party is created, if the empresa already has an `ok` Cartão whose address is not masked and `sede_*` is empty, fill the sede from the **stored** `extracao_dados`. That is fill-empty with `sede_origem='cartao_cnpj'`, left D2-pending, and costs no re-extraction.

**D1/D2 rules for the new facts**
- The first document fills. A later document that disagrees opens an `empresa_campo_conflitos` row through the existing `EMPRESA` descriptor. New `campo` values: `sede`, `nire`, `administracao`, `socios_quantidade`, `administradores`.
- `administradores` is conflicted **as a set**: an alteração contratual that changes the administradores is never auto-replaced.
- Manual entry stamps `origem='manual'`.

## B. Contract qualification text for a PJ party

**Formalize before adding the third copy (recurrence rule).**
- New helpers in `frases.py`:
  - `pj_identificacao(razao, cnpj, *, nire=None, nome_fantasia=None, creci=None, de_direito_privado=False)`
  - `pj_sede(endereco)`
  - `pj_representacao(representantes, *, socios_quantidade)`
- Refactor `qualificacao_imobiliaria` and `qualificacao_intermediario` onto these helpers with **their goldens byte-identical**. That is the acceptance test.

**`frases.qualificacao_parte_pj(p: ParteEmpresa) -> str`**

```
{RAZÃO SOCIAL}, pessoa jurídica de direito privado, inscrita no CNPJ sob o nº {cnpj}[ e NIRE {nire}], com sede na {endereco_texto(sede)}, neste ato representada por {rep}
```

- **Single representante:**
  - `"{seu sócio administrador | sua sócia administradora | seu administrador | sua administradora} {texto_pessoa(r, em_nucleo=True)}, {residente e domiciliado(a)} na {endereco_texto(r.endereco)}"`.
  - Gender comes from `r.genero` via `_g`. `cargo` comes from the matched `empresa_administradores` row.
  - Use **"sua única sócia" / "seu único sócio"** only when `socios_quantidade == 1` **and** that fact is confirmed. This matches 866.
- **Several representantes:** "seus sócios administradores" (or "seus administradores" when the cargos differ), then each person's qualification joined with ", e ".
- "inscrita no CNPJ sob o nº" is the house style (`qualificacao_imobiliaria`). 866's "inscrita sob CNPJ nº" is accepted drift. The facts must match 100%; the connective wording may differ.

**Side composition** (`contexto.py`)
- `V_qualificacao` = the PJ parties of that side first (866 order), then `frases.qualificacao(PF…)`, joined with ", e ".
- Agreement: `concordancia.lado(generos_PF + ["f"] * n_pj, …)`. One PJ alone gives "a VENDEDORA", as in 866. Representantes contribute no gender to the side.
- Signers:
  - Digital: `f"{RAZÃO} – p.p. {REP NOME}    {rep email}"`, one line per representante.
  - Física: `{nome: "RAZÃO p.p. REP", documento: "CNPJ …"}`.
  - The template is unchanged.
- `EnviarAssinaturaDialog.partesParaSignatarios` adds the representantes as signers.

**Gate** (`derivacao._partes`, plus a new `_partes_pj`)
- "Ao menos um vendedor" is satisfied by a PF **or** a PJ party.
- Faltas, each keyed `parte_pj.<id>.*` with a destino to the PJ block:
  - `cartao_cnpj`
  - `sede`
  - `nire` (only for a Junta-registered natureza)
  - `representante` (none linked)
  - `administracao`
  - each representante's PF qualificação keys: nome_oficial, nacionalidade, genero, RG/órgão, CPF, endereço. Estado civil is **not** required. A missing e-mail is an aviso (`PARTE_SEM_EMAIL` path).
- Bloqueios:
  - `CNPJ_INVALIDO` (DV check).
  - `PARTE_PJ_SITUACAO` when situação ≠ `ativa` (see §G Q4).
  - `PARTE_PJ_NATUREZA_SEM_REDACAO`: v1 drafts only for Ltda, SLU and EI (natureza 206-2, 213-5, 230-5). S/A, S/S, associações and similar forms have a different representation regime and get the same honest refusal `PAPEIS_SEM_REDACAO` gives.
  - `REPRESENTANTE_NAO_ADMINISTRADOR`: the representante's CPF does not match a D2-confirmed `empresa_administradores` row.
  - `ADMINISTRACAO_CONJUNTA_INCOMPLETA`: administração is `conjunta` but not every administrador is linked as a representante.
- A procuração-based representante is out of scope for v1. It falls into the same honest refusal.

**Titular rule.** If the titular is a representante of a comprador-side PJ party, the titular is **not** also printed as a PF comprador. See §G Q5.

## C. Checklist and certidões for a PJ party

**Checklist** (`empresas/checklist_service.listar(..., como_parte: bool)`; the route `GET /api/empresas/{id}/checklist?atendimento_id=` derives `como_parte` from an `atendimento_partes_pj` row)

| item_key | título | Required | Satisfied when |
|---|---|---|---|
| `cartao_cnpj` | Cartão CNPJ | always (existing) | upload exists |
| `contrato_social` | Contrato social / última alteração consolidada | como_parte | upload exists |
| `dados_cadastrais` | Dados cadastrais (Ficha Cadastral da Junta Comercial) | como_parte; see §G Q6 | upload exists |
| `socios_representantes` | Sócios / representantes | como_parte | ≥1 representante, each matched to a confirmed administrador, and the administração rule passes (the same predicate the gate uses; import it, never restate it) |

Representantes' identity documents use each cliente's **existing** per-cliente checklist. The PJ block links to it; no new PF checklist is built.

**Certidões**
- A PJ party on a certificando side (vendedor always; comprador only when `tem_permuta`, per E6) **always** requires the **11-item `tipos_exigidos("cnpj")` set**. This does not go through E1's ativa/baixada window, because an irregular situação already blocks (§B).
- Dedupe by `empresa.id` (E4): if the PJ party is also an E1 company of a certificando, print it once, with the PJ party wins attribution.
- Group order: PJ party groups first, then PF certificandos, then E1 companies. This matches 866.
- `conferir` gains a destino argument in place of `Pessoa` (it only reads `p.parte_id`) so a PJ falta navigates to the PJ block.
- `DadosContrato.empresas` stays the one E4-deduped list. PJ-party empresas are merged in, which means `validacao_extracao.coletar`'s D2 loop (:595-600) covers them automatically. New `CampoValidavel` entries: `empresa.sede`, `empresa.registro`, `empresa_administradores`.
- `empresas_service.listar`/`pessoas_do_card` include PJ-party empresas with `motivo='parte_pj'`, `exige_certidoes=True`. The matriz EMP column and the Serasa N/A (`certidoes_matriz_service.py:321`) then follow **with no matriz edit**.
- `motivo` comes from a new `derivacao.classificar_parte_pj`, shared by the badge and the gate. This is the same N=2 discipline as `motivo_publico`.
- **Documents group** (`contexto.py`): when a PJ party exists, add a group "Documentos de {RAZÃO}" with the items "Cartão do CNPJ" and "Contrato Social" (866 listed both), using new constants in `frases`. The "CNH da sócia" line is covered by the existing `PENDENCIA_DOCUMENTOS`.
- Print `pendencia_estado_civil` only when a PF certificando exists.

**Representantes.** Whether they are certificandos is §G Q1. It is implemented as `Politica.representante_pj_certificando` (default per the owner's answer). When it is true:
- representantes enter `pessoas_certificadas` and `pessoas_do_card` (`papel='representante_pj'`);
- they get the PF 12-item set, their E3 cônjuge, and their E1 companies (the 866 shape).

**Out of scope for v1:** a PJ `antigo_proprietario`. It keeps today's PF-only path, and that is flagged in the delivery note.

## D. FGTS CRF opt-in

- **Where the flag lives: per contrato**, `atendimento_contratos.incluir_crf_fgts` (§A.6). The alternative was per deal.
  - This follows the exact precedent of `processo_legado` and `modalidade_assinatura` (contract-level switches read by `carregador` into `DadosContrato`).
  - A lawyer's request is for a specific instrument.
  - In practice a deal has one generated contract, so it matches the owner's "per deal" intent. There is no deal-level duplicate.
- **Audit:** `atualizar` stamps `_por`/`_em` whenever the key changes. It is not admin-only; it is an ordinary operator decision.
- **Wire shape:**
  - `ContratoPatchBody.incluir_crf_fgts: Optional[bool]` (`schemas.py:394`).
  - `CAMPOS` in `contratos_service.py:80-88`.
  - The contract GET/list payload returns `incluir_crf_fgts`, `incluir_crf_fgts_por` (the actor, as for `processo_legado_por`) and `incluir_crf_fgts_em`.
- **Rendering:**
  - Add `frases.CERTIDOES_OPCIONAIS = (("fgts_regularidade", "Certificado de Regularidade do FGTS – CRF", "nº", False, True, None),)`. The label has no `{R}`; a CRF is a certificate of regularity, not a negativa/positiva. Its wording is "emitido em", masculine.
  - `rotulo_certidao`/`item_certidao` look up `CERTIDOES + CERTIDOES_OPCIONAIS`.
  - `tipos_exigidos(tipo_documento, *, opcionais=())` appends the opted-in tipos at the end (office order). `d.incluir_crf_fgts` passes `("fgts_regularidade",)` for **every printed PJ group**, whether a PJ party or an E1 company.
  - `nao_emitida` renders a "– PENDENTE" line plus a pendência letter (the existing path).
  - The 30-day emission rule and the validade rule apply through the existing `tempo()`.
  - A `positiva` CRF (irregular) takes the existing `CERTIDOES_POSITIVAS` path.
- **When the flag is ON and a CRF is missing:** my recommendation is **falta**, by the same `conferir` path. Once the lawyer asked for it, a listing that silently omits it is the silent-error shape. The scope of the falta is §G Q3.
- With the flag OFF, nothing changes. The matriz row 5.13 and the manual fan-out stay as they are, so the CRF can still be added at any time.
- **UI:** in `ContratoModalidadeSection.tsx`, a switch "Incluir CRF (FGTS) das empresas nas certidões" with helper text "Use somente quando o jurídico solicitar." Show `por/em` when it is on.

## E. Extractors (seed, `seed/lib/backend/noctusai_lib/integrations/documents/`)

The evidence requires them. The **NIRE is printed (866) and is not on the Cartão**, and the **power to represent comes only from the contrato social**. Both follow the `cartao_cnpj.py` shape: frozen `*Fields` plus `confiancas`/`rotulos`/`aviso`/`error`, `extract(text_ladder)`, a Fake in `fake.py`, registered in `capacidades.py` and `__init__.py`.

- **`contrato_social.py`, `ContratoSocialFields`**
  - Fields: `razao_social`, `cnpj`, `nire` (from the Junta stamp; 11 digits), `tipo_ato` (constituição|alteração|consolidação), `data_arquivamento`, `sede`, `socios` [{nome, cpf}], `administradores` [{nome, cpf, cargo}], `administracao` (isolada|conjunta|None), `socios_quantidade`, `capital_social` (read into JSON, never promoted).
  - Classify `administracao` from clause patterns ("isoladamente", "individualmente", "em conjunto", "conjuntamente"). If the text is ambiguous, return None plus an aviso. Never guess.
  - A CPF that fails the DV check becomes None; never correct it. Vision output is never `alta`.
  - Text layer is deterministic. Image-only uses the ladder vision rung. Page targeting uses the `paginas=` added on `feat/sw-neg-s1-seed`: first two pages (sócios, sede) plus the last two (the Junta stamp). The administração clause needs a full read, so the result is `too_many_vision_pages` ⇒ manual rather than a partial guess.
- **`ficha_cadastral.py`, `FichaCadastralFields`** (JUCESP Ficha Cadastral simplificada/completa, or Certidão Simplificada)
  - Fields: `nire`, `razao_social`, `cnpj`, `sede`, `socios`/`administradores` with cargo, `data_ultimo_arquivamento`.
  - The Receita QSA is **not** accepted as a NIRE source: it has no NIRE and it masks CPFs.
- Shared parsing (sócio/administrador line parsing, the administração classifier) lives in a private `_registro_empresarial.py`. It is not duplicated across the two modules.

**SW apply** (`empresas/extracao_service.py` dispatch by tipo, plus `dados_service.aplicar_registro`)
- D1 fill or conflict on `nire`, `administracao`, `socios_quantidade`, `sede_*` and the `empresa_administradores` set.
- Administradores are matched to linked representantes **by DV-valid CPF only**. A name-only match is an aviso and is never auto-linked.
- An administrador who is not a representante yet surfaces as a one-click suggestion ("Adicionar como representante"). That links an existing cliente by CPF, or creates one from nome+CPF on the operator's click.
- The existing empresas sweep is tipo-agnostic (pendente rows), so the new tipos ride it. `sweep_service.py` is not edited.
- `proveniencia/fontes.py`: new Fontes `contrato_social` and `ficha_cadastral` (dominio `empresa`, `Entrada.EMPRESA_CARD_UPLOAD`) with their `campos`.

## F. Slices (file-disjoint)

| Slice | Paths | Tests (acceptance) | Collision / sequencing |
|---|---|---|---|
| **S1 seed** (engineer-seed) | `seed/.../documents/{contrato_social.py, ficha_cadastral.py, _registro_empresarial.py, fake.py, capacidades.py, __init__.py}`, `seed/lib/backend/tests/integrations/documents/test_{contrato_social,ficha_cadastral}.py` | Synthetic text only. Isolada, conjunta and ambiguous ⇒ None plus aviso. NIRE read from a stamp line. Bad CPF DV ⇒ None. A sócio-administrador vs a non-sócio administrador gets the right cargo. Vision never `alta`. Existing seed suite green. | `__init__.py`/`capacidades.py` are touched by `feat/sw-neg-s1-seed` (complete, awaiting integration): **C3, dispatch after it integrates**. `cartao_cnpj.py` is on `feat/sw-p1-fixes-2`; S1 does not touch it. |
| **S2 SW backend: model, routes, apply** (backend-engineer) | `migrations/NNN_*.sql`, `migrations/APPLIED.md`, `app/modules/empresas/{partes_service.py (new), partes_router.py (new), __init__.py (register the router; no `main.py` edit), checklist_service.py, documentos_service.py, dados_service.py, extracao_service.py, router.py}`, `app/modules/card_hub/{empresas_service.py, contratos_service.py, schemas.py}`, `app/modules/card_hub/proveniencia/fontes.py`, `tests/modules/empresas/test_partes_pj*.py`, `tests/modules/card_hub/test_contratos*.py` | Routes (§F-API below): auth strictly `== 401` on every route. 400 on a bad CNPJ DV or bad lado. 409 on a duplicate PJ party. Deleting an empresa that is a party ⇒ 409 (plus a realdb FK test). A foreign cliente ⇒ 404. Checklist `como_parte` toggles its 3 items. Cartão sede backfilled from stored JSON (masked ⇒ not filled). Registry apply is fill-empty, and a differing set ⇒ conflict. CPF-only matching. `listar` returns `motivo='parte_pj'`. CRF PATCH stamps por/em. **At least one `NOCTUS_REALDB_TESTS=1` test** covering the RESTRICT/CASCADE FKs (P1 G5 lesson). Fontes REGISTRO sweep stays exhaustive. | 🔴 `dados_service.py`, `extracao_service.py` and `certidoes_matriz_service.py` are on `feat/sw-p1-fixes-2`. 🔴 `fontes.py` and migration 171 are on `feat/sw-neg-s2-backend`. **C3: dispatch after both integrate.** Does not touch `card_hub/router.py`, `deps.py`, `app/services/` or `main.py`. |
| **S3 generator** (backend-engineer) | `app/modules/card_hub/contrato_gerador/{dados.py, carregador.py, derivacao.py, frases.py, contexto.py, politica.py, validacao_extracao.py}`, `tests/modules/card_hub/{test_contrato_gerador_pj.py (new), contrato_gerador_fixtures.py}` | Imobiliária/intermediário goldens byte-identical after the helper extraction. PJ-only vendedor side renders "a VENDEDORA". PJ first, then PF, joined. "única sócia" only when `socios_quantidade==1` and confirmed. No estado civil for the representante. Each §B falta and bloqueio fires. PJ group has 11 items without Serasa, deduped vs E1. CRF off ⇒ absent. CRF on ⇒ listed plus falta when missing; `nao_emitida` ⇒ PENDENTE. D2-pending registry/sede ⇒ `gerar` 409. PF-only fixtures produce unchanged goldens. | 🔴 `dados.py`, `carregador.py` and `validacao_extracao.py` are on `feat/sw-neg-s2b-gate` (ready): **C3, dispatch after it integrates**. `derivacao.py`/`frases.py` are free. Codes to the §A column names. The carregador reads are verified on the merged tip. |
| **S4 FE** (frontend-engineer) | `frontend/src/components/card/{AdicionarCompradorDialog.tsx, ParteEmpresaBlock.tsx (new), EmpresasSection.tsx, ContratoModalidadeSection.tsx, EnviarAssinaturaDialog.tsx, ClienteCardDialog.tsx}`, `frontend/src/hooks/{usePartesPj.ts (new), useEmpresas.ts, useContratos.ts}`, `frontend/src/types/partesPj.ts (new)`, `frontend/src/lib/documentoTipos.ts`, colocated `*.test.tsx` | "Pessoa jurídica" switch on the vendedor/comprador variants, hidden for `conjuge`. When ON: CNPJ (DV-checked) plus a Cartão upload is the preferred path, plus the representante picker (reuses the PF link/create sub-form). The PJ block shows razão, situação, sede and NIRE with provenance badges, the checklist (4 items), the contrato social/ficha slots via the shared `DocumentoTipoSlot` (polling to terminal), and the administrador suggestions. Signers include the representantes. CRF switch. Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`. pt-BR copy. | 🔴 `EmpresasSection.tsx`/`useEmpresas.ts` are on `feat/sw-p1-fixes-2`; `documentoTipos.ts` is on `feat/sw-neg-s3-frontend`: **C3, after both integrate**. `cardSubpages.ts` is not touched. |
| **S5 answer-key vocabulary** (engineer-seed) | `mcp/noctusai/tools/noctus/dev/drive_census.py` plus its tests | The answer key gains `partes_pj[]` (razão, cnpj, nire, sede, representantes, anuentes). 866 re-parses with its PJ vendedora as a PJ, not as PF. No personal values in results. | Free, C1. Can run in parallel now. |

**§F-API (contract-first; S2 builds exactly this, S4 codes against it)**
- `GET /api/clientes/{cliente_id}/partes-pj?lado=` → `{items: [{id, lado, ordem, empresa: {id, cnpj, razao_social, nome_fantasia, natureza_juridica, situacao_cadastral, data_situacao_cadastral, nire, administracao, socios_quantidade, sede: {logradouro, numero, complemento, bairro, cidade, uf, cep}, dados_origem, sede_origem, registro_origem}, representantes: [{id, cliente_id, nome, cpf, cargo | null, administrador_confirmado: bool}], administradores_sugeridos: [{nome, cpf, cargo}], checklist: {items: [...]}, pronto: bool}]}`
- `POST /api/clientes/{cliente_id}/partes-pj` with `{lado, cnpj, razao_social?, representantes?: [{cliente_id} | {nome, celular?, cpf?}]}` → 201, returning the item.
- `DELETE /api/clientes/{cliente_id}/partes-pj/{id}` → 204. This removes the party only, never the empresa.
- `POST|DELETE /api/clientes/{cliente_id}/partes-pj/{id}/representantes[/{rep_id}]`
- Empresa document upload, extract, confirm and discard reuse the existing `/api/empresas/{id}/documentos*` routes (`empresas/router.py:98-229`) with the new tipos.
- `PATCH` contrato with `{incluir_crf_fgts: bool}`.

**Gates on the merged tip:** `noctus.dev.gate_sweep` (social-wiring pytest and vitest, seed-lib, vite build), then `predeploy_check social-wiring`.

**E2E** (uploads only; no extractable value is typed)
1. Create card `[TESTE PJ] 866`. Add the vendedor through the PJ switch using only the Cartão CNPJ upload. Upload the contrato social and the Junta document from the 866 folder.
2. Link the sócia by uploading her identity document. The representante match must come from the contrato social extraction.
3. Upload the PJ's and the PF certidões. Generate.
4. Diff against the 866 REV FINAL with `tests/e2e_contrato/harness.py`.
   - Razão, CNPJ, NIRE, sede and the representante's facts must match 100%.
   - Expected, accepted diffs: "inscrita no CNPJ sob o nº" wording; no Serasa line in the PJ group (owner's 11-item rule); the documents group layout; the anuente, depending on §G Q2.
5. CRF:
   - OFF ⇒ absent (matches 866).
   - ON ⇒ listed from the CRF in the folder.
   - ON with an empresa that has no CRF ⇒ the falta named per §G Q3.
6. Append the scorecard to `project-history/roadmaps/sw-drive-extraction-P1-883-log.md`, or a sibling 866 log.

## G. Owner questions (business calls only)

1. **Representantes as certificandos.** In 866 the office printed the sócia's own PF certidões, her spouse's, and certidões for 4 other companies they hold. Should a PJ party's representante (and their cônjuge and their other companies) get the full vendedor certidão treatment? My recommendation: **yes for sócio-administradores** (matches 866); no for a non-sócio administrador.
2. **Anuência of the representante's spouse.** 866 qualified the sole partner's spouse in the preamble, with an anuência clause. Is that required whenever the representante is married, only when the company has one sócio, or never? My recommendation: **never by default**, since it is a company asset. If you want it, we add an `anuente` role and need the clause text.
3. **CRF opt-in, falta scope.** When the CRF is switched on and a company has none: (a) falta for every company group in the contract [recommended]; (b) print only the CRFs that exist, never a falta; (c) falta only for the PJ party itself.
4. **PJ party that is not `ativa`.** Should an `inapta` or `suspensa` seller company block generation [recommended: block; only `ativa` passes], or pass with a warning?
5. **A company as buyer.** Outside a permuta there is 0 evidence in 41 folders. Confirm the PJ switch should also exist for compradores (qualification only; certidões only in a permuta). Also confirm this rule: when the card's titular is the representante of the buying company, the titular is not printed again as an individual buyer.
6. **"Dados cadastrais".** Is this the Junta Comercial's Ficha Cadastral, and is it **required** even when the contrato social is on file? My recommendation: accept either document as the source of NIRE and administration; mark `dados_cadastrais` as required only when the contrato social does not yield a confirmed NIRE.

## H. Recommended tech-lead calls (mine; ratify or amend)

- The party is the `empresas` row in its own `atendimento_partes_pj` table. That table is fail-safe for unaware consumers; overloading `atendimento_partes` is not.
- Representation power is a **company fact** (`empresa_administradores`, from the documents) that the gate checks. It is never a per-deal typed "qualidade".
- The PJ wording is formalized into shared `frases` helpers (third instance). The existing goldens are the proof that nothing moved.
- v1 drafts only for Ltda, SLU and EI. Other legal forms and procuração-based representation get an honest refusal, the same as `PAPEIS_SEM_REDACAO`.
- Capital social is not printed or stored as a column (866). "única sócia" appears only when a confirmed `socios_quantidade==1`.
- The CRF flag lives on the contract row, next to `processo_legado` and `modalidade_assinatura`. There is no deal-level duplicate.
- Migration number is taken at build time (≥172). 169 stays a gap.
- Wave order:
  - Now: S5, and S1 once `feat/sw-neg-s1-seed` lands.
  - After `feat/sw-neg-s2b-gate` integrates: S3.
  - After `feat/sw-p1-fixes-2`, `feat/sw-neg-s2-backend` and `feat/sw-neg-s3-frontend` integrate: S2, then S4.

## Owner answers (2026-09-25), binding; they override §B/§C/§G where they differ
- Q1: **deal 866 is an EXCEPTION. Do not model on it.** A PJ party needs ONLY the company's own certidões (the 11-item PJ set). Representantes are NOT certificandos: no PF certidões, no cônjuge, no E1 companies for them. `Politica.representante_pj_certificando` is not built (or is fixed False).
- Q2: anuência of the representante's spouse: NEVER by default (no anuente role in v1).
- Q3: CRF opt-in ON + a company without a CRF ⇒ falta for EVERY company group listed.
- Q4: a PJ party whose situação ≠ ativa is NOT blocked. Its certidões are required the same way ("we need those certidões as well"). Drop the `PARTE_PJ_SITUACAO` bloqueio; the 11 certidões are always required for a PJ party regardless of situação.
- Q5, Q6: not asked yet; the architect's recommendations stand as defaults until the owner overrides (PJ switch on both sides, qualification only for compradores outside a permuta; the titular is not re-printed as PF when they represent the buying PJ; dados_cadastrais required only when the contrato social yields no confirmed NIRE).
- Since 866 is an exception, its wording ("única sócia", NIRE, the documents group) is NOT a golden. The qualification text still needs razão/CNPJ/sede/representante; the E2E diff against 866 is informational only.
