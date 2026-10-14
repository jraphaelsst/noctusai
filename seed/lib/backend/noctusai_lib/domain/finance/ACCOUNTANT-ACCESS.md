# Accountant read access (E16) — what it is and how an org admin grants it

An external contador gets **read-only** access to the finance reports and exports. Never a write, never more than the org that granted it.

## What the grant opens

`accountant_dependency` = *org admin* **OR** *holds the permission `finance.accountant_read:<org_id>`* (checked through the seed permissions repo,
`domain/permissions`). It guards these GETs (everything else — and every write — stays `admin_dependency`):

`/reports/dre` · `/reports/simples-base` · `/reports/budget` · `/budgets` · `/reports/livro-caixa` · `/reports/mei-monthly` · `/accountant-checklist` ·
`/exports/dre.csv` · `/exports/entries.csv` · `/exports/ledger.ofx` · `/exports/livro-caixa.{csv,pdf}` · `/exports/mei-monthly.{csv,pdf}` · `/exports/dominio.txt`

* **Per org, by construction.** `public.user_permission_grants` is user-global and the permission string is opaque, so the org is part of the string
  (`accountant_permission_for(cfg, org_id)`). A grant written by client A's admin opens nothing in client B; the bare `finance.accountant_read` opens nothing.
* **Masking unchanged.** `FinanceContext.is_admin` stays false for the accountant, so counterparty CPF/CNPJ stay masked in `entries.csv` and lists. Unmasking is an org-admin decision made by
  making that person an org admin — there is deliberately no half-way role.
* **Not an admin.** The accountant cannot change anything, including the budget, the DRE settings and the accounting codes.
* `mount_finance(...)` wires it (default repo = Supabase over `get_core_client()`, core migration 046; pass `permissions=` to inject a Fake). A host calling `make_finance_router` directly passes
  `accountant_dependency=`; without it the reads are admin-only exactly as before.

## How an org admin grants it today

1. Invite the accountant into the org as ordinary staff (the existing org invitation flow); they need a license-gated membership in that org.
2. Record the grant for that user and org: `make_permission_grant_repository(supabase_client=core).add_grant(user_id=..., permission=accountant_permission_for(cfg, org_id), granted_by=admin_id)`,
   or the SQL equivalent `insert into public.user_permission_grants (user_id, permission, granted_by) values ('<user>', 'finance.accountant_read:<org_id>', '<admin>')`.
3. Revoke with `remove_grant` / `delete` of that row.

**Gap (NOC-REMEDIATE[finance-accountant-grant-ui]: no screen exists to grant/revoke — the permissions slice ships the repository only, "WHO may grant is the consumer's route-level decision" — 2026-10-14).**
Until a host ships that screen (a "Convidar contador" action next to the team page that does step 1 + 2), step 2 is an operator action. The UI hides nothing the server would not refuse:
the `FinanceShell` prop `isAccountant` is UX only.
