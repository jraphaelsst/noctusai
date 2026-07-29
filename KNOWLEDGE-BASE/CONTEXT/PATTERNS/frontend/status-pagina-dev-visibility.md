# `status_pagina` dev-visibility — an RLS read-policy makes the FE branch dead

> **Rule.** A page's visibility gate is **two halves in two languages**: the RLS
> policy that decides whether the `status_pagina` row is **returned**, and the
> frontend `DEV_ROLES` const that decides whether the returned row is
> **rendered**. If RLS filters a status out, every downstream FE branch keyed on
> that status is **dead code** — and the two halves must name the SAME roles or
> you get split-brain. Enforced by `check_status_pagina_role_parity`.

Born 2026-07-17, landed 2026-07-29. `status_pagina` shipped with exactly one
policy — `todos_veem_producao USING (status = 'producao')`. The frontend reads
the table through the product's **authenticated** Supabase client, so RLS
applies: a `desenvolvimento` row was returned to **nobody, not even an owner**.
`isPageVisible()` then did `find() → undefined → return false`, making its own
`if (status === 'desenvolvimento') return isDevOrOwner(...)` branch, and the
"DEV" badge beside it, unreachable.

Live blast radius: `instagram_insights` and `meta` were seeded
`desenvolvimento` and were therefore **invisible in production to every user
including the operator** — while the whole Anúncios console, IG Conteúdo and IG
Visão geral were shipped, deployed and smoke-tested behind them.

---

## Why it hides so well

Both failure modes present identically — *"the page is just missing from the
sidebar"*:

| Divergence | RLS says | FE says | User sees |
|---|---|---|---|
| Status filtered by RLS | row not returned | branch never runs | page missing |
| Role only in SQL | row returned | `isDevOrOwner` false → hidden | page missing |
| Role only in FE | row not returned | would have rendered | page missing |

Nothing errors. No log line. The FE gate *looks* correct in review — the bug is
only visible from `pg_policies`, which is why this is a
[[feedback_verify_live_runtime_before_spec]] instance: the spec was right and
the read path silently disagreed.

The generalisation is the reusable part: **an RLS read-policy that filters out a
category makes every downstream code branch keyed on that category dead.** The
DB read path and the FE gate are two halves of one contract that drift
independently.

---

## The shape that works

Two additive legs, same commit:

1. **A second, additive SELECT policy.** Postgres OR's permissive policies, so
   adding `dev_veem_desenvolvimento` can only *widen* visibility —
   `todos_veem_producao` is never touched.

   ```sql
   DROP POLICY IF EXISTS "dev_veem_desenvolvimento" ON <schema>.status_pagina;
   CREATE POLICY "dev_veem_desenvolvimento" ON <schema>.status_pagina
       FOR SELECT TO authenticated
       USING (
           status = 'desenvolvimento'
           AND public.current_org_role() = ANY (ARRAY['owner', 'dev', 'admin'])
       );
   ```

   - `TO authenticated` is **mandatory** — anon has no `auth.uid()`, so
     `current_org_role()` is `NULL` and `NULL = ANY(...)` is false ⇒ zero rows.
   - Scoped to `'desenvolvimento'` only; `'desativado'` stays hidden from all.
   - `DROP` + `CREATE` (there is no `CREATE POLICY IF NOT EXISTS`) for
     idempotent re-application.

2. **`public.current_org_role()`** — `STABLE SECURITY DEFINER` with
   `SET search_path TO 'public'`, symmetric with `current_org_id()`. The role
   comes from `public.noctus_users.org_role` keyed on `auth.uid()`: a
   core-managed, **server-owned** table. 🔴 **Never `user_metadata`** — that JWT
   claim is user-spoofable and must never key RLS
   (`KB § PATTERNS/backend/database-rls.md`, [[feedback_rls_never_key_on_user_metadata]]).

---

## 🔴 The parity contract

The SQL role array and the frontend `DEV_ROLES` const
(`seed/lib/frontend/src/roles.ts`) **must name the same roles**. There is no
shared source between a SQL literal and a TS const, and after the fleet fan-out
there are **N+1 files** to keep in lockstep — hand-syncing was never going to
hold.

`check_status_pagina_role_parity` (`--check-status-pagina-role-parity`) compares
every `**/migrations/*status_pagina_dev_visibility.sql` against the const and
reports the exact set difference. It treats an **unparseable** role list on
either side as an issue rather than a pass — an unreadable contract is precisely
where drift hides.

`isDevOrOwner` must **consume** `DEV_ROLES`, not restate it. The original
hardcoded `orgRole === 'owner' || orgRole === 'dev'` sat directly beside the
const it ignored, and silently omitted `admin`.

---

## How to apply

- Adding a nav item that is not ready ⇒ it needs a `status_pagina` row; until
  the dev-visibility policy exists in that schema, `desenvolvimento` means
  **hidden from everyone**, not "hidden from non-devs".
- Changing who sees dev pages ⇒ change `DEV_ROLES` **and** every
  `*_status_pagina_dev_visibility.sql` in the same commit; the keeper blocks
  otherwise.
- New product ⇒ inherits the policy from `templates/product-seed/backend/migrations/005_status_pagina_dev_visibility.sql`.
- Verifying ⇒ query `pg_policies`, not the FE. The FE cannot tell you what the
  read path returned.

## Composes with

- `KB § PATTERNS/backend/database-rls.md` — the RLS trust-root rules.
- `KB § PATTERNS/frontend/product-internal-wiring.md` — route-exists ≠ wired;
  this is the gate-exists ≠ readable sibling.
- `KB § PATTERNS/common/gate-methodology-sync.md` — why the keeper shipped in
  the same commit as the fan-out that made hand-syncing untenable.
