import { describe, it, expect } from 'vitest';
import { isOrgAdmin, resolveSSOContext } from './sso';

const admin = (m: Record<string, unknown>) => isOrgAdmin(resolveSSOContext(m));

describe('isOrgAdmin', () => {
  it('owner and admin org roles', () => {
    expect(admin({ org_role: 'owner' })).toBe(true);
    expect(admin({ org_role: 'admin' })).toBe(true);
  });
  it('platform admin (noctus_role) even with a member org role', () => {
    expect(admin({ noctus_role: 'admin', org_role: 'member' })).toBe(true);
  });
  it('picked org: staff stay admin whatever the effective org role', () => {
    expect(admin({ noctus_role: 'admin', org_role: 'dev' })).toBe(true);
  });
  it('member, dev, manager, missing metadata are not admins', () => {
    expect(admin({ org_role: 'member' })).toBe(false);
    expect(admin({ org_role: 'dev' })).toBe(false);
    expect(admin({ org_role: 'manager' })).toBe(false);
    expect(isOrgAdmin(resolveSSOContext(null))).toBe(false);
  });
});
