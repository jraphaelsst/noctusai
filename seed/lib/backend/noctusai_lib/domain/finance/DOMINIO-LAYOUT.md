# Domínio "leiaute com separador" — what the finance export implements

Code: `dominio.py`. Endpoint: `GET /api/finance/exports/dominio.txt?from=&to=&cnpj=[&history_code=]`.

## Sources read (2026-10-14)

* Layout page — Thomson Reuters Central de Soluções, "Leiaute: Domínio Sistemas com Separador" (solução 672):
  https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=672 (record tables for 0000, 0200, 0220, 0240, 6000, 6100, 6110).
* **Official sample file** `exemplo_arquivo__lancamento_lote.txt` (attached to that page, `arquivos_exemplos.zip`), 112 bytes, CRLF, ASCII:

```
|0000|33333333000191|
|6000|X||||
|6100|10/09/2015|55|5|5571,24|1|DESCRICAO DO HISTORICO CONTABIL|GERENTE|||
```

* Omie's help page (Painel do Contador → Domínio → "Leiaute com Separador") — confirms the record families (0000, 0200, 0220,
  0240, 6000 "Lançamentos em Lote", 5100/5200/5300) and that 6000 carries the batch postings.

## What we emit

```
|0000|<CNPJ/CPF, digits only>|
|6000|X||||                      one debit : one credit  (repeated before each 6100)
|6100|dd/mm/aaaa|<debit>|<credit>|<valor 1234,56>|<histórico code>|<histórico text>|<usuário>|<filial>|<SCP>|
```

One `6000` (type `X`, the "um débito para um crédito" form) per `6100` child — the sample's exact shape, repeated per posting. Lines end CRLF, as the sample. Debit/credit are the
**reduced account codes** (`fin_categories.accounting_code`, `fin_accounts.accounting_code`) — free text the contador chose.

## Verified (layout page + sample agree)

| item | evidence |
|---|---|
| pipe `|` separator, each line starts and ends with `|` | sample |
| record ids `0000` / `6000` / `6100` and their field ORDER | layout tables (6000: tipo, lançamento padrão, localizador, RTT FCONT; 6100: data, débito, crédito, valor, histórico código, histórico texto, usuário, filial, SCP) + sample |
| `0000` carries the company inscription (CNPJ/CPF/CEI/CAEPF, digits only) | layout: "Informar apenas números" |
| date `dd/mm/aaaa` | layout ("Data … dd/mm/aaaa") + sample |
| value uses a comma decimal, no thousands separator (`5571,24`) | sample |
| `6000` type `X` = um débito para um crédito; `D`, `C`, `V` are the other batch forms | layout |
| usuário empty = the importing user; filial empty = matriz | layout comments + sample |

## UNVERIFIED — do not rely on these without a test import into the contador's Domínio

1. **Encoding.** The sample is ASCII, the layout page states none. We emit ASCII only (accents folded, `|`/line breaks removed). Domínio may well accept cp1252/ANSI accents; unverified.
2. **Histórico.** We leave the code empty (`history_code` is an optional query parameter) and put the full text in the description. The layout says the code is *"informar código conforme registro 0220"* and *"if the code is given, fill only the complement"* — it does **not** say an empty code is accepted. The sample has code `1`. If the contador's base requires a code, pass `history_code`.
3. **Max length** of the histórico text — not stated; capped at 250 characters by us.
4. **Types of the 6100 cells** (date/decimal/numeric) are blank in the published table (the page renders them as images); the format above is inferred from the sample and the general "Tipo de dados" paragraph. That paragraph says a *Numérico* field is an integer ("100,99 → 10099") yet the sample writes `5571,24` — we follow the sample.
5. **Is `0000` mandatory** for a lançamentos-only file? The sample has it; we always write it. The company must already exist in Domínio under that inscription.
6. **Account codes are the "código reduzido"** of Domínio's chart (`0200` field 2). The software never creates or syncs the chart: the contador types the reduced code into the category/account.
7. **Cash-movement scope.** No accrual (receivable/payable) postings, invoices (1000/2000/3000), inventory (0100) or payment-of-invoice (5100/5200/5300) records. Those are the contador's / the fiscal organ's.
8. Whether a `0000` record may appear once with many `6000`/`6100` pairs after it (we do) — the layout does not forbid it; the sample has a single pair.

The software prepares and exports; importing and signing belong to a licensed contador (CRC).
