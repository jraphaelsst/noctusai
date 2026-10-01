# atendimento-partes-imoveis — certidões per party, imóvel↔atendimento link, interesses, roteiro rework

> Branch `feat/sw-certidoes-partes-imovel-link` (off `origin/dev`). Owner ask 2026-10-01.
> Contract: `atendimento-partes-imoveis-CONTRACT.md` (authored in Wave A, verbatim in every Wave B brief).
> Delivery: everything together (owner decision) — integrate on this branch, gates on the merged tip, then `dev`.

## 1 · Why

1. **Certidões arrive with old emission dates.** Root cause (verified against prod data 2026-10-01):
   `certidoes/registry.py:225` sends `preferencia_emissao="2via"` to InfoSimples Receita/PGFN, so a
   person holding a still-valid CND gets the OLD certidão back (e.g. NEON PARK requested 01/10 →
   `emissao_data 23/06/2026`). Last 60d automatic: `cnd_federal` 9/23 old; every other tipo 0 old.
   The contract gate (`derivacao.py:1447`, 30d) blocks them — correct, but Marina has to re-emit by hand.
2. Certidão analysis already extracts data but feeds only the certidão row — never the party profile.
3. The card's certidões matriz is person-scoped (`VEND n` only, no compradores, newest-`created_at` wins,
   doesn't follow the person across deals, no PJ party).
4. Imóvel↔atendimento is two free-text códigos; Meta leads' `answers.REF` (100% of 1,895 rows carry it,
   e.g. `ONE9441`) is never read; manual leads don't require an imóvel.
5. No comprador interest list, no vendedor↔imóvel ownership, no "who was interested in this imóvel",
   roteiro has no date / no photo in PDF / no signature+proposal fields.

## 2 · Owner decisions (2026-10-01)

- D1 Meta leads carry the código in `answers.REF` → on arrival: atendimento + funnel card linking lead AND imóvel.
- D2 Manual lead/cliente creation: imóvel código REQUIRED (registry-backed picker). Inbound without a
  resolvable código → accepted + flagged `imovel_pendente` (never drop a real lead).
- D3 Dedicated pages (not modals): `/clientes/:id` (lead/comprador) and `/vendedores/:id`.
  Roles overlap (a comprador can be a vendedor and vice versa) → ONE person-page component, two routes,
  section order by role. Comprador page bottom: "Imóveis que possui" (ownership we have registered).
  Vendedor page bottom: "Interesses" (intro to permuta).
- D4 The 9 stale Receita certidões: Marina re-emits via the new tab's stale warning (no auto re-emit).
- D5 Imóvel page: "Interessados" — every lead/cliente ever interested (full lead history backfilled),
  with contact + last interaction, so old leads can be reached. Same page: "Imóveis similares" by the
  PROPERTY profile (tipo, região/bairro, faixa de preço, dormitórios, área) so an interested lead can be
  offered alternatives — reuse the permutas matching engine, do not build a second matcher.
- D6 `/certidoes` page stays untouched and working (Marina uses it). Retire only after the tab is 100%.

## 3 · Design

### 3.1 Certidões (fix + feed)
- Receita: request a NEW emission (InfoSimples PGFN param value verified against their docs, not guessed;
  update `test_certidoes_service.py:294`). Parser reads `emissao_data` (the field Receita actually returns)
  in `_parse_resultado_padrao` alongside `data_emissao`/`data_consulta`.
- Manual PDF date: prefer the emission line ("emitida em", "data de emissão", "expedida") over the
  first-date-on-any-page rule.
- Serasa via Crednet: do not fill a NEW consulta from a Crednet older than `politica.certidao_max_dias`.
- Re-upload onto a locked (confirmed) resultado must clear numero/emitida_em/validade_ate and re-extract
  (a new file = new evidence; the lock protects a human edit of THAT file only).
- Edit dialog must not default an empty `emitida_em` to today.
- **Feed to party**: after `_derive_estrutura`, write party data through the existing quinteto provenance
  (`_origem/_documento_id/_em/_confirmado_*`) + `campo_conflitos` (fill-empty, conflict-on-disagree):
  PF → `clientes.nome_oficial`, `cpf`, `data_nascimento` (when present); PJ → `empresas.razao_social`,
  `situacao_cadastral`, `data_situacao_cadastral`. Register the certidão source in `proveniencia/fontes.FONTES`
  and `validacao_extracao.REGISTRO`; include party certidões in `linhagem.py`.
- Certidões become **party-scoped** (cliente_id | empresa_id) and follow the party across deals;
  `atendimento_parte_id` stays as provenance. Cell selection = newest `emitida_em` (tie → newest created_at).

### 3.2 Parties
- `atendimento_partes` gains `empresa_id` (cliente_id XOR empresa_id). PJ can be comprador or vendedor.
- Titular (`atendimentos.cliente_id`) is COMP 1 in every party listing.
- Labels computed `COMP n` / `VEND n` by lado+ordem (PF and PJ share the numbering per lado).
- Registration lookup: typing a CPF/CNPJ returns the existing cliente/empresa + their other atendimentos +
  latest certidão per tipo with age. Older than `certidao_max_dias` → warning + "re-emitir e re-analisar".

### 3.3 Imóvel ↔ atendimento
- New junction `atendimento_imoveis(atendimento_id, codigo → imovel_registry, origem lead|manual|campanha|negociacao, principal bool)`.
  `atendimento_negociacao.imovel_codigo` remains "the one under negotiation" and must be ∈ junction (service-enforced).
- Ingest: Meta (`answers.REF` → new `meta_ads_leads.codigo_imovel` + `_norm`, backfilled), OLX/imovelweb
  (already parse), manual (required) → `registrar_imovel` + link on card spawn. Backfill from
  `leads.codigo_imovel_norm` and `atendimento_negociacao.imovel_codigo`.
- Invariant: atendimento has ≥1 cliente and ≥1 imóvel; legacy rows without imóvel surface `imovel_pendente`.

### 3.4 Interesses / propriedade / interessados / similares
- `cliente_imovel_interesses(cliente_id, codigo, origem lead|manual|campanha|roteiro|permuta, lead_id?, created_by, created_at, deleted_at)`
  — backfilled from every historical lead with a resolvable código (the "Interessados" source).
- `imovel_proprietarios(codigo, cliente_id XOR empresa_id, origem manual|matricula|atendimento, ...)` —
  backfill from vendedor partes × negociação imóvel and matrícula owners matched by CPF.
- Imóvel page: "Interessados" + "Imóveis similares" (property-profile similarity via the permutas matching engine);
  from a similar imóvel the operator can add it to an interessado's interest list in one click.

### 3.5 Roteiro
- `roteiros.data_visita DATE` (required on create, no time).
- Flow (shared `ImovelInteressesList`, mounted on the person page AND the card's Roteiros tab):
  checkbox rows → "Gerar roteiro" → ordering dialog (dnd-kit, already installed) + date → "Confirmar ordem"
  → create roteiro with ordered códigos → PDF.
- "Adicionar interesse" popup: live typeahead (`/api/imoveis/busca`) narrowing as the código is typed;
  each row = first photo, código, endereço + complemento, valor (R$); click adds.
- PDF (move to `noctusai_lib...documents.html_pdf.render_html_pdf`, the owner-mandated PDF path; photo
  embedded as `data:` URI): one imóvel per page — technical data, first photo, proprietário (now known via
  `imovel_proprietarios`), "Visita realizada" + assinatura, "Gerou proposta? ☐ Sim ☐ Não", proposta (texto),
  ☐ Permuta ☐ Financiamento ☐ FGTS.

## 4 · Waves

- **Wave A — foundation** (1 backend engineer): every migration (179+) + the CONTRACT doc (existing shapes
  EXTRACTED field-by-field, new ones authored with the 4 stateful legs). Pushed before Wave B.
- **Wave B — parallel, file-disjoint** (build to the contract):
  - BE-certidoes · BE-partes (partes PJ + lookup) · BE-imoveis (junction, ingest, interesses, proprietários,
    interessados, similares, person page endpoint) · BE-roteiro (date, ordered create, PDF)
  - FE-certidoes-tab · FE-pessoa-interesses-roteiro (pages, shared list, add popup, ordering, PDF trigger,
    imóvel Interessados) · FE-leads-partes (required código picker, linked imóveis in card, PJ party +
    CPF/CNPJ lookup + stale warning)
- **Wave C — integrate**: merged-tip gates, ONE E2E contract check per new endpoint, wiring audit, then `dev`.

## 11 · Change log
- 2026-10-01 — scaffolded from three read-only audits + prod read-only queries; owner decisions D1–D6.
