# Julia's mistakes ledger - schema (extension of the generic living ledger)

One row per mistake, in `julia-mistakes.ndjson` (one JSON object per line). INTERIM: a plain file in the shape below; it plugs
into `noctus.dev.findings_ledger` (append / close / status / query / reconcile, one shared drift keeper) as Julia's schema
extension when that lands. Do not hand-edit once the tool exists: append and close through it. `LEDGER.md` is the rendered summary.

| field | meaning |
|---|---|
| `id` | `JL-NNN` |
| `titulo` | one line: the symptom |
| `fonte` | `{tipo: eval-run \| prod-conversation \| handoff \| compliance-retry \| owner-report, ref: run id / case slug / thread ref}` |
| `atribuicao` | `MODEL` (passes on other runs with the same state: wording, variance) \| `STRUCTURAL` (wiring, state, gate, harness, counters) \| `CONTENT` (contradictory or missing instructions) \| `AMBIGUOUS` |
| `evidencia` | what input the model actually had / what the trace showed |
| `camada_fix` | `code` \| `content-draft` \| `eval-case` \| `deploy` \| `owner-decision` \| `none` |
| `status` | `open` \| `in-progress <branch>` \| `fixed <sha>` \| `accepted <rationale>` |
| `caso_eval` | the mechanism case slug that reproduces it (a fix is not done until it is in the suite and passes on the real turn path) |
| `passk` | latest `{k, aprovadas, run, hash, em}` the reconcile hook saw for `caso_eval` |
| `xref` | cross-reference to the security burn-down row (leaks / prompt exposure) - never a duplicate |
| `aberto_em`, `atualizado_em` | dates |

**Reconcile hook** (`reconcilia.py`): reads a runner result (`tools/rodar_mecanismo_local.py --out`) and decides each row from the latest
run of its `caso_eval`: a failing case reopens a `fixed` row; a case that passes pass^k closes an `open` / `in-progress` one;
`accepted` rows are left alone. `--check` exits 1 when a status disagrees with the `passk` the last run recorded.
