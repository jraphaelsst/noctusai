/**
 * Shared SSO context utilities.
 *
 * When a user enters a product via SSO from NoctusAI Core, the Core's
 * /api/sso/session endpoint syncs role, org, subscription, and license
 * info into the user's Supabase `user_metadata`.  These helpers read
 * that metadata so every product can determine access and display
 * context-aware UI consistently.
 */

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
