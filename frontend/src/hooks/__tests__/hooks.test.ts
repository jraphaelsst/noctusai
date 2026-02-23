/**
 * Frontend tests — API client module validation.
 * Tests are written as simple unit tests to avoid React module resolution hangs.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock supabase
vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: { session: { access_token: 'test-token-abc' } },
      }),
    },
  },
}));

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('api-client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should make GET request with auth header', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [] }),
    });

    const { api } = await import('@/lib/api-client');
    await api.get('/api/ativos');

    expect(mockFetch).toHaveBeenCalled();
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/ativos');
    expect(options.headers.Authorization).toBe('Bearer test-token-abc');
  });

  it('should append query params to GET requests', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [] }),
    });

    const { api } = await import('@/lib/api-client');
    await api.get('/api/ativos', { natureza: 'imovel', busca: 'test' });

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('natureza=imovel');
    expect(url).toContain('busca=test');
  });

  it('should skip null/undefined/empty params', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [] }),
    });

    const { api } = await import('@/lib/api-client');
    await api.get('/api/ativos', { natureza: 'imovel', busca: null, empty: '' });

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('natureza=imovel');
    expect(url).not.toContain('busca');
    expect(url).not.toContain('empty');
  });

  it('should send JSON body on POST', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: { id: 'new' } }),
    });

    const { api } = await import('@/lib/api-client');
    await api.post('/api/ativos', { natureza: 'imovel', valor: 500000 });

    const [url, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ natureza: 'imovel', valor: 500000 });
  });

  it('should send PATCH request', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: { id: 'upd' } }),
    });

    const { api } = await import('@/lib/api-client');
    await api.patch('/api/ativos/upd-1', { valor: 600000 });

    const [_, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe('PATCH');
  });

  it('should send DELETE request', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });

    const { api } = await import('@/lib/api-client');
    await api.delete('/api/ativos/del-1');

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/ativos/del-1');
    expect(options.method).toBe('DELETE');
  });

  it('should throw on 400 with detail message', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Natureza inválida' }),
    });

    const { api } = await import('@/lib/api-client');
    await expect(api.get('/api/ativos')).rejects.toThrow('Natureza inválida');
  });

  it('should throw on 401', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Token ausente' }),
    });

    const { api } = await import('@/lib/api-client');
    await expect(api.post('/api/ativos')).rejects.toThrow('Token ausente');
  });

  it('should throw on 500', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: 'Internal Error' }),
    });

    const { api } = await import('@/lib/api-client');
    await expect(api.get('/api/metas')).rejects.toThrow('Internal Error');
  });

  it('should handle non-JSON error gracefully', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 502,
      json: () => Promise.reject(new Error('Not JSON')),
    });

    const { api } = await import('@/lib/api-client');
    await expect(api.get('/api/funil')).rejects.toThrow();
  });

  it('should handle network errors', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const { api } = await import('@/lib/api-client');
    await expect(api.get('/api/profiles')).rejects.toThrow('Network error');
  });

  it('should throw when no session exists', async () => {
    const { supabase } = await import('@/integrations/supabase/client');
    vi.mocked(supabase.auth.getSession).mockResolvedValueOnce({
      data: { session: null },
    } as any);

    const { api } = await import('@/lib/api-client');
    await expect(api.get('/api/ativos')).rejects.toThrow('Não autenticado');
  });

  it('should use correct Content-Type header', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: {} }),
    });

    const { api } = await import('@/lib/api-client');
    await api.post('/api/clientes', { nome: 'Test' });

    const [_, options] = mockFetch.mock.calls[0];
    expect(options.headers['Content-Type']).toBe('application/json');
  });
});
