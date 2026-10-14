/**
 * Multi-org S5b: the shell and `useIsOrgAdmin` follow the EFFECTIVE org of this visit
 * (`/api/me/access`), not the org/role the SSO token was minted with. The token stands in
 * only while access has not answered.
 */
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();
let metadata: Record<string, unknown> = {};
vi.mock('@noctusai/seed/infra', () => ({
  useAuthStore: () => ({ user: { user_metadata: metadata } }),
  api: { get: (...a: unknown[]) => apiGet(...a) },
}));

import { useIsOrgAdmin } from './use-is-org-admin';
import { useEffectiveSSOContext } from './use-effective-sso-context';
import { resolveEffectiveSSOContext } from './sso';
import type { MeAccess } from './access';

const accessIn = (id: string, nome: string, orgRole: string | null | undefined): MeAccess => ({
  has_access: true,
  product_slug: 'p',
  org: { id, nome },
  org_selection: {
    available: true, required: false, mfa_required: false, acting: false,
    org: { id, nome }, home_org: null, selection_id: 'sel', org_role: orgRole,
  },
});

describe('resolveEffectiveSSOContext', () => {
  const token = { org_id: 'org-a', org_name: 'Org A', org_role: 'owner' };

  it('no access answer yet: the token, flagged as such', () => {
    const ctx = resolveEffectiveSSOContext(token, undefined);
    expect(ctx).toMatchObject({ orgSource: 'token', orgId: 'org-a', isProductAdmin: true });
    expect(ctx.org).toMatchObject({ name: 'Org A', role: 'owner' });
  });

  it('access answered: its org + role replace the token ones (admin does not leak)', () => {
    const ctx = resolveEffectiveSSOContext(token, accessIn('org-b', 'Org B', 'member'));
    expect(ctx).toMatchObject({ orgSource: 'access', orgId: 'org-b', isProductAdmin: false });
    expect(ctx.org).toMatchObject({ name: 'Org B', role: 'member', logoUrl: null });
  });

  it('access answered with no org: never the token org', () => {
    const ctx = resolveEffectiveSSOContext(token, { has_access: false, product_slug: 'p', org: null });
    expect(ctx.org.name).toBeNull();
    expect(ctx.orgId).toBeNull();
  });

  it('org_role null means no role in the effective org (member, not the token admin)', () => {
    const ctx = resolveEffectiveSSOContext(token, accessIn('org-b', 'Org B', null));
    expect(ctx.org.role).toBe('member');
    expect(ctx.isProductAdmin).toBe(false);
  });

  it('pre-picker backend (no org_role key): the token role IS the effective one', () => {
    const ctx = resolveEffectiveSSOContext(token, { has_access: true, product_slug: 'p', org: { id: 'org-a', nome: 'Org A' } });
    expect(ctx.org.role).toBe('owner');
    expect(ctx.isProductAdmin).toBe(true);
  });

  it('platform staff stay product admin in any effective org', () => {
    const ctx = resolveEffectiveSSOContext(
      { ...token, noctus_role: 'admin' }, accessIn('org-c', 'Cliente C', 'member'),
    );
    expect(ctx.isProductAdmin).toBe(true);
    expect(ctx.org.name).toBe('Cliente C');
  });
});

describe('useIsOrgAdmin / useEffectiveSSOContext — follow the effective role', () => {
  let qc: QueryClient;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  beforeEach(() => {
    apiGet.mockReset();
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  });
  afterEach(() => cleanup());

  it('token member, switched into an org they own: admin once access answers', async () => {
    metadata = { org_id: 'org-a', org_name: 'Org A', org_role: 'member' };
    apiGet.mockResolvedValue(accessIn('org-b', 'Org B', 'owner'));
    const { result } = renderHook(() => ({ admin: useIsOrgAdmin(), ctx: useEffectiveSSOContext() }), { wrapper });
    // pending: the token stands in
    expect(result.current.admin).toBe(false);
    expect(result.current.ctx.orgSource).toBe('token');
    await waitFor(() => expect(result.current.admin).toBe(true));
    expect(result.current.ctx.org.name).toBe('Org B');
    expect(apiGet).toHaveBeenCalledWith('/api/me/access');
  });

  it('token owner, switched into an org where they are a member: not admin', async () => {
    metadata = { org_id: 'org-a', org_name: 'Org A', org_role: 'owner' };
    apiGet.mockResolvedValue(accessIn('org-b', 'Org B', 'member'));
    const { result } = renderHook(() => useIsOrgAdmin(), { wrapper });
    expect(result.current).toBe(true); // token, while pending
    await waitFor(() => expect(result.current).toBe(false));
  });

  it('shares ONE /api/me/access request across consumers', async () => {
    metadata = { org_role: 'member' };
    apiGet.mockResolvedValue(accessIn('org-b', 'Org B', 'admin'));
    const { result } = renderHook(() => [useIsOrgAdmin(), useIsOrgAdmin(), useEffectiveSSOContext()], { wrapper });
    await waitFor(() => expect(result.current[0]).toBe(true));
    expect(apiGet).toHaveBeenCalledTimes(1);
  });
});

describe('without a QueryClientProvider (isolated component tests)', () => {
  beforeEach(() => { apiGet.mockReset(); });
  afterEach(() => cleanup());

  it('never throws, never fetches, and reads the token org/role like the pending state', () => {
    metadata = { org_id: 'org-a', org_name: 'Org A', org_role: 'owner' };
    const { result } = renderHook(() => ({ admin: useIsOrgAdmin(), ctx: useEffectiveSSOContext() }));
    expect(result.current.admin).toBe(true);
    expect(result.current.ctx).toMatchObject({ orgSource: 'token', orgId: 'org-a' });
    expect(apiGet).not.toHaveBeenCalled();
  });
});
