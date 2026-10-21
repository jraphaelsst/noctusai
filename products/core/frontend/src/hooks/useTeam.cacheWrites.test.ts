/**
 * Cache writes (wave 2 of the invalidate-only fan-out) for the team hooks: the list shows
 * the change while the request is in flight / the moment it answers.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock('../lib/api', () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, put: mockPut, delete: mockDelete },
}));

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const w = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, w };
}

beforeEach(() => {
  vi.resetAllMocks();
  mockGet.mockReturnValue(new Promise(() => {})); // the settle refetch must never be what the test relies on
});

describe('team cache writes', () => {
  it('a removed member leaves the list on the click', async () => {
    const { qc, w } = setup();
    qc.setQueryData(['core', 'team', 'members', 'o1'], [{ id: 'u1' }, { id: 'u2' }]);
    mockDelete.mockReturnValue(new Promise(() => {}));
    const { useRemoveMember } = await import('./useTeam');
    const { result } = renderHook(() => useRemoveMember('o1'), { wrapper: w });
    result.current.mutate('u1');
    await waitFor(() => expect(qc.getQueryData(['core', 'team', 'members', 'o1'])).toEqual([{ id: 'u2' }]));
  });

  it('a role change is drawn on the click and rolled back when it fails', async () => {
    const { qc, w } = setup();
    qc.setQueryData(['core', 'team', 'members', 'o1'], [{ id: 'u1', org_role: 'member' }]);
    mockPatch.mockRejectedValue(new Error('403'));
    const { useChangeMemberRole } = await import('./useTeam');
    const { result } = renderHook(() => useChangeMemberRole('o1'), { wrapper: w });
    result.current.mutate({ userId: 'u1', role: 'admin' });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData<any>(['core', 'team', 'members', 'o1'])[0].org_role).toBe('member');
  });

  it('an invitation is first in the pending list and the secret token is not cached', async () => {
    const { qc, w } = setup();
    qc.setQueryData(['core', 'team', 'invitations', 'o1'], [{ id: 'i0' }]);
    mockPost.mockResolvedValue({
      data: { id: 'i1', email: 'a@b.c', role: 'member', status: 'pending', invited_by: 'u', expires_at: 'x', created_at: 'y', token: 'SECRET' },
    });
    const { useInviteMember } = await import('./useTeam');
    const { result } = renderHook(() => useInviteMember('o1'), { wrapper: w });
    result.current.mutate({ email: 'a@b.c', role: 'member' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const list = qc.getQueryData<any[]>(['core', 'team', 'invitations', 'o1'])!;
    expect(list.map((i) => i.id)).toEqual(['i1', 'i0']);
    expect(list[0]).not.toHaveProperty('token');
  });

  it('a product block flips on the click', async () => {
    const { qc, w } = setup();
    const key = ['core', 'team', 'product-access', 'o1', 'u1'];
    qc.setQueryData(key, { products: [{ slug: 'erp', blocked: false }], can_edit: true, target_is_staff: false });
    mockPut.mockReturnValue(new Promise(() => {}));
    const { useSetMemberProductAccess } = await import('./useTeam');
    const { result } = renderHook(() => useSetMemberProductAccess('o1', 'u1'), { wrapper: w });
    result.current.mutate({ slug: 'erp', blocked: true });
    await waitFor(() => expect(qc.getQueryData<any>(key).products[0].blocked).toBe(true));
  });
});
