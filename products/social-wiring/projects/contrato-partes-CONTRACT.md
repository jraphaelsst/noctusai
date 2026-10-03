# Contract generator: party qualification and non-payment clauses (API delta for FE)

Branch `feat/contract-partes-clausulas`, migration **193** (`193_contrato_partes_clausulas.sql`).
The wording comes from the office's signed contracts (redacted corpus catalog, sections 3 to 7 and 9).
Every change below is additive. Existing request and response shapes keep their keys.

## 1. Party papéis (`POST/PATCH /api/clientes/{cliente_id}/compradores[/{parte_id}]`)

`PAPEIS_POR_LADO` adds two values:

| papel | lado | meaning |
|---|---|---|
| `anuente` | vendedor | A seller's spouse or companion who signs without owning. |
| `representante` | vendedor, comprador | A person who signs for a company party. |

- A company (`cnpj` / `empresa_id`) cannot take `conjuge`, `anuente` or `representante`. The API answers 400.
- An anuente is only worded when the person is the reciprocal spouse or companion of a signing PF vendedor. Set that link on the person record, through `PATCH /api/clientes/{id}` `conjuge_cliente_id`, the same way as for a `conjuge`. Setting the papel does **not** create the link: an anuente is not always a spouse. Any other anuente is the bloqueio `ANUENTE_SEM_REDACAO`.
- `GET .../compradores` items carry `representa_parte_id` (null or the PJ party's `parte_id`).

## 2. NEW `PATCH /api/clientes/{cliente_id}/compradores/{parte_id}/contrato`

PATCH semantics: only the keys you send are written, and `null` clears a field. Returns 401 without a token.

```json
{
  "pj_nire": "35200000001",
  "pj_sede_logradouro": "Rua X", "pj_sede_numero": "7", "pj_sede_complemento": null,
  "pj_sede_bairro": "Centro", "pj_sede_cidade": "Cotia", "pj_sede_uf": "SP", "pj_sede_cep": "06700-000",
  "representa_parte_id": "<uuid of the PJ party>"
}
```

- `pj_*` is only accepted on a company party (otherwise 400). The UF is upper-cased and must be 2 letters. The CEP must have 8 digits and is stored as digits only.
- `representa_parte_id` is only accepted on a person whose papel is `representante`. It must name a company party of the **same** atendimento (otherwise 400).
- The response is the party row (`_out` keys) plus `empresa_id`, `pj_nire` and `pj_sede_*`.
- `GET /api/clientes/{id}/partes` is unchanged. The PJ qualification is read by the generator through `partes_service.partes_pj`, which now returns `nire`, `sede{…}` and `situacao_cadastral`.

## 3. `PATCH /api/clientes/{id}` (person) gains

| field | type | notes |
|---|---|---|
| `identidade_tipo` | `"rg" \| "rne" \| "rnm"` \| null | null reads as `rg`. `rne`/`rnm` print "cédula de identidade RNE <n> <órgão>". |
| `pacto_antenupcial_data` | date | The escritura de pacto antenupcial. Store it on **both** spouses. |
| `pacto_antenupcial_tabelionato` | text | As in the escritura, e.g. "2º Tabelião de Notas de Cotia". Printed after "pelo". |
| `pacto_antenupcial_livro` | text | |
| `pacto_antenupcial_folha` | text | |

The pacto antenupcial reader (`pacto_antenupcial_service`, document type `pacto_antenupcial`) fills the four pacto columns on both matched spouses through the same conflict-safe path as `regime_bens`:

- an empty field is filled, with `_origem='pacto_antenupcial'` and pending confirmation;
- a different value already on file opens a `cliente_campo_conflitos` row and is never overwritten;
- each column has its own provenance quintet (`_origem`, `_documento_id`, `_em`, `_confirmado_por`, `_confirmado_em`);
- a hand edit is stamped `manual`;
- the values appear in the legal review's `campos`.

## 4. `PUT /api/clientes/{id}/negociacao/termos` gains

- `onus_baixa_protocolo_em` (date). Required when `onus_quitacao = 'ja_quitado'`: it is the day the baixa request was filed at the Registro de Imóveis. It is read back in the `termos` aggregate as an ISO date.
- `obrigacoes_vendedor` and `permuta_obrigacoes_entrega` **no longer block**. Each typed line prints verbatim as its own paragraph:
  - seller obligations print as a "Parágrafo" of the ÔNUS clause;
  - permuta delivery prints inside the permuta posse clause.

  Both are recorded as legal-review items.

## 5. Readiness report (`GET .../contratos/{id}/geracao`)

- NEW top-level key `itens_revisao`: `[{codigo, titulo, texto}]`. It lists the wording the final legal review will be pointed at.
- New `switches`: `tem_onus_ja_quitado`, `tem_usufruto`, `tem_anuentes`, `tem_obrigacoes_vendedor`, `tem_permuta_obrigacoes`. With `ja_quitado`, `tem_saldo_devedor` is now false, because nothing is left to pay.

New `faltando.campo` values. Each one carries a `destino`, the same way the existing ones do:

| campo | onde |
|---|---|
| `partes.pj.{razao_social,cnpj,nire,sede_logradouro,sede_numero,sede_bairro,sede_cidade,sede_uf,sede_cep}` | partes (`parte_id` = PJ party) |
| `partes.pj.representante` | partes (`parte_id` = PJ party) |
| `qualificacao.pacto_antenupcial` / `qualificacao.pacto_antenupcial_{data,tabelionato,livro,folha}` | partes |
| `imovel.numero_registro_imoveis` | imovel. Also raised when the stored value has no readable city, e.g. a bare CNS or "… da Capital". |
| `matricula.permuta.<id>.cartorio` | imovel. Same rule, for the permuta imóvel. |
| `negociacao.onus_baixa_protocolo_em` | negociacao |
| `imovel.certidao.{cnd_iptu,cnd_condominio}.resultado` | imovel |

REMOVED: `partes.pj_sem_qualificacao`.

New `bloqueios`:

- `ANUENTE_SEM_REDACAO`
- `PJ_MAIS_DE_UM_REPRESENTANTE`, `REPRESENTANTE_FORA_DO_LADO`, `REPRESENTANTE_SEM_EMPRESA`, `PJ_PAPEL_SEM_REDACAO`, `CNPJ_INVALIDO`
- `PACTO_ANTENUPCIAL_DIVERGENTE`
- `IDENTIDADE_TIPO_DESCONHECIDO`, `IDENTIDADE_ESTRANGEIRO_BRASILEIRO`
- `ONUS_USUFRUTO_SEM_FINANCIAMENTO`, `ONUS_BAIXA_PROTOCOLO_POSTERIOR`, `ONUS_JA_QUITADO_MAIS_DE_UM_ATO`
- `PERMUTA_OBRIGACOES_SEM_PERMUTA`, `TEXTO_LIVRE_COM_MARCACAO`
- `CERTIDAO_IMOVEL_RESULTADO_DESCONHECIDO`

REMOVED bloqueios: `ONUS_QUITACAO_SEM_REDACAO`, `OBRIGACOES_VENDEDOR_SEM_REDACAO`, `PERMUTA_OBRIGACOES_SEM_REDACAO`.

New `avisos`:

- `PJ_REDACAO_A_CONFIRMAR`: "redação de PJ derivada de um único contrato assinado — confirme na revisão jurídica".
- `ESTRANGEIRO_COM_RG`.
- `OBRIGACOES_VENDEDOR_TEXTO_LIVRE`, `PERMUTA_OBRIGACOES_TEXTO_LIVRE`.

## 6. Contract versions

`versao.revisao_juridica` gains `itens: [{codigo, titulo, texto}]`. Rows from before migration 193 return `[]`. Show these items to the legal reviewer next to `campos`. There is nothing to confirm per item: the approval itself covers them.

## 7. Rendering changes worth knowing

- The registry always prints "Cartório de Registro de Imóveis de <Cidade>", with "<N>º" kept when the heading has an ordinal. This changes the V1 to V6 renders in one phrase only; the test hashes are re-pinned.
- The imóvel IPTU and condomínio certidão lines print their real resultado ("Certidão Positiva de …"). Before this change they always said "Negativa".
