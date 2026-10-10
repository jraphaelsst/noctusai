import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();
vi.mock('@noctusai/seed/infra', () => ({
  supabase: { removeAllChannels: async () => [] },
  api: { get: (...a: unknown[]) => apiGet(...a), put: vi.fn(), delete: vi.fn() },
}));

import { useOrgSelection, resetOrgSelectionPage, ME_ACCESS_QUERY_KEY } from './org-selection';
import { getOrgPin, setOrgPin, notifyOrgSelectionChanged } from './org-pin';

const X = { id: 'x', nome: 'X' };
const Y = { id: 'y', nome: 'Y' };
const access = (org: { id: string; nome: string }) => ({
  has_access: true, product_slug: 'p', org,
  org_selection: {
    available: true, required: false, mfa_required: false, acting: true,
    org, home_org: X, selection_id: `sel-${org.id}`,
  },
});

describe('useOrgSelection pin vs org swap', () => {
  const reload = vi.fn();
  const orig = window.location;
  let qc: QueryClient;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  beforeEach(() => {
    apiGet.mockReset(); reload.mockReset();
    resetOrgSelectionPage(); setOrgPin(null);
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    Object.defineProperty(window, 'location', { configurable: true, value: { ...orig, reload } });
  });
  afterEach(() => {
    cleanup();
    Object.defineProperty(window, 'location', { configurable: true, value: orig });
  });

  it('first access pins without reload', async () => {
    apiGet.mockResolvedValue(access(X));
    renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    expect(reload).not.toHaveBeenCalled();
  });

  it('access reporting another org under an existing pin reloads, never re-pins', async () => {
    apiGet.mockResolvedValue(access(X));
    renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    apiGet.mockResolvedValue(access(Y));
    await qc.invalidateQueries({ queryKey: ME_ACCESS_QUERY_KEY });
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    expect(getOrgPin()).toBe('x');
  });

  it('after a 409 pin-clear, a refetch reporting another org reloads instead of silently re-pinning', async () => {
    apiGet.mockResolvedValue(access(X));
    renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    notifyOrgSelectionChanged();
    expect(getOrgPin()).toBeNull();
    apiGet.mockResolvedValue(access(Y));
    await qc.invalidateQueries({ queryKey: ME_ACCESS_QUERY_KEY });
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    expect(getOrgPin()).not.toBe('y');
  });

  it('same-org refetch does not reload (and restores the pin after a 409 clear)', async () => {
    apiGet.mockResolvedValue(access(X));
    renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    notifyOrgSelectionChanged();
    await qc.invalidateQueries({ queryKey: ME_ACCESS_QUERY_KEY });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    expect(reload).not.toHaveBeenCalled();
  });
});
