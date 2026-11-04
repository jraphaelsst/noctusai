import * as React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';

import { ApiError, type ApiClient } from '../../api';
import {
  createApiTokensHooks,
  maskTokenPrefix,
  tokenRefusalMessage,
  type ApiTokenItem,
  type MintedApiToken,
} from './createApiTokensHooks';

let api: ApiClient;
let qc: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client: qc }, children);

const row = (id: string, over: Partial<ApiTokenItem> = {}): ApiTokenItem => ({
  id, label: `t-${id}`, prefix: 'noc_3a4f9c01', scopes: ['reminders:read'], created_at: '2026-11-04T10:00:00Z',
  last_used_at: null, revoked_at: null, expires_at: null, service_account_id: null, ...over,
});
const minted = (id: string): MintedApiToken => ({
  id, label: `t-${id}`, token: `noc_${id}secret`, prefix: 'noc_aaaabbbb', scopes: ['reminders:read'],
  created_at: '2026-11-04T11:00:00Z', expires_at: null,
});

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() } as unknown as ApiClient;
});

describe('maskTokenPrefix', () => {
  it('keeps the first 4 and the last 4 characters', () => {
    expect(maskTokenPrefix('noc_3a4f9c01')).toBe('noc_••••9c01');
  });
  it('never lengthens a short value', () => {
    expect(maskTokenPrefix('noc_')).toBe('noc_');
  });
});

describe('tokenRefusalMessage', () => {
  it('names the MFA refusal', () => {
    const err = new ApiError(403, 'mfa_required', { detail: 'mfa_required' });
    expect(tokenRefusalMessage(err)).toMatch(/MFA/);
  });
  it('names the unknown-scope refusal', () => {
    const err = new ApiError(422, 'x', { detail: 'unknown token scopes: root:*' });
    expect(tokenRefusalMessage(err)).toContain('root:*');
  });
  it('names a platform-admin refusal', () => {
    const err = new ApiError(403, 'x', { detail: { code: 'platform_admin_required' } });
    expect(tokenRefusalMessage(err)).toMatch(/administradores/);
  });
});

describe('queries', () => {
  it('lists tokens and reads the server scope allow-list', async () => {
    (api.get as any).mockImplementation(async (p: string) => (p.endsWith('/scopes') ? { scopes: ['a:read'], strict: true } : [row('1')]));
    const h = createApiTokensHooks(api);
    const list = renderHook(() => h.useApiTokens(), { wrapper });
    const scopes = renderHook(() => h.useTokenScopes(), { wrapper });
    await waitFor(() => expect(list.result.current.data).toHaveLength(1));
    await waitFor(() => expect(scopes.result.current.data?.scopes).toEqual(['a:read']));
    expect(api.get).toHaveBeenCalledWith('/api/settings/api-tokens');
    expect(api.get).toHaveBeenCalledWith('/api/settings/api-tokens/scopes');
    expect(list.result.current.showSkeleton).toBe(false);
  });
});

describe('writes land in the list cache', () => {
  const seed = (h: ReturnType<typeof createApiTokensHooks>, rows: ApiTokenItem[]) => {
    (api.get as any).mockResolvedValue(rows);
    return renderHook(() => ({ list: h.useApiTokens(), mint: h.useMintToken(), rotate: h.useRotateToken(), revoke: h.useRevokeToken() }), { wrapper });
  };

  it('mint posts an explicit no_expiry and prepends the new row', async () => {
    const h = createApiTokensHooks(api);
    const r = seed(h, [row('1')]);
    await waitFor(() => expect(r.result.current.list.data).toHaveLength(1));
    // The settle refetch never answers: what the cache holds is the write's own doing.
    (api.get as any).mockReturnValue(new Promise(() => undefined));
    (api.post as any).mockResolvedValue(minted('2'));
    await act(() => r.result.current.mint.mutateAsync({ label: 'x', scopes: ['reminders:read'], expiresInDays: null, serviceAccountId: 'sa1' }));
    expect(api.post).toHaveBeenCalledWith('/api/settings/api-tokens', {
      label: 'x', scopes: ['reminders:read'], no_expiry: true, service_account_id: 'sa1',
    });
    expect(qc.getQueryData<ApiTokenItem[]>(['api-tokens', '/api/settings/api-tokens'])!.map((t) => t.id)).toEqual(['2', '1']);
  });

  it('mint with days posts expires_at, not no_expiry', async () => {
    const h = createApiTokensHooks(api);
    const r = seed(h, []);
    await waitFor(() => expect(r.result.current.list.isSuccess).toBe(true));
    (api.get as any).mockReturnValue(new Promise(() => undefined));
    (api.post as any).mockResolvedValue(minted('2'));
    await act(() => r.result.current.mint.mutateAsync({ label: 'x', scopes: ['a'], expiresInDays: 30 }));
    const body = (api.post as any).mock.calls[0][1];
    expect(body.no_expiry).toBeUndefined();
    expect(Date.parse(body.expires_at)).toBeGreaterThan(Date.now() + 29 * 86_400_000);
  });

  it('rotate revokes the old row and adds the successor', async () => {
    const h = createApiTokensHooks(api);
    const r = seed(h, [row('1')]);
    await waitFor(() => expect(r.result.current.list.data).toHaveLength(1));
    // The settle refetch never answers: what the cache holds is the write's own doing.
    (api.get as any).mockReturnValue(new Promise(() => undefined));
    (api.post as any).mockResolvedValue(minted('2'));
    await act(() => r.result.current.rotate.mutateAsync('1'));
    expect(api.post).toHaveBeenCalledWith('/api/settings/api-tokens/1/rotate', {});
    const cached = qc.getQueryData<ApiTokenItem[]>(['api-tokens', '/api/settings/api-tokens'])!;
    expect(cached.map((t) => [t.id, !!t.revoked_at])).toEqual([['2', false], ['1', true]]);
  });

  it('revoke stamps revoked_at at once and rolls back when the server refuses', async () => {
    const h = createApiTokensHooks(api);
    const r = seed(h, [row('1')]);
    await waitFor(() => expect(r.result.current.list.data).toHaveLength(1));
    (api.get as any).mockReturnValue(new Promise(() => undefined));
    (api.delete as any).mockRejectedValueOnce(new ApiError(404, 'gone'));
    await act(async () => { await r.result.current.revoke.mutateAsync('1').catch(() => undefined); });
    expect(qc.getQueryData<ApiTokenItem[]>(['api-tokens', '/api/settings/api-tokens'])![0].revoked_at).toBeNull();
    (api.delete as any).mockResolvedValueOnce(undefined);
    await act(() => r.result.current.revoke.mutateAsync('1'));
    expect(qc.getQueryData<ApiTokenItem[]>(['api-tokens', '/api/settings/api-tokens'])![0].revoked_at).not.toBeNull();
  });
});
