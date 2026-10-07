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

/** `GET /api/me/access` */
export interface MeAccess {
  has_access: boolean;
  product_slug: string;
  org: { id: string; nome: string } | null;
}

/** True when a parsed 403 body (flat, `{error:{}}` or `{detail:{}}`) is the license refusal. */
export function isOrgSemLicencaBody(data: unknown): boolean {
  if (!data || typeof data !== 'object') return false;
  const d = data as Record<string, any>;
  const body = d.error && typeof d.error === 'object'
    ? d.error
    : d.detail && typeof d.detail === 'object'
      ? d.detail
      : d;
  return body?.code === ORG_SEM_LICENCA_CODE;
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
 * Returns `false` ONLY on an explicit `has_access: false` (or the
 * `org_sem_licenca` 403). Any other outcome (network error, 5xx, route absent
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
    return data?.has_access !== false;
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
