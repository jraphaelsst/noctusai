/**
 * "Can this user change agency-wide settings?" — the FE mirror of the
 * backend's `exigir_admin_da_org` (`app/pipelines.py`): a platform/product
 * admin, or an org owner/admin.
 *
 * ONE predicate for every admin-gated control (stage editors on Comercial and
 * Esteira, Automações rules, lead-source setup). Before this helper the
 * Comercial page checked `isProductAdmin || org role ∈ ADMIN_ROLES` while the
 * Esteira board checked `isProductAdmin` only — an org owner could edit one
 * board's stages and not the other's, though the server allows both.
 *
 * The expression is the seed's canonical `useIsOrgAdmin` (this file is its local
 * name, kept so the call sites and their test mocks stay put). It reads the
 * EFFECTIVE org of the visit (`/api/me/access`) — after a member switches org,
 * the role in the org they are now in decides, not the SSO token's (multi-org
 * S5b). This file used to re-implement it over `user_metadata`, which kept the
 * token's role after a switch.
 *
 * UX only: it hides what the server would refuse. The server's check (the
 * TRUSTED `public.noctus_users` cascade, not `user_metadata`) stays
 * authoritative.
 */
export { useIsOrgAdmin } from "@noctusai/lib/design-system";
