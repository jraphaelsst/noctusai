/**
 * License-gate client helpers (Round 2 — license gate).
 *
 * The SERVER is the gate (every authenticated route answers
 * `403 {code:"org_sem_licenca"}` for an org without an active license). These
 * helpers are the UX half: send the user to `/sem-acesso` instead of leaving
 * them on a shell where every call fails.
 */

/** Machine code the backend puts in the 403 body. */
export const ORG_SEM_LICENCA_CODE = 'org_sem_licenca';

/** Seed-mounted route every product serves (zero per-product code). */
export const SEM_ACESSO_PATH = '/sem-acesso';

/** Machine code of the 409 the backend answers when the SPA's org pin is stale. */
export const ORG_SELECTION_CHANGED_CODE = 'org_selection_changed';

/**
 * Machine code of the 409 a gated route answers when platform staff hold no live
 * selection on a picker-ready product (every entry is a choice — owner 2026-10-12).
 */
export const ORG_SELECTION_REQUIRED_CODE = 'org_selection_required';

export interface OrgRef { id: string; nome: string }

/** A member's eligible org for this product (`org_selection.eligible_orgs`, owner D1). */
export interface EligibleOrg { id: string; nome: string | null; org_role: string; is_home: boolean }

/** An org whose team the caller manages (`org_selection.manageable_orgs`, owner D2/D3). */
export interface ManageableOrg { id: string; nome: string | null; org_role: string }

/**
 * `org_selection` block of `GET /api/me/access` (org-picker contract; multi-org S4b contract in
 * `project-history/roadmaps/multi-org-membership-2026-10.md`).
 */
export interface OrgSelectionState {
  /**
   * Product is picker-ready AND the caller may choose: platform staff, or a MEMBER with >=2
   * eligible orgs for this product (owner D1, 2026-10-14).
   */
  available: boolean;
  /** available AND no live selection for this login yet → picker is mandatory. */
  required: boolean;
  /** Staff without aal2: picking is blocked until 2FA (members never need it, Q1). */
  mfa_required: boolean;
  /** Staff live selection whose target differs from the home org (a member is never acting). */
  acting: boolean;
  org: OrgRef | null;
  home_org: OrgRef | null;
  selection_id: string | null;
  /** The caller's role in the EFFECTIVE org (absent on a pre-picker backend). */
  org_role?: string | null;
  /** Member: this product's eligible orgs, home first (`[]` for staff). Absent pre-S4b. */
  eligible_orgs?: EligibleOrg[];
  /** `owner` = THE NoctusAI owner, `admin` = NoctusAI admin, `null` = not platform staff. */
  platform_role?: 'owner' | 'admin' | null;
  /** Platform staff: may manage ANY org's team. Absent pre-S4b. */
  manage_any_org?: boolean;
  /** The caller's ACTIVE owner/admin memberships. Absent pre-S4b. */
  manageable_orgs?: ManageableOrg[];
}

/**
 * True when the picker applies to a MEMBER (non-staff with >=2 eligible orgs, D1) rather than to
 * platform staff. Same picker, same entry handshake -- only the presentation differs (no "acting"
 * banner, the home org is the member's last-active org, roles per org). A pre-S4b backend never
 * sends `manage_any_org`; there only staff could pick, so absence reads as staff.
 */
export function isMemberOrgPicker(selection: OrgSelectionState): boolean {
  return selection.available && selection.manage_any_org === false;
}

/** `GET /api/me/org-choices` row (`org_role` on member rows). */
export interface OrgChoice { id: string; nome: string; is_home: boolean; org_role?: string }

/** `GET /api/me/access` */
export interface MeAccess {
  has_access: boolean;
  product_slug: string;
  org: { id: string; nome: string } | null;
  /** Absent on a pre-picker backend image → treat as not available. */
  org_selection?: OrgSelectionState;
}

export const ME_ACCESS_QUERY_KEY = ['me', 'access'] as const;

/**
 * THE `GET /api/me/access` query -- one key, one cache policy for every consumer (picker, gate,
 * switcher, the shell's effective org, `useIsOrgAdmin`, `TeamPage`). Lives here, dependency-free,
 * so a consumer holding its own `api` (TeamPage) shares the SAME cache entry without importing
 * `@noctusai/seed/infra`. `fetchAccess` is the caller's `GET /api/me/access`.
 */
export function meAccessQueryOptions(fetchAccess: () => Promise<MeAccess>) {
  return {
    queryKey: ME_ACCESS_QUERY_KEY,
    queryFn: fetchAccess,
    staleTime: 60_000,
    retry: false,
    placeholderData: (prev: MeAccess | undefined) => prev,
  };
}

/** Safe default for non-staff / old backends. */
export const NO_ORG_SELECTION: OrgSelectionState = {
  available: false, required: false, mfa_required: false, acting: false,
  org: null, home_org: null, selection_id: null,
};

/** Normalised `org_selection` (never undefined). */
export function orgSelectionOf(access: MeAccess | null | undefined): OrgSelectionState {
  return { ...NO_ORG_SELECTION, ...(access?.org_selection ?? {}) };
}

/** The `code` of a parsed error body (flat, `{error:{}}` or `{detail:{}}`). */
function errorCodeOf(data: unknown): unknown {
  if (!data || typeof data !== 'object') return undefined;
  const d = data as Record<string, any>;
  const body = d.error && typeof d.error === 'object'
    ? d.error
    : d.detail && typeof d.detail === 'object'
      ? d.detail
      : d;
  return body?.code;
}

/** True when a parsed 409 body (flat, `{error:{}}` or `{detail:{}}`) is the stale-pin refusal. */
export function isOrgSelectionChangedBody(data: unknown): boolean {
  return errorCodeOf(data) === ORG_SELECTION_CHANGED_CODE;
}

/**
 * True for EITHER org-picker 409 (`org_selection_changed` stale pin, or
 * `org_selection_required` no live selection) — both reopen the required picker.
 */
export function isOrgSelectionRefusalBody(data: unknown): boolean {
  const code = errorCodeOf(data);
  return code === ORG_SELECTION_CHANGED_CODE || code === ORG_SELECTION_REQUIRED_CODE;
}

/** True when a parsed 403 body (flat, `{error:{}}` or `{detail:{}}`) is the license refusal. */
export function isOrgSemLicencaBody(data: unknown): boolean {
  return errorCodeOf(data) === ORG_SEM_LICENCA_CODE;
}

export interface CheckProductAccessOptions {
  /** Product backend base URL (`env.BACKEND_API_URL`). */
  baseUrl: string;
  /** Bearer token; omit in cookie-session mode (`credentials: include`). */
  token?: string | null;
  fetchImpl?: typeof fetch;
}

/**
 * Ask the product whether the signed-in user's org holds its license.
 *
 * Returns `false` ONLY on an explicit `has_access: false` with no org choice pending (or
 * the `org_sem_licenca` 403). Any other outcome (network error, 5xx, route absent
 * on a pre-gate image) returns `true`: the server re-enforces on every call,
 * so a transient failure here must not lock a licensed user out of login.
 */
export async function checkProductAccess(opts: CheckProductAccessOptions): Promise<boolean> {
  const doFetch = opts.fetchImpl ?? fetch;
  try {
    const res = await doFetch(`${opts.baseUrl}/api/me/access`, {
      headers: opts.token ? { Authorization: `Bearer ${opts.token}` } : {},
      credentials: opts.token ? 'same-origin' : 'include',
    });
    if (res.status === 403) {
      const data = await res.json().catch(() => null);
      return !isOrgSemLicencaBody(data);
    }
    if (!res.ok) return true;
    const data = (await res.json().catch(() => null)) as Partial<MeAccess> | null;
    if (data?.has_access !== false) return true;
    // A multi-org member whose last-active org is unlicensed but who has >=2 licensed orgs has
    // no effective org until they choose one (core 081): that is the shell's org picker, not
    // `/sem-acesso` -- refusing here locked out a user the picker would have let in (2026-10-27).
    const sel = data.org_selection;
    return Boolean(sel?.available && sel.required);
  } catch {
    return true;
  }
}

/** Hard-navigate to `/sem-acesso` (no-op when already there). */
export function redirectToSemAcesso(): void {
  if (typeof window === 'undefined') return;
  if (window.location.pathname === SEM_ACESSO_PATH) return;
  window.location.assign(SEM_ACESSO_PATH);
}
