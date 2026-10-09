# Signing companies (imobiliárias) per org — FE↔BE contract

Status: AUTHORED 2026-10-09 by noc-1 (tech-lead for this slice). Both slices build TO this file; neither side re-derives it.
Home: `products/social-wiring/projects/signing-companies/CONTRACT.md` (the BE slice commits it).

## Why
Deal 876's signed contract qualifies TANGERINO CONSULTORIA IMOBILIÁRIA LTDA (CNPJ 06.057.235/0001-04), which is also the commission PIX payee. But `org_dados_cadastrais` holds ONE company per org (PK `org_id`). Prod today has 1 org row (ONE CONSULTORIA IMOBILIÁRIA LTDA, CNPJ 40.479.637/0001-27) and 22 contracts.

## Owner decisions (2026-10-09, verbatim choices)
- D1 **Identity per company; ops stay org-wide.** Per company: razão social, nome fantasia, CNPJ, CRECI-PJ, CRECI-PJ região, responsável nome, responsável CRECI, responsável CRECI região, telefone, e-mail, endereço (its city = signing place). Org-wide and UNCHANGED on `org_dados_cadastrais`: `plataforma_assinatura_*`, `posse_multa_diaria`, `prazo_pendencias_padrao_dias`, `suporte_*`.
- D2 **Backfill: all existing contracts = the migrated company.** The org's current row becomes registry entry #1 and every existing contract of that org records it as its chosen company, so they regenerate exactly as today.
- D3 **CRECI região: two separate fields**, one for the company's CRECI-PJ and one for the responsável's CRECI, each printed independently.
- D4 **PIX payee: warn on mismatch.** Payees stay typed per deal. The contract checker emits a NON-BLOCKING aviso when the office's commission payee CPF/CNPJ differs from the chosen company's CNPJ.
- Spec (owner, via noc-0): the org registers N companies; on the card the user MUST choose which one signs; the chosen company's data feeds generation; same mechanism family as witnesses (migration 168). No selection ⇒ the validator flags it (never a silent fallback); exactly ONE active company registered ⇒ it is auto-selected.

## DB (migration = next free number; run `noctus.dev.next_migration_number`, ≥215)
1. `social_wiring.org_imobiliarias`:
   `id uuid pk default gen_random_uuid()`, `org_id uuid not null references public.organizations(id) on delete cascade`,
   `razao_social text`, `nome_fantasia text`, `cnpj text`, `creci_pj text`, `creci_pj_regiao text`,
   `responsavel_nome text`, `responsavel_creci text`, `responsavel_creci_regiao text`, `telefone text`, `email text`,
   `endereco_cep/logradouro/numero/complemento/bairro/cidade/uf text` (same names as `org_dados_cadastrais`),
   `created_at timestamptz not null default now()`, `created_por uuid`, `updated_at timestamptz`, `updated_por uuid`,
   `excluida_em timestamptz` (SOFT delete, same posture as `org_testemunhas` / migration 168: never hard-deleted).
   Partial unique index: `(org_id, regexp_replace(cnpj,'\D','','g')) WHERE excluida_em IS NULL AND cnpj IS NOT NULL`.
   Index `(org_id)`.
2. `atendimento_contratos.imobiliaria_id uuid NULL REFERENCES social_wiring.org_imobiliarias(id) ON DELETE RESTRICT` + index.
   ONE company per contract ⇒ a nullable FK, not a join table (witnesses need N, this needs exactly 1).
3. Backfill (idempotent): for each org with an `org_dados_cadastrais` row AND zero `org_imobiliarias` rows, insert one registry row copying the identity columns (regiões NULL). Then `UPDATE atendimento_contratos SET imobiliaria_id = <that row> WHERE org_id = … AND imobiliaria_id IS NULL`.
4. `org_dados_cadastrais` identity columns are NOT dropped (forward-only); COMMENT each as "superseded by org_imobiliarias (migration N) — no longer read or written". The API stops reading/writing them.
5. RLS on `org_imobiliarias`, org-picker shape (migration 211): `<t>_select_own_org` FOR SELECT TO authenticated USING `(org_id = (SELECT public.current_org_id_for('social_wiring')))`; `<t>_write_own_org` FOR ALL TO authenticated USING/WITH CHECK same; `<t>_service_role` FOR ALL TO service_role USING (true) WITH CHECK (true). Then re-run `SELECT public.attach_acting_audit_triggers('social_wiring');` (migration 214, idempotent) so the new table gets the acting-audit trigger. Satisfy keeper `check_org_picker_ready_policies` and any RLS keepers.
6. `status_pagina` row `('imobiliarias','producao') ON CONFLICT DO NOTHING` (new settings page, mirrors 168's 'testemunhas').
7. Do NOT apply to prod. Migration file + APPLIED.md convention only; applying is the tech-lead's + owner's call.

## Shared item shape — `Imobiliaria`
```json
{
  "id": "uuid",
  "razao_social": "str|null", "nome_fantasia": "str|null", "cnpj": "str|null",
  "creci_pj": "str|null", "creci_pj_regiao": "str|null",
  "responsavel_nome": "str|null", "responsavel_creci": "str|null", "responsavel_creci_regiao": "str|null",
  "telefone": "str|null", "email": "str|null",
  "endereco_cep": "str|null", "endereco_logradouro": "str|null", "endereco_numero": "str|null",
  "endereco_complemento": "str|null", "endereco_bairro": "str|null", "endereco_cidade": "str|null", "endereco_uf": "str|null",
  "faltando": ["razao_social", "cnpj", "responsavel_nome", "responsavel_creci", "endereco_cidade"],
  "created_at": "iso", "updated_at": "iso|null"
}
```
`faltando` = derived, never stored: the subset of the 5 fields the contract REQUIRES (same list as `derivacao._imobiliaria`) that are empty. `[]` = complete.

## Settings registry — prefix `/api/settings` (settings_router, `get_current_user_org`, org from token, never body)
| Method + path | Body | 2xx | Errors |
|---|---|---|---|
| GET `/imobiliarias` | — | 200 `{"items": [Imobiliaria & {"contratos_em_uso": int}], "total": int}` active only (`excluida_em IS NULL`), ordered `created_at` asc, paged past 1 000 | 401 |
| POST `/imobiliarias` | `ImobiliariaCreateBody` | 201 `Imobiliaria` | 401 · 422 field validation · 409 `{"error": {"code": "IMOBILIARIA_CNPJ_DUPLICADO", "message": "Já existe uma imobiliária ativa com este CNPJ."}}` (AppException body, not `detail`) |
| PATCH `/imobiliarias/{id}` | `ImobiliariaPatchBody` (every field optional, only sent fields change) | 200 `Imobiliaria` | 401 · 400 no fields · 404 not found/other org/soft-deleted · 409 same as POST · 422 |
| DELETE `/imobiliarias/{id}` | — | 204 (soft delete: sets `excluida_em`; contracts that chose it KEEP it) | 401 · 404 |

`ImobiliariaCreateBody` (StrictHttpModel — unknown fields are 422): `razao_social` REQUIRED (1..255), `cnpj` REQUIRED (valid mod-11 via `noctusai_lib.integrations.documents.cnpj.is_valid`; stored as typed), every other field optional with the max_lengths `DadosImobiliariaBody` uses today; `creci_pj_regiao`/`responsavel_creci_regiao` max 64; `endereco_uf` max 2. PATCH: same validators on supplied values; `razao_social` if sent must be non-empty; `cnpj` if sent must be valid.

Existing GET/PUT `/api/settings/imobiliaria` (singular) KEEP their paths but now carry ONLY the org-wide fields: `plataforma_assinatura_nome`, `plataforma_assinatura_url`, `posse_multa_diaria`, `prazo_pendencias_padrao_dias`, `suporte_nome`, `suporte_whatsapp`, `suporte_email` (+ `updated_at` on GET). Identity fields leave `DadosImobiliariaBody` ⇒ sending one is now a 422 (Strict). DEPRECATION: identity fields on that endpoint are gone in both directions.

## Per-contract selection — card_hub router, prefix `/api/clientes` (sibling of `contrato_testemunhas_router.py`)
| Method + path | Body | 2xx | Errors |
|---|---|---|---|
| GET `/{cliente_id}/contratos/{contrato_id}/imobiliaria` | — | 200 `ContratoImobiliaria` | 401 · 404 contract not in this cliente/org |
| PUT `/{cliente_id}/contratos/{contrato_id}/imobiliaria` | `{"imobiliaria_id": "uuid" \| null}` | 200 `ContratoImobiliaria` (state after the write) | 401 · 404 contract or company not in org · 400 `{"error": {"code": "IMOBILIARIA_SELECIONADA_INVALIDA", "message": "<nome> foi removida do cadastro e não pode ser escolhida para um novo contrato."}}` when choosing a soft-deleted company the contract does not already hold |

`ContratoImobiliaria`:
```json
{
  "imobiliaria": {"id": "uuid", "razao_social": "str|null", "nome_fantasia": "str|null", "cnpj": "str|null", "excluida": false, "faltando": []} ,
  "origem": "selecionada" | "unica" | null
}
```
Resolution rule (ONE function, used by this GET, the generator's loader and the readiness check — never re-derived):
- `atendimento_contratos.imobiliaria_id` set ⇒ that row (even if soft-deleted: `excluida: true`), `origem: "selecionada"`.
- else exactly ONE active company in the org ⇒ that row, `origem: "unica"` (owner rule: auto-select; read-time, not persisted).
- else ⇒ `{"imobiliaria": null, "origem": null}`.
PUT `null` clears the stored choice (resolution then falls back to the rule above). State after PUT: `atendimento_contratos.imobiliaria_id` = the body value.

## Contract generation (BE)
- `carregador._imobiliaria` builds `Imobiliaria` from the RESOLVED company (identity) + `org_dados_cadastrais` (ops fields). `dados.Imobiliaria` gains `id: Optional[str]`, `creci_pj_regiao`, `responsavel_creci_regiao`. No resolved company ⇒ `id=None`, identity fields None.
- `derivacao._imobiliaria`: `id is None` ⇒ `av.falta("imobiliaria.selecao", "Imobiliária que assina o contrato", "imobiliaria")` (other identity fallas still listed as today). A soft-deleted chosen company is still usable (it was chosen before deletion).
- D4 aviso: for each intermediário with `corretor_id` set (the office's own intermediação) and a `favorecido_id` whose favorecido has a `cpf_cnpj`, if its digits ≠ the chosen company CNPJ digits ⇒ `av.avisa("CORRETAGEM_FAVORECIDO_DIFERENTE_DA_IMOBILIARIA", "O favorecido da corretagem (<nome>) não é a imobiliária que assina o contrato (<razão social>). Confira o PIX.")`. Never blocks.
- `frases.qualificacao_imobiliaria` (D3): `…com inscrição no CRECI sob o nº {creci_pj}` + ` ({creci_pj_regiao})` when set; `…corretor de imóveis CRECI {responsavel_creci}` + ` ({responsavel_creci_regiao})` when set. Unset região ⇒ text exactly as today (the 22 backfilled contracts regenerate byte-identical).
- Aditivo (`contrato_aditivo`): uses the company resolved for the contract it amends (same function).
- `proveniencia/fontes.py`: identity fields now sourced from `org_imobiliarias`.

## FE
- New settings page "Imobiliárias" at `/imobiliarias`, mounted exactly like Testemunhas (App.tsx nav entries + route + `status_pagina` 'imobiliarias'), list + create/edit dialog + soft delete (confirmation shows `contratos_em_uso`, informative only), `faltando` shown as "Incompleta: …". CNPJ validated client-side too (mod-11).
- The Settings page's "Dados da imobiliária" form keeps ONLY the org-wide fields and links to "Imobiliárias" for company data.
- Card: per contract in `ContratosContainer`, next to the witnesses picker, a REQUIRED "Imobiliária que assina" select (`useContratoImobiliaria` GET/PUT). `origem:"unica"` ⇒ show it as chosen with a "única cadastrada" hint; `null` ⇒ visible required-choice state; `excluida` ⇒ flag "removida do cadastro"; non-empty `faltando` ⇒ link to the settings page.
- Loading states per CLAUDE.md §1 (`showSkeleton = isPending && !data`, never `isLoading`).

## Acceptance
- BE: pytest for the 4 settings routes + 2 contract routes (strict `== 401` auth tests), resolution rule (3 branches), migration backfill idempotence, readiness `imobiliaria.selecao` falta, D4 aviso, região printing + unchanged print when região unset.
- FE: vitest for the settings page CRUD, the card select's 3 origem states, the narrowed org-wide form.
- E2E-shape: one test hitting the real routes asserting the shapes above.
