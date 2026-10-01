# reports/ — dated snapshots of QuintoAndar report tables

One CSV per report table we evaluated, `YYYY-MM-DD-<section>-<tab>.csv`, joined with Vista
CRM fields (via `vista.imoveis.get`, read-only). Layout of the source report:
`../knowledge/performance-report.md`.

**No personal data here** (AGENT.md rule 4): rows keep CRM code, QA id, price, period and
Vista listing fields only. Address, captador name and phone are dropped. The full version
stays local to the user's machine, outside the repo.

`acao` column (triage, derived from Vista, not from QuintoAndar):
- **A** Vista `Ocupacao=Inquilino` → probably unavailable; confirm with the captador, then discard.
- **B** Vista `Status` has no Aluguel → the rent offer is stale; discard rent in CRM/QA.
- **C** Vista read refused (`ExibirNoSite=Nao`) → check the record in Vista by hand.
- **D** everything else → contact the owner and confirm availability (QA "Central da Imobiliária").
