# Contrato — payment shapes (API delta for the FE)

**Branch:** `feat/contract-pagamentos` · **Migration:** `192_parcela_divisao_fgts_quitacao_boleto.sql` · **Date:** 2026-10-03

The contract generator now prints the payment shapes the office's signed contracts use. This file lists only what changed in the negociação API (`/api/clientes/{cliente_id}/negociacao/...`) and in the generator's readiness codes. Everything else is unchanged.

## 1. Parcela: new fields

### Request: `POST /negociacao/parcelas` and `PATCH /negociacao/parcelas/{parcela_id}`

| Field | Type | Rules |
|---|---|---|
| `valor_fgts` | decimal string, `> 0`, optional | Only on `tipo='financiamento'`. Must be **less than** `valor`, because the financed part is `valor - valor_fgts`. PATCH: an explicit `null` clears it. |
| `favorecidos_divisao` | `Array<{favorecido_id: uuid, valor?: decimal > 0, percentual?: decimal in (0, 100]}>`, max 20 | Only on `sinal`, `intermediaria`, `direta` or `saldo`. Needs **at least 2** entries. Each entry has `valor` **or** `percentual`, never both (422). Both may be blank while drafting. Entries cannot mix the two kinds. The same favorecido cannot appear twice. Every favorecido must belong to this atendimento (404 otherwise). POST default is `[]`. PATCH: if the field is sent it **replaces** the split, and `[]` removes it. If it is absent, the split is left alone. |

`favorecido_id` and `favorecidos_divisao` are **mutually exclusive**:
- A request where both end up set returns 400 (`"a parcela já tem um favorecido único — remova-o …"`).
- To switch from a single favorecido to a split, send in one PATCH: `{"favorecido_id": null, "favorecidos_divisao": [...]}`.
- To switch back, send in one PATCH: `{"favorecidos_divisao": [], "favorecido_id": "<id>"}`.
- PATCHing `favorecido_id` on a parcela that has a split, without sending `favorecidos_divisao`, returns 400.
- Changing `tipo` to one that is not paid into an account while a split exists returns 400. Remove the split first.
- Changing `tipo` away from `financiamento` while `valor_fgts` is set returns 400. Clear it in the same PATCH.

Sums are **not** checked on save. Draft states are fine. The generator gate checks them (see §3).

### Response: every parcela in `GET /negociacao/estruturada` (and every write's aggregate)

```jsonc
{
  "...": "existing fields unchanged",
  "valor_fgts": "100000.00" | null,
  "favorecidos_divisao": [
    { "id": "uuid", "favorecido_id": "uuid" | null, "valor": "30000.00" | null, "percentual": "50" | null, "ordem": 0 }
  ]
}
```
`favorecido_id` inside a share is `null` only when that favorecido was deleted after the split was made (FK `ON DELETE SET NULL`). The generator reports it as missing.

## 2. Termos: `onus_quitacao` gains `vendedores_boleto`

`PUT /negociacao/termos`: `onus_quitacao` now also accepts **`"vendedores_boleto"`**, meaning the seller pays the lien off by bank slip. It uses the existing `onus_prazo_dias` field (required for this value, like `compradores_prazo`).

## 3. Shapes the generator now accepts (FE can offer them)

| Shape | How to enter it | Printed as |
|---|---|---|
| More than one **sinal** | Several `tipo='sinal'` parcelas, **consecutive** in `ordem` | ONE "Parcela 01: Sinal e princípio de pagamento: {Σ}, a serem pagos da seguinte forma: {A} …, e {B} …". The multa rescisória is Σ sinais. |
| More than one **permuta** parcela | Several `tipo='permuta'` parcelas, each with its own `permuta_ativo_ids` | One line per parcela with its own imóveis. The escritura/posse wording goes plural. |
| One permuta parcela, **two imóveis** | One parcela with two `permuta_ativo_ids` (already supported) | "por permuta dos imóveis … E …" |
| **FGTS** split known | `valor_fgts` on the financiamento parcela, **or** a separate `tipo='fgts'` parcela with no vencimento/evento of its own | "{TOTAL}, onde será utilizado {FGTS}, por meio do uso das contas vinculadas ao FGTS e {FIN} por meio de recursos de financiamento imobiliário e/ou moeda corrente nacional, …". Both data shapes print the same paragraph, and a separate fgts parcela does **not** get its own number. |
| FGTS without a split | `financiamento.fgts = true`, no `valor_fgts` | "…, por meio do uso das contas vinculadas ao FGTS e de recursos de financiamento imobiliário e/ou moeda corrente nacional, …" |
| One parcela, **several payees** | `favorecidos_divisao` | The head line ends "… a ser realizada da seguinte forma:", then sub-items "01.1) {VALOR}[, correspondentes a {PCT}% (…) da parcela,] em favor de …". A later parcela with the same accounts and proportions prints "nas mesmas contas correntes e proporções informadas na Parcela 01". |
| Lien paid by **boleto** | `onus_quitacao='vendedores_boleto'` + `onus_prazo_dias` | "… o qual deverá ser quitado através de boleto bancário emitido pela instituição financeira responsável, onde O VENDEDOR terá o prazo de até N dias corridos …" |

FE note: `frontend/src/types/negociacaoEstruturada.ts` still documents `fgts` as blocked (`PARCELA_FGTS_SEPARADA`) and leaves it out of `PARCELA_TIPOS_CRIAVEIS`. That is no longer true, so offering it again is the FE's call. The comment is now stale.

## 4. Readiness codes (`/contrato/.../geracao` bloqueios / faltando)

**Removed from the contract gate (now generated instead):** `MAIS_DE_UM_SINAL`, `MAIS_DE_UMA_PARCELA_PERMUTA`, `PARCELA_FGTS_SEPARADA`. `MAIS_DE_UM_SINAL` (and the fgts parcela's own vencimento/evento falta) still come out of the **aditivo**'s restated-schedule evaluation, because the aditivo prints one line per stored parcela and does not fold tranches yet (`derivacao._negociacao(..., agrupar_parcelas=False)`, the default).

**New bloqueios:**
- Sinais: `SINAIS_NAO_CONSECUTIVOS`, `SINAL_EM_PARCELAS_COM_DIVISAO`, `CORRETAGEM_SINAL_PARCIAL` (mark corretagem on every sinal tranche or on none), `POSSE_MARCO_PARTE_DO_SINAL` (the posse marco must be the last tranche).
- Split: `FAVORECIDO_E_DIVISAO`, `DIVISAO_COM_UM_FAVORECIDO`, `DIVISAO_EM_PARCELA_SEM_FAVORECIDO`, `DIVISAO_FAVORECIDO_REPETIDO`, `DIVISAO_VALOR_E_PERCENTUAL`, `DIVISAO_MISTA`, `DIVISAO_SOMA_DIVERGE`, `DIVISAO_PERCENTUAL_DIVERGE`, `DIVISAO_PERCENTUAL_INEXATO` (the percentages do not split the value into exact cents, so enter values instead).
- FGTS: `MAIS_DE_UMA_PARCELA_FGTS`, `PARCELA_FGTS_SEM_FINANCIAMENTO`, `FGTS_EM_DUPLICIDADE`, `PARCELA_FGTS_MOMENTO_DIVERGENTE`, `VALOR_FGTS_FORA_DO_FINANCIAMENTO`, `FGTS_MAIOR_QUE_PARCELA`, `FGTS_NAO_MARCADO_NO_FINANCIAMENTO`.
- Permuta: `PERMUTA_IMOVEL_EM_DUAS_PARCELAS`, `PERMUTA_IMOVEL_NAO_CARREGADO`, `PERMUTA_IMOVEL_SEM_PARCELA`.

**New faltando campos:**
- `negociacao.parcela.{id}.divisao.{n}.favorecido`
- `negociacao.parcela.{id}.divisao.{n}.valor`
- `negociacao.parcela.{id}.permuta_imoveis` (only when the deal has 2+ permuta parcelas; one parcela keeps `negociacao.permuta_imoveis`)
- `negociacao.onus_prazo_dias` for `vendedores_boleto`.

**Still refused:** `CONFISSAO_EM_PARCELA_NAO_DIRETA`. None of the catalogued signed contracts has a confissão de dívida on a non-direta parcela.
