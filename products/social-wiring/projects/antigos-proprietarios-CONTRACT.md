# Antigos proprietários — API contract (backend → frontend)

Owner decisions 2026-10-05 (33 signed contracts). Branch `feat/antigos-proprietarios-be`; migration `203`.
All paths are under `/api/clientes/{cliente_id}`; raw-dict responses (card convention, no `{"data":…}` envelope);
`atendimento_id` is always optional (resolved like every other card route; ambiguous ⇒ 409 on writes).

## 0. Where it lives in the UI

The card's **Certidões** tab (`CertidoesPartesTab`) gets **subtabs**, one per `grupo`:
`comprador` · `vendedor` (sellers + the sellers' companies) · `antigo_proprietario` (previous owners + their companies).
The previous owners are **never** in `GET …/partes` nor `GET …/compradores` (they sign nothing, are never qualified).
The antigos subtab header carries: the "required (last transfer < 5 years)" notice, **Dispensar / Reativar**, and
**Adicionar / Remover** (manual). Rows get the same per-cell emission / upload / re-read actions as any party.

## 1. Rows — extend the existing payload (no parallel list)

`GET /certidoes/partes` — each entry of `partes[]` gains **`grupo`**: `"comprador" | "vendedor" | "antigo_proprietario"`.
Split subtabs on `grupo`, never on `papel`. Order is stable: compradores, vendedores, the sellers' derived companies
(`EMP n`, grupo `vendedor`), previous owners (`ANT n`, grupo `antigo_proprietario`, `papel="antigo_proprietario"`),
the previous owners' derived companies (`ANT EMP n`, grupo `antigo_proprietario`, `parte_id=null`, `papel=""`).
Everything else (cells, totals, emissão `POST …/certidoes/partes/{kind}/{alvo_id}/emissao`, reemitir, células, reler)
is unchanged and works on antigos rows.

## 2. Header state

`GET /certidoes/antigos-proprietarios[?atendimento_id=]` → 200
```json
{
  "atendimento_id": "uuid",
  "exigido": true,                       // true | false | null (unknown)
  "motivo": "transferencia_menos_de_5_anos",
  // | transferencia_5_anos_ou_mais | sem_transferencia_registrada | ultima_transferencia_desconhecida | sem_imovel
  "janela_anos": 5,
  "ultima_transferencia": {"ato_id": "…|null", "ato_ref": "…|null", "natureza": "compra_e_venda", "data_registro": "2024-03-01|null", "detalhes_origem": "…"} ,
  "origem_dados": "titulo_confirmado | extracao | manual | null",
  "transmitentes": [{"nome": "…", "documento_mascarado": "***.982.247-**", "tipo_pessoa": "PF|PJ", "ja_no_card": true}],
  "dispensado": null | {"em": "iso", "por": {"id": "uuid", "nome": "…|null"}, "motivo": "…"},
  "sincronizacao_pendente": 0            // transmitentes the matrícula names that are not yet on the card (> 0 ⇒ call §3)
}
```
`documento_mascarado` is the matrícula reading, masked; a row already on the card carries the full `documento` in §1.

## 3. Sync from the matrícula (idempotent) — call on opening the Certidões tab and after any matrícula change

`POST /certidoes/antigos-proprietarios/sincronizar` body `{ "atendimento_id"?: uuid }` → 200
```json
{"atendimento_id": "uuid",
 "criados":  [{"parte_id": "uuid", "nome": "…", "tipo_pessoa": "PF|PJ"}],
 "ja_no_card": [{"nome": "…", "documento_mascarado": "…"}],
 "emissoes": [{"parte_id": "uuid", "status": "solicitada|nao_iniciada", "codigo": null|"DOCUMENTO_AUSENTE"|"CREDENCIAIS_AUSENTES", "consulta_id": "uuid|null"}],
 "ignorado": null | "dispensado" | "sem_imovel" | "matricula_nao_nomeia_antigos" | "transferencia_5_anos_ou_mais"}
```
Creates (only what is missing, matched by CPF/CNPJ) a party row `papel=antigo_proprietario, lado=vendedor, origem=matricula`
for each seller of the last transfer, **only** when the deal is not dispensed, the matrícula names them and the transfer is
< 5 years old; then starts the automated certidões for each new party through the same path as the emission button
(`status="solicitada"`; processing runs in the background — poll `GET /certidoes/partes`). `nao_iniciada` is reported, not
hidden: show `codigo` and keep the row's own emission button. A manual date override names nobody ⇒ `ignorado`.
After the call, refetch `GET /certidoes/partes`.

## 4. Manual add / remove (when the matrícula does not name them)

`POST /certidoes/antigos-proprietarios` → **201** body (StrictHttpModel, `extra=forbid`): person `{nome, cpf}` or company `{cnpj, razao_social?}`
(+ optional `atendimento_id`) → `{"parte": <ParteItem + origem "manual">, "emissao": {…as §3}}`.
Errors: 422 (neither/both of nome|cnpj, invalid CPF/CNPJ) · 409 already a party of this deal.

`DELETE /certidoes/antigos-proprietarios/{parte_id}` → 204. 422 if the party is not a previous owner (never detaches a seller);
404 if it does not belong to this card. Removing a `origem=matricula` row is re-created by the next §3 unless dispensed.

## 5. Dispense / undispense — **admin only** (trusted `noctus_users` row, same gate as `processo-legado`)

`PUT /certidoes/antigos-proprietarios/dispensa` body `{"motivo": "3..500 chars", "atendimento_id"?}` → 200 = §2 state (with `dispensado` set).
`DELETE /certidoes/antigos-proprietarios/dispensa[?atendimento_id=]` → 200 = §2 state (`dispensado: null`).
Errors: 401 unauthenticated · **403** non-admin · 422 motivo missing/short/long. Show Dispensar/Reativar only to admins (the 403 is the gate).
Dispensing is per deal; `dispensado_por/em/motivo` are stamped server-side (never accepted from the body).

## 6. Readiness (`GET …/contratos/{id}/geracao`) — what the UI must render

Faltas about previous owners carry `onde = "antigos_proprietarios"` and
`destino = {"tela": "card_certidoes", "rota": "/clientes", "ancora": "certidoes", "alvo": "certidoes-subtab-antigo_proprietario", "ids": {cliente_id, contrato_id, parte_id?}}`.
The UI opens the card's Certidões tab and selects the subtab whose key is the `grupo` in the `alvo` suffix (`antigo_proprietario`);
`ids.parte_id` (when present) is the row to scroll to. Campos:

| campo | meaning |
|---|---|
| `partes.antigo_proprietario` | required (< 5y) and no previous owner on the card — add one, sync, or dispense |
| `qualificacao.nome_oficial` / `qualificacao.genero` | a previous owner's name / gender (the instrument prints them) |
| `certidao.<tipo>` (+ `.numero`, `.emitida_em`, `.consulta_tipo_documento`) | missing certidão of a previous owner OR of their company |
| `partes.pj.razao_social` / `partes.pj.cnpj` | a company previous owner's data |

Avisos (`avisos[].codigo`): `ANTIGO_PROPRIETARIO_DISPENSADO_NO_NEGOCIO` (new — an admin dispensed it for this deal; it is **not** a falta),
`ANTIGO_PROPRIETARIO_DISPENSADO` (transfer ≥ 5 years), `ANTIGO_PROPRIETARIO_PROCESSO_LEGADO`, `PJ_ANTIGO_PROPRIETARIO_A_CONFIRMAR`.
Companies of previous owners follow the sellers' rule (ATIVA/INAPTA any stake; baixada < 5 years; older baixadas omitted); a company's
`empresa.<id>.cartao_cnpj` falta keeps its own destino (`card_empresas`).

## 7. Anuente (item B)

An anuente spouse (signs, owns nothing) is **never** certified nor are their companies; readiness never requires them
(no `certidao.*`, no `empresa.*`, no estado-civil certidão falta for an anuente). The rows are not in the certidões matrix as
requiring anything — nothing to render beyond what already exists.

## 8. Not in this contract (frontend decisions / follow-ups)

- Auto-sync is **UI-triggered** (§3) — no server-side hook on matrícula confirmation yet.
- Emission for the previous owners' *companies* is not auto-started (their CNPJs surface only after a Crednet read); use the row's emission button.
