/**
 * Shared SSO context utilities.
 *
 * When a user enters a product via SSO from NoctusAI Core, the Core's
 * /api/sso/session endpoint syncs role, org, subscription, and license
 * info into the user's Supabase `user_metadata`.  These helpers read
 * that metadata so every product can determine access and display
 * context-aware UI consistently.
 */

import { ADMIN_ROLES } from './roles';
import type { OrgRole } from './roles';
import type { MeAccess } from './access';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Metadata = Record<string, any> | undefined | null;

// ---------------------------------------------------------------------------
// Role resolution (lightweight — used everywhere)
// ---------------------------------------------------------------------------

export interface SSORoleInfo {
  isSSO: boolean;
  isProductAdmin: boolean;
}

/**
 * Resolve SSO role information from user metadata.
 *
 * 1. `org_role` in ("owner", "admin") → product admin
 * 2. `noctus_role === "admin"` → product admin (NoctusAI admin — full access)
 * 3. Otherwise → not a product admin
 */
export function resolveSSORoles(metadata: Metadata): SSORoleInfo {
  if (!metadata) return { isSSO: false, isProductAdmin: false };

  const isSSO = !!metadata.noctus_role || !!metadata.org_role;

  const isProductAdmin =
    metadata.org_role === 'owner' ||
    metadata.org_role === 'admin' ||
    metadata.noctus_role === 'admin';

  return { isSSO, isProductAdmin };
}

// ---------------------------------------------------------------------------
// Full SSO context (rich — for layouts, feature gating, branding)
// ---------------------------------------------------------------------------

export interface SSOPlanInfo {
  slug: string | null;
  maxUsers: number | null;
  maxProducts: number | null;
  features: Record<string, unknown> | null;
}

export interface SSOSubscriptionInfo {
  status: string | null;
  expiresAt: string | null;
}

export interface SSOLicenseInfo {
  expiresAt: string | null;
}

export interface SSOOrgInfo {
  name: string | null;
  logoUrl: string | null;
  role: string;
}

export interface SSOContext extends SSORoleInfo {
  plan: SSOPlanInfo;
  subscription: SSOSubscriptionInfo;
  license: SSOLicenseInfo;
  org: SSOOrgInfo;
}

/**
 * Resolve the full SSO context from user metadata.
 *
 * Includes everything from `resolveSSORoles()` plus subscription plan,
 * license expiry, and org branding info.  All fields gracefully default
 * to null when the corresponding data wasn't synced.
 */
export function resolveSSOContext(metadata: Metadata): SSOContext {
  const roles = resolveSSORoles(metadata);
  const m = metadata || {};

  return {
    ...roles,
    plan: {
      slug: m.plan_slug ?? null,
      maxUsers: m.plan_max_users ?? null,
      maxProducts: m.plan_max_products ?? null,
      features: m.plan_features ?? null,
    },
    subscription: {
      status: m.subscription_status ?? null,
      expiresAt: m.subscription_expires_at ?? null,
    },
    license: {
      expiresAt: m.license_expires_at ?? null,
    },
    org: {
      name: m.org_name ?? null,
      logoUrl: m.org_logo_url ?? null,
      role: m.org_role ?? 'member',
    },
  };
}

// ---------------------------------------------------------------------------
// Helpers for common checks
// ---------------------------------------------------------------------------

/** True if subscription is in trial and expiry date is set. */
export function isTrial(ctx: SSOContext): boolean {
  return ctx.subscription.status === 'trial' && !!ctx.subscription.expiresAt;
}

/** Days remaining until subscription expires. Null if no expiry date. */
export function subscriptionDaysRemaining(ctx: SSOContext): number | null {
  const exp = ctx.subscription.expiresAt;
  if (!exp) return null;
  const diff = new Date(exp).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

/** Days remaining until license expires. Null if permanent (no expiry). */
export function licenseDaysRemaining(ctx: SSOContext): number | null {
  const exp = ctx.license.expiresAt;
  if (!exp) return null;
  const diff = new Date(exp).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

/**
 * THE "is this user an org admin?" UX gate (was hand-copied 14x).
 *
 * True for a product admin (`org_role` owner/admin or `noctus_role` admin)
 * OR an org role of owner/admin. Org-picker note: platform staff are
 * `noctus_role === 'admin'` so `isProductAdmin` is already true for them
 * whichever org they pick (owner-equivalent per the 2026-10-08 spec); the
 * picked org needs no extra input. UX only: the backend (effective-org
 * resolver) is authoritative and re-enforces on every request.
 */
export function isOrgAdmin(ctx: Pick<SSOContext, 'isProductAdmin'> & { org: { role: string } }): boolean {
  return ctx.isProductAdmin || ADMIN_ROLES.includes(ctx.org.role as OrgRole);
}

// ---------------------------------------------------------------------------
// Effective org of THIS visit (multi-org S5b)
// ---------------------------------------------------------------------------

/** Where the org/role of an {@link EffectiveSSOContext} came from. */
export type EffectiveOrgSource = 'access' | 'token';

export interface EffectiveSSOContext extends SSOContext {
  /**
   * `access` = the server's EFFECTIVE org (`GET /api/me/access`); `token` = the SSO
   * token's org, used ONLY while access has not answered (pending, or no answer).
   */
  orgSource: EffectiveOrgSource;
  /** The effective org's id (access `org.id`; the token's `org_id` only as the fallback). */
  orgId: string | null;
}

/**
 * The SSO context with `org` + `isProductAdmin` re-based on the EFFECTIVE org of this
 * visit. The SSO token names the org that ADMITTED the user; after a member (or staff)
 * switches org through the picker, the server's effective org (`/api/me/access` `org` +
 * `org_selection.org_role`) is a different one -- the shell's subtitle, role label and
 * admin gate must follow it, never the token.
 *
 * - `access` undefined (pending / no answer) -> the token, `orgSource: 'token'`.
 * - `access` answered -> its org name (null when it has none -- never the token's) and its
 *   `org_role` (`null` -> `member`). A pre-picker backend sends no `org_role` (`undefined`):
 *   no switch is possible there, so the token's role IS the effective one.
 * - `isProductAdmin` = platform admin (`noctus_role`, platform-wide) OR an owner/admin
 *   EFFECTIVE role -- the token's `org_role` no longer counts once access answered.
 *
 * Plan / subscription / license stay the token's (out of scope: core syncs them per
 * admitting org). UX only -- the server re-enforces on every request.
 */
export function resolveEffectiveSSOContext(
  metadata: Metadata,
  access: MeAccess | null | undefined,
): EffectiveSSOContext {
  const token = resolveSSOContext(metadata);
  if (!access) {
    const tokenOrgId = typeof metadata?.org_id === 'string' ? metadata.org_id : null;
    return { ...token, orgSource: 'token', orgId: tokenOrgId };
  }
  const answered = access.org_selection?.org_role;
  const role = answered === undefined ? token.org.role : (answered ?? 'member');
  const isPlatformAdmin = metadata?.noctus_role === 'admin';
  return {
    ...token,
    isProductAdmin: isPlatformAdmin || ADMIN_ROLES.includes(role as OrgRole),
    // /api/me/access carries no logo: the token's belongs to the token's org.
    org: { name: access.org?.nome ?? null, logoUrl: null, role },
    orgSource: 'access',
    orgId: access.org?.id ?? null,
  };
}
