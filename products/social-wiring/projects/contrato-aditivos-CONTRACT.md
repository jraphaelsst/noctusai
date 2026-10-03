# Aditivos de contrato — endpoint contract (BE ↔ FE)

> Owner, 2026-09-24: aditivos are in scope — "model, store and generate them".
> Backend: `products/social-wiring/backend/app/modules/card_hub/contrato_aditivo/` ·
> migration `190_contrato_aditivos.sql`. Status: **BE shipped on `feat/contract-aditivos-be`; FE pending.**

An **aditivo** amends ONE contract (`atendimento_contratos` row) that is **assinado**, or that has an
`assinatura_data` (and is not `cancelado`). Every aditivo re-qualifies all parties, cites the original
by its signing date, carries one or more **structured amendments**, and ends with the
"demais cláusulas inalteradas" ratification. Two print styles, picked per aditivo:

| `estilo` | Title | Sections |
|---|---|---|
| `house` (default) | `ADITIVO AO INSTRUMENTO PARTICULAR DE …` (with `SEGUNDO `/`TERCEIRO ` … prefix from the 2nd one) | `CLÁUSULA PRIMEIRA – DO OBJETO DESTE ADITIVO`, then one `CLÁUSULA` per amendment, then `DAS DEMAIS CLÁUSULAS E CONDIÇÕES CONTRATUAIS` |
| `formal` | `PRIMEIRO TERMO ADITIVO AO INSTRUMENTO PARTICULAR DE …` | numbered sections `1.`, `2.` … with `N.k.` sub-items, then `N. DA RATIFICAÇÃO` |

All routes need auth (strict 401) and live under
`/api/clientes/{cliente_id}/contratos/{contrato_id}/aditivos`. Errors use the platform envelope
`{"error": {"code", "message", "details"}}`. A foreign / deleted contract or aditivo is `404`.

---

## 1. Shapes

### 1.1 Amendment (`Alteracao`) — discriminated on `tipo`

`clausula_alvo` = the NUMBER of the original contract's clause being changed (1 = Primeira, 2 = Segunda…).

```jsonc
// pagamento — the schedule is RESTATED in full via the aditivo's `parcelas` (never free text).
{ "tipo": "pagamento", "clausula_alvo": 2, "novo_valor": "490000.00" /* optional: the price itself changes */ }

// posse — definitive (on a date) or precária (from a date, for a purpose)
{ "tipo": "posse", "clausula_alvo": 5, "data": "2026-12-15", "precaria": false }
{ "tipo": "posse", "clausula_alvo": 5, "data": "2026-10-15", "precaria": true,
  "finalidade": "a medição para os móveis planejados" }          // finalidade REQUIRED when precaria

// comissao — WHEN an installment of the corretagem is paid
{ "tipo": "comissao", "clausula_alvo": 13, "parcela_corretagem": 1,
  "marco": "parcela", "parcela_numero": 2 }                        // marco: parcela | data | financiamento
//   marco=parcela  -> parcela_numero REQUIRED (number in the aditivo's new schedule when it also has a
//                     pagamento amendment, else in the ORIGINAL schedule: "Parcela 02 do contrato original")
//   marco=data     -> data REQUIRED
//   marco=financiamento -> paid on the signing of the financing contract

// outro — free text printed as an extra clause; ALWAYS named in the legal review
{ "tipo": "outro", "clausula_alvo": null /* optional */, "titulo": "Da trava de dados bancários",
  "texto": "Fica vedada qualquer alteração …" }                    // titulo 3..120, texto 10..8000; newlines = paragraphs
```

At most ONE `pagamento` and ONE `posse` per aditivo (422 otherwise). Print order is fixed:
pagamento → posse → comissão → outro.

### 1.2 Parcela (`ParcelaAditivoIn`) — same fields as a negociação parcela, minus permuta

```jsonc
{ "tipo": "sinal" | "intermediaria" | "financiamento" | "fgts" | "saldo" | "direta",
  "valor": "50000.00",                 // > 0
  "vencimento": "2026-11-10" | null,   // a vencimento OR an evento is required (gate)
  "evento": "na assinatura do presente aditivo" | null,
  "forma_pagamento": "PIX" | null,     // required for sinal/intermediaria/direta/saldo (gate)
  "favorecido_id": "<uuid>" | null,    // an atendimento_favorecidos row of THIS deal (404 otherwise);
                                       // required for sinal/intermediaria/direta/saldo (gate)
  "confissao_divida": false }
```
Order = list order (printed `Parcela 01`, `02`, …). `tipo: "permuta"` is rejected (422) — amending a
permuta is an `outro`.

### 1.3 Aditivo (response)

```jsonc
{
  "id": "<uuid>", "contrato_id": "<uuid>",
  "ordinal": 1,                                  // 1 = PRIMEIRO … auto, never reused
  "estilo": "house" | "formal",
  "status": "rascunho" | "em_revisao" | "enviado_assinatura" | "assinado" | "cancelado",
  "status_em": "<iso>" | null, "status_por": {actor} | null,
  "alteracoes": [Alteracao, …],
  "parcelas": [{ "id", "tipo", "valor", "vencimento", "evento", "forma_pagamento",
                 "favorecido_id", "confissao_divida", "ordem" }],
  "assinatura_data": "2026-09-20" | null,        // dates the aditivo (null = today at generation)
  "modalidade_assinatura": "digital" | "fisica",
  "created_at": "<iso>", "updated_at": "<iso>" | null,
  "versao_atual": Versao | null,                 // highest numero
  "versoes": [Versao, …]                         // numero DESC
}
```
`Versao` is **exactly the contract version shape** (`contratos_service.saida_versao`): `id, nome_original,
mime_type, tamanho_bytes, tipo_documento ("aditivo"), enviado_por, created_at, numero, rotulo,
origem ("gerado"), docx_disponivel, modalidade_assinatura, revisao_juridica: {status, campos[],
revisado_por, revisado_em}`.

---

## 2. Routes

| Method | Path (after `…/contratos/{contrato_id}`) | Body | 2xx | Notable errors |
|---|---|---|---|---|
| GET | `/aditivos` | — | 200 `{"aditivos": [Aditivo…]}` (ordinal ASC) | 404 |
| POST | `/aditivos` | `AditivoCreateBody` | 201 `Aditivo` | 409 `CONTRATO_ORIGINAL_NAO_ASSINADO`, 422 |
| PATCH | `/aditivos/{aditivo_id}` | `AditivoPatchBody` | 200 `Aditivo` | 409 `ADITIVO_CONGELADO`, 409 `CONTRATO_AGUARDANDO_REVISAO_JURIDICA`, 409 (no version to send), 422 |
| GET | `/aditivos/{aditivo_id}/geracao` | — | 200 `Geracao` | 404 |
| POST | `/aditivos/{aditivo_id}/gerar` | `{"assinatura_data"?: "YYYY-MM-DD"}` (optional body) | 201 `{"versao": Versao, "avisos": [...]}` | 400 `ADITIVO_INCOMPLETO`, 422 `CONTRATO_LINT`, 422 `CONTRATO_PDF_NAO_GERADO` |
| GET | `/aditivos/{aditivo_id}/versoes` | — | 200 `{"versoes": [Versao…]}` | 404 |
| GET | `/aditivos/{aditivo_id}/versoes/{versao_id}/url?formato=pdf\|docx&intent=view\|download&impressao=bool` | — | 200 `{"url", "expires_at"}` (LGPD access logged) | 409 `CONTRATO_AGUARDANDO_REVISAO_JURIDICA` when `impressao=true` and not reviewed; 404 |
| POST | `/aditivos/{aditivo_id}/versoes/{versao_id}/revisao-juridica` | — | 200 `Aditivo` | 403 (not org admin/owner), 409 (already approved / nothing to review) |

### Bodies

```jsonc
// AditivoCreateBody (strict: unknown keys -> 422)
{ "estilo": "house", "alteracoes": [Alteracao…], "parcelas": [ParcelaAditivoIn…],
  "assinatura_data": null, "modalidade_assinatura": "digital" }

// AditivoPatchBody — every field optional; a PRESENT `alteracoes` / `parcelas` REPLACES the whole list
{ "estilo"?, "alteracoes"?, "parcelas"?, "assinatura_data"?, "modalidade_assinatura"?, "status"? }
```
- Content (`estilo`, `alteracoes`, `parcelas`) is frozen once `status` is `assinado` / `cancelado`
  → 409 `ADITIVO_CONGELADO` (`details.status`).
- `status` → `enviado_assinatura` / `assinado` requires a generated version whose legal review is
  approved (409 `CONTRATO_AGUARDANDO_REVISAO_JURIDICA`, `details.campos` = labels).

### Geracao (readiness — the POST's exact precondition)

```jsonc
{ "aditivo_id", "contrato_id", "ordinal": 1, "estilo": "house",
  "assinatura_data": "2026-09-20",          // the date gerar will use without a body date
  "pronto": false,
  "faltando":  [{ "campo", "rotulo", "onde", "parte_id", "destino": {tela, rota, ancora, alvo, ids}, "sugestoes" }],
  "bloqueios": [{ "codigo", "mensagem" }],
  "avisos":    [{ "codigo", "mensagem" }],
  "revisao_juridica_exigida": true }
```
Same item shapes as the contract's `GET …/geracao`. A falta about the aditivo itself has
`onde: "contrato"` and `destino.alvo: "aditivo-<aditivo_id>"` — **the FE renders that DOM id on the
aditivo's editor** so "Resolver" lands on it. Party/imóvel/office faltas point where the contract's do.

Gate codes (bloqueios) the FE should expect: `ORIGINAL_NAO_ASSINADO`, `ORIGINAL_CANCELADO`,
`ADITIVO_CANCELADO`, `ADITIVO_ANTERIOR_AO_ORIGINAL`, `PARCELAS_SEM_ALTERACAO_DE_PAGAMENTO`,
`SOMA_PARCELAS_DIFERENTE_DO_PRECO`, `VENCIMENTOS_FORA_DE_ORDEM`, `MAIS_DE_UM_SINAL`,
`COMISSAO_SEM_INTERMEDIACAO`, `COMISSAO_PARCELA_INEXISTENTE`, `COMISSAO_SEM_FINANCIAMENTO`,
`OUTRO_COM_MARCACAO`, `MATRICULA_COM_MARCACAO_BRUTA`, `CPF_INVALIDO`, plus the party rules of the
contract gate (`CONJUGE_*`, `REGIME_DIVERGENTE`, `DOCUMENTO_DUPLICADO`, …). Faltando campos include
`contrato.assinatura_data`, `aditivo.alteracoes`, `aditivo.parcelas`, `aditivo.parcela.<id>.<campo>`,
`qualificacao.*`, `imovel.*`, `matricula.atos`, `imobiliaria.testemunha.*`.
Avisos: `OUTRO_EXIGE_REVISAO_JURIDICA`, `CLAUSULA_ALVO_DIVERGENTE` (generated originals only),
`POSSE_DATA_ANTERIOR_AO_ADITIVO`, `NOVO_VALOR_IGUAL_AO_ORIGINAL`, `FAVORECIDO_TERCEIRO`, `PARTE_SEM_EMAIL`.

---

## 3. Lifecycle & legal review

1. Create (`rascunho`) → fill amendments / schedule → `GET geracao` until `pronto`.
2. `POST gerar` → a version (PDF + .docx), **always** `revisao_juridica.status = "aguardando"`;
   `campos` lists `Redação do aditivo (revisão jurídica obrigatória)` + one `Cláusula livre: <TÍTULO>`
   per `outro`.
3. Viewing/downloading the draft is allowed; `impressao=true` and sending/marking signed wait for the
   admin's "Aprovar revisão jurídica".
4. Re-generating creates `numero` 2, 3, … (never reused); each needs its own approval.

Testemunhas are the ORIGINAL contract's selected witnesses (`…/contratos/{id}/testemunhas`); the
signing city is the office's. No new FE field for either.
