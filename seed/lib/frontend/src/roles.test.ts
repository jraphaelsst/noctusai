/**
 * `roles.ts` — the dev-page visibility contract.
 *
 * These exist because `isDevOrOwner` used to hardcode `owner || dev` right
 * beside a `DEV_ROLES` const it ignored, and nothing caught the divergence:
 * the const said one thing, the function did another, and the fleet-wide
 * dev-page gate flowed through the function. Now the function consumes the
 * const, and this file pins that it does.
 */
import { describe, expect, it } from 'vitest';

import { ASSIGNABLE_ROLES, DEV_ROLES, grantableRoles, isDevOrOwner } from './roles';

describe('DEV_ROLES', () => {
  it('is the single source of truth for dev-page visibility', () => {
    // 🔴 PARITY CONTRACT with the `dev_veem_desenvolvimento` RLS policy in
    // every `*_status_pagina_dev_visibility.sql`. Changing this list means
    // changing those migrations in the same commit — `check_status_pagina_
    // role_parity` enforces it, and this assertion states the expected value
    // so a silent edit here fails loudly rather than drifting the fleet.
    expect([...DEV_ROLES].sort()).toEqual(['admin', 'dev', 'owner']);
  });
});

describe('isDevOrOwner', () => {
  it.each(DEV_ROLES)('grants %s', (role) => {
    expect(isDevOrOwner(role)).toBe(true);
  });

  it('grants admin — the role the old hardcoded check silently omitted', () => {
    expect(isDevOrOwner('admin')).toBe(true);
  });

  it.each(['manager', 'member', 'viewer', 'test'])('denies %s', (role) => {
    expect(isDevOrOwner(role)).toBe(false);
  });

  it('denies an absent role rather than throwing', () => {
    expect(isDevOrOwner(null)).toBe(false);
    expect(isDevOrOwner(undefined)).toBe(false);
    expect(isDevOrOwner('')).toBe(false);
  });

  it('denies an unknown role string', () => {
    expect(isDevOrOwner('superuser')).toBe(false);
  });
});

describe('grantableRoles', () => {
  // finais, 2026-09-28: before this, the invite form offered "Administrador"
  // to a Gerente (manager), who then got a 403 from the backend's
  // `_GRANT_REQUIRES` gate — the dropdown must never offer what the server
  // will refuse.
  it('a non-product-admin (e.g. a manager) never sees "admin"', () => {
    expect(grantableRoles(false)).not.toContain('admin');
  });

  it('a non-product-admin still sees every other assignable role', () => {
    expect(grantableRoles(false)).toEqual(ASSIGNABLE_ROLES.filter((r) => r !== 'admin'));
  });

  it('a product admin (org owner/admin, or a NoctusAI platform operator) sees every assignable role', () => {
    expect(grantableRoles(true)).toEqual(ASSIGNABLE_ROLES);
  });
});
