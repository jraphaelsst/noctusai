/**
 * Admin-gating hook for the Agentes UI.
 *
 * Contract §E ("Roles"): persona writes, agent toggles and approval
 * decisions on someone else's request are `owner`/`admin` only; any org
 * member can chat and read their own conversations — the same role set as
 * the backend's `ADMIN_ROLES = frozenset({"owner", "admin"})`
 * (`app/dependencies.py`), plus platform admins.
 *
 * The expression is the seed's canonical `useIsOrgAdmin` (this file is its
 * local name, kept so the call sites and their test mocks stay put). It reads
 * the EFFECTIVE org of the visit (`/api/me/access`) — after a member switches
 * org, the role in the org they are now in decides, not the SSO token's
 * (multi-org S6). It used to read `resolveSSORoles(user_metadata)`, which kept
 * the token's role after a switch. UX only: the server re-enforces.
 */
export { useIsOrgAdmin as useIsAdmin } from "@noctusai/lib/design-system";
