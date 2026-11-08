---
name: noc-tax-params
description: Use to keep the Brazilian tax-parameter registry current — triggers "atualizar parâmetros fiscais", "parâmetros fiscais vencidos", "re-verify tax params", "nova resolução CGSN", "mudou a alíquota", "N parâmetros fiscais a reverificar". Runs the staleness report, then has the accountant agent re-verify each flagged key online (primary text first) and records a bump or a successor row on a self-branch; the schema keeper judges the commit.
version: 1.0.0
---

# noc-tax-params — re-verify the fiscal parameters, never let them rot

The registry (`seed/lib/backend/noctusai_lib/domain/finance/params/*.yaml`, loader `registry.py`) is the ONLY home of Brazilian tax numbers and dates; code reads it with `param()`/`params_for()`, the canon cites its keys. Staleness is driven by the calendar, so it never blocks unrelated work — it is reported (`noctus.dev.finance_params_staleness`, rolled up daily by `noc-daily-ops`) and fixed here.

## Row contract (one YAML row = one fact over one period)
`key` · `value` (money = int centavos, rates/ratios = Decimal STRING, never a YAML float) · `unit` (`pct`·`brl_centavos`·`dia_do_mes`·`date`·`ratio`·`text`·`meses`) · `scope{regime, anexo}` · `vigencia_de` / `vigencia_ate` (null = open) · `norma` · `fonte_url[>=1]` · `tier` · `verificado_em` · `verificado_por` · `revalidar_em` (optional override of the tier age) · `notas`. Same key+scope may never overlap in time. `verificado_em` is never in the future.

## Tiers (strongest first; sets the max age in `_policy.yaml`)
`norma` (Planalto/LC/Lei/Decreto: 365 d) · `orgao_oficial` (Res. CGSN, IN RFB, Solução de Consulta, portais: 180 d) · `publicacao_tecnica` (Sebrae, CFC-adjacent, 90 d) · `especialista` (contador/blog/consultoria — needs **>= 2** `fonte_url`, 90 d, **owner review before it counts**) · `pratica` (never served as a number).

## Procedure
1. **Report** — `noctus.dev.finance_params_staleness` (CLI `--finance-params-staleness`). Reasons: `verificacao_vencida` · `vigencia_terminando` · `vigencia_encerrada_sem_sucessor`. `escalate: true` = a key with no successor ends within 15 days (or already ended): do it now. `inconclusive` = registry unreadable: fix the load first.
2. **Self-branch** (skill `noc-self-branch`): `feat/tax-params-<yyyymm>`.
3. **Dispatch agent `accountant`** (read-only advisor) with the flagged rows: re-verify EACH key ONLINE by tier — primary text first (Planalto, normasinternet2.receita.fazenda.gov.br, CGSN), a mirror only as a clue. It returns per key: still-correct / changed / not-found, with URL, accessed date, quoted sentence.
4. **Apply per key** (YAML only, then commit):
   - unchanged → bump `verificado_em` (today) + `verificado_por` (`accountant <yyyy-mm-dd>`); update the source if it moved;
   - changed or ending → add a SUCCESSOR row (new `vigencia_de`, new value/norma/sources) and close the old row's `vigencia_ate` the day before. **Never edit a closed row's value in place** — past computations must stay reproducible by date;
   - `especialista` rows (and anything the accountant could not source from `norma`/`orgao_oficial`) → flag for the owner; do not present them as settled.
5. **Commit** — pre-commit runs `check_finance_params_schema` (real loader) and `check_tax_canon_no_inline_params`; a canon line that retypes a value must cite its key in backticks. A code constant that duplicates a registry row is moved to `param()` (fix-on-contact).
6. **Hand off** — `noctus.dev.release_steward action=request slug=<slug> ...`; keep building. Reconcile closes the auto-improvement drift rows by itself once the key stops being stale (`finance_param_fresh:<key>`).
7. A human **contador (CRC)** is still required for filings, regime/Anexo choice and anything signed (`KB § PATTERNS/finance/br-tax-advisor-canon.md` §8).

## Depth
`KB § PATTERNS/finance/br-tax-advisor-canon.md` · tool `noctus.dev.finance_params_staleness` · keepers `check_finance_params_schema` + `check_tax_canon_no_inline_params` · agent `accountant`.
