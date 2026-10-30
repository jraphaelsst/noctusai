/** Cache writes of the brand hooks: activation, patch, and the ingest -> job hand-off. */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockUpload = vi.fn();

vi.mock('../lib/api', () => ({ api: { get: mockGet, post: mockPost, patch: mockPatch, upload: mockUpload } }));
vi.mock('@noctusai/lib/design-system', async (orig) => ({
  ...(await orig<object>()),
  useEffectiveSSOContext: () => ({ orgId: 'o1' }),
}));

const tokens = { light: { primary: '1 1% 1%' }, dark: {}, radius: '0.5rem', fonts: {} };
const setup = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const w = ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, w };
};

beforeEach(() => {
  vi.resetAllMocks();
  mockGet.mockReturnValue(new Promise(() => {})); // settle refetches must never be what the test relies on
});

describe('brand cache writes', () => {
  it('activating draws the new active + archives the previous one on the click, and commits current', async () => {
    const { qc, w } = setup();
    qc.setQueryData(['core', 'brand', 'o1', 'identities'], [
      { id: 'a', version: 1, status: 'active' }, { id: 'b', version: 2, status: 'draft' },
    ]);
    qc.setQueryData(['core', 'brand', 'o1', 'identity', 'b'], { id: 'b', version: 2, status: 'draft', tokens });
    mockPost.mockResolvedValue(undefined);
    const { useActivateBrandIdentity } = await import('./useBrandIdentity');
    const { result } = renderHook(() => useActivateBrandIdentity(), { wrapper: w });
    act(() => result.current.mutate('b'));
    await waitFor(() => {
      const rows = qc.getQueryData<any[]>(['core', 'brand', 'o1', 'identities'])!;
      expect(rows.map((r) => r.status)).toEqual(['archived', 'active']);
    });
    await waitFor(() => expect((qc.getQueryData(['core', 'brand', 'o1', 'current']) as any).tokens).toEqual(tokens));
    expect(mockPost).toHaveBeenCalledWith('/api/brand/identities/b/activate');
  });

  it('a failed activation rolls the list back', async () => {
    const { qc, w } = setup();
    const before = [{ id: 'a', version: 1, status: 'active' }, { id: 'b', version: 2, status: 'archived' }];
    qc.setQueryData(['core', 'brand', 'o1', 'identities'], before);
    mockPost.mockRejectedValue(new Error('boom'));
    const { useActivateBrandIdentity } = await import('./useBrandIdentity');
    const { result } = renderHook(() => useActivateBrandIdentity(), { wrapper: w });
    act(() => result.current.mutate('b'));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData(['core', 'brand', 'o1', 'identities'])).toEqual(before);
  });

  it('patching shows the edit at once and commits the re-validated row', async () => {
    const { qc, w } = setup();
    qc.setQueryData(['core', 'brand', 'o1', 'identity', 'b'], { id: 'b', brand_book: 'old', tokens, validation: {} });
    mockPatch.mockResolvedValue({ brand_book: 'new', validation: { warnings: ['x'] } });
    const { usePatchBrandIdentity } = await import('./useBrandIdentity');
    const { result } = renderHook(() => usePatchBrandIdentity(), { wrapper: w });
    act(() => result.current.mutate({ id: 'b', brand_book: 'new' }));
    await waitFor(() => expect((qc.getQueryData(['core', 'brand', 'o1', 'identity', 'b']) as any).validation).toEqual({ warnings: ['x'] }));
    expect((qc.getQueryData(['core', 'brand', 'o1', 'identity', 'b']) as any).brand_book).toBe('new');
  });

  it('ingest sends multipart and seeds the job as queued (hand-off to polling)', async () => {
    const { qc, w } = setup();
    mockUpload.mockResolvedValue({ job_id: 'j1' });
    const { useIngestBrand } = await import('./useBrandIdentity');
    const { result } = renderHook(() => useIngestBrand(), { wrapper: w });
    act(() => result.current.mutate({ files: [new File(['x'], 'a.md')], descriptions: { 'a.md': 'doc', 'b.md': '  ' } }));
    await waitFor(() => expect(qc.getQueryData(['core', 'brand', 'o1', 'job', 'j1'])).toEqual({ status: 'queued' }));
    const [path, form] = mockUpload.mock.calls[0] as [string, FormData];
    expect(path).toBe('/api/brand/identities/ingest');
    expect(form.getAll('files')).toHaveLength(1);
    expect(JSON.parse(form.get('descriptions') as string)).toEqual({ 'a.md': 'doc' });
  });
});
