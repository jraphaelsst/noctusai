# Org-admin UX gate — one seed helper, never a hand-copy

> **Rule.** "Is this user an org admin?" in a product frontend is
> `useIsOrgAdmin()` (component) or `isOrgAdmin(ctx)` (pure, over a
> `resolveSSOContext` result) from `@noctusai/lib` — never the inline
> `ctx.isProductAdmin || ctx.org.role === "owner" || ctx.org.role === "admin"`.
> Enforced by `check_hand_copied_org_admin` (pre-commit, blocking, awake
> products only).

Born 2026-10-09 (DRY recurrence). The expression had been hand-copied **15x
across 7 products** (social-wiring 8 incl. the new `PessoaPage` "Excluir
cliente" gate, community, orbity, and the asleep adconnect / daily-life /
knowledge-extractor / personal-finance). Formalized in the seed lib:

- `seed/lib/frontend/src/sso.ts` → `isOrgAdmin(ctx)`: `isProductAdmin` OR
  `org.role` ∈ `ADMIN_ROLES` (`roles.ts`). Exported from the root barrel.
- `seed/lib/frontend/src/use-is-org-admin.ts` → `useIsOrgAdmin()`: reads the
  auth store like every call site did. Exported from
  `@noctusai/lib/design-system` (beside `useOrgSelection`) because it needs
  `@noctusai/seed/infra`, which the dependency-free root barrel must not import.

## Org picker (2026-10-08) — why no extra input is needed

Platform staff picking a customer org are, by the backend's trusted check
(`seed/lib/backend/noctusai_lib/api/auth/effective_org.py` →
`is_platform_staff`), `noctus_users.role = 'admin'` AND home `org_role`
owner/admin; inside the picked org they act as `ACTING_ORG_ROLE = "owner"`.
The JWT's `noctus_role === 'admin'` already makes `isProductAdmin` true, so
the helper answers "admin" in any picked org — the owner-equivalent the spec
asks for — without reading the picker state.

## Scope and limits

- **UX only.** The server (`require_org_admin_role`, effective-org resolver)
  is authoritative and re-checks every request; `user_metadata` is
  user-writable and must never gate the backend (`check_no_metadata_authz`).
- **Variants compose, they don't copy:** `isOrgAdmin(ctx) || ctx.org.role === "dev"`
  (social-wiring `Settings.tsx`) is fine — the keeper flags only the
  `isProductAdmin` + owner/admin triple.
- **Asleep products keep their copies** until woken (no keeper walks them —
  `KB § PATTERNS/architect/product-working-scope.md`); the first commit after
  waking one surfaces them.
- Test files are not scanned (mocks may legitimately spell the shape out).
