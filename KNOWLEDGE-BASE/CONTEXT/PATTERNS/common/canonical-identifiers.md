# Canonical identifiers — the punctuated form is canonical (CPF, CNPJ, RG, ...)

> **Owner rule, 2026-10-01:** the canonical reference for all document numbers, ids, protocols
> and so on is the **punctuated** form. A value that claims to be a document number but has no
> punctuation is **checked against the canonical punctuated form** of its type, to measure
> whether it fits. Zero extra LLM/API cost — deterministic code, usable over already-stored
> extractions.
>
> Sibling of the phone canon (E.164 — `primitives/phone.py`, `@noctusai/lib/phone`), same
> three-runtime contract, same lessons.

## 1 · The contract (one table, three runtimes)

| Runtime | Where |
|---|---|
| Python | `noctusai_lib.primitives.identificador` |
| TypeScript | `@noctusai/lib/identificador` (`lerIdentificador`, `canonicoIdentificador`, `formatIdentificador` = THE display seam, `equivalentesIdentificador`, `chaveBuscaIdentificador`, `detectarTipoIdentificador`, `extrairCns`) |
| plpgsql | `seed/lib/sql/identificador.sql` (`canonizar_identificador`, `identificador_chave_busca`) — a product adopts it by copying into its next migration |
| **Case table** | `seed/lib/shared/identificador.cases.json` — asserted by `tests/test_identificador.py`, `identificador.test.ts`, and the SQL parity block (generated between `BEGIN-CASES`/`END-CASES`; the Python test fails when stale). Add a case to all runtimes or to none. |

`ler(tipo, valor) -> Leitura(canonico, cabe, dv_ok, dv_completado, motivo, tipo_detectado)`;
`equivalentes(tipo, a, b) -> True | False | None` (None = undecidable);
`detectar_tipo(valor) -> [tipo]`; `chave_busca`; `formatar`; `extrair_cns(texto)`.

## 2 · Types

`cpf` `000.000.000-00` · `cin` (= CPF) · `cnpj` `00.000.000/0000-00` (numeric + alphanumeric) ·
`rg` SP `00.000.000-D` (mod-11, `X` allowed) · `cnh` · `titulo_eleitor` `0000 0000 0000` ·
`nis_pis` `000.00000.00-0` · `cep` `00000-000` · `cns_cartorio` `00000-D` ·
`matricula_imovel` (integer, thousand dots `79.826`) · `inscricao_municipal` (per-município
profile; Cotia `00000.00.00.0000.00.000[-D]`) · `orgao_expedidor` (`SSP/SP`, `IIRGD` ≡
`SSP/SP`) · `certidao_controle_receita` `XXXX.XXXX.XXXX.XXXX` · `protocolo_cenprot` (digit run).
Extend by adding a reader to the registry in all runtimes, with evidence.

## 3 · Rules that cost something to learn

- **Never invents data.** The ONE completion allowed is a SP RG missing its check digit — the DV
  is a pure function of the other eight digits (CNH prints `30128742`; the matrícula has
  `30.128.742-9`). A 7-digit RG, an old non-SP shape, a 7-digit CEP (lost a leading zero) are
  `cabe=False` and stay visible.
- **The DV decides between OCR readings** (`15.668.564-3` fails, `16.669.554-3` passes).
- **A valid CPF in an RG field is detected, not stored** (`tipo_detectado='cpf'`). 11-digit runs are
  ambiguous by chance (~1/11 pass the NIS DV): `detectar_tipo` returns candidates, priority
  cpf > cnpj > cnh > nis_pis.
- **One DV implementation.** `integrations/documents/{cpf,cnpj,rg}.py` delegate to the registry;
  a guard test fails if a second algorithm reappears there.
- **Search**: canonicalizing changes what the UI shows, not what a substring matches —
  `chave_busca` is canonical alnum when the value parses, RAW alnum otherwise; normalize the
  needle too and floor it (`CHAVE_BUSCA_MIN`). See memory `feedback_canonicalizing_a_value_breaks_search`.
- **Honest limits:** titulo/NIS/CNH DV rules are implemented from the published algorithms and
  hand-verified on synthetic values only; CNS cartório and Cotia IM have no published DV
  (`dv_ok=None`). The SQL twin is parity-checked at apply time (no local Postgres in the seed).
