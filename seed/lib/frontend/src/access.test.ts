import { describe, it, expect, vi, afterEach } from 'vitest';
import { checkProductAccess, isOrgSemLicencaBody } from './access';
import { createApiClient } from './api';

const res = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('checkProductAccess', () => {
  it('false only on explicit has_access=false', async () => {
    const f = vi.fn().mockResolvedValue(res(200, { has_access: false }));
    expect(await checkProductAccess({ baseUrl: 'http://p', token: 't', fetchImpl: f as any })).toBe(false);
    expect(f.mock.calls[0][0]).toBe('http://p/api/me/access');
    expect(f.mock.calls[0][1].headers.Authorization).toBe('Bearer t');
  });
  it('true when has_access=true', async () => {
    const f = vi.fn().mockResolvedValue(res(200, { has_access: true }));
    expect(await checkProductAccess({ baseUrl: '', token: 't', fetchImpl: f as any })).toBe(true);
  });
  it('false on 403 org_sem_licenca', async () => {
    const f = vi.fn().mockResolvedValue(res(403, { detail: 'x', code: 'org_sem_licenca' }));
    expect(await checkProductAccess({ baseUrl: '', token: 't', fetchImpl: f as any })).toBe(false);
  });
  it('fails open on network error / 5xx (server re-enforces)', async () => {
    const boom = vi.fn().mockRejectedValue(new Error('net'));
    expect(await checkProductAccess({ baseUrl: '', token: 't', fetchImpl: boom as any })).toBe(true);
    const five = vi.fn().mockResolvedValue(res(503, {}));
    expect(await checkProductAccess({ baseUrl: '', token: 't', fetchImpl: five as any })).toBe(true);
  });
  it('isOrgSemLicencaBody reads flat, error and detail shapes', () => {
    expect(isOrgSemLicencaBody({ code: 'org_sem_licenca' })).toBe(true);
    expect(isOrgSemLicencaBody({ error: { code: 'org_sem_licenca' } })).toBe(true);
    expect(isOrgSemLicencaBody({ detail: { code: 'org_sem_licenca' } })).toBe(true);
    expect(isOrgSemLicencaBody({ code: 'mfa_required' })).toBe(false);
    expect(isOrgSemLicencaBody(null)).toBe(false);
  });
});

describe('api client interceptor: 403 org_sem_licenca', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('calls onOrgSemLicenca and still rejects the call', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      res(403, { detail: 'Sua organização não tem acesso a este produto.', code: 'org_sem_licenca' }),
    ));
    const onOrgSemLicenca = vi.fn();
    const client = createApiClient({
      getBaseUrl: () => 'http://p',
      getAuthToken: async () => 't',
      onOrgSemLicenca,
    });
    await expect(client.get('/api/x')).rejects.toMatchObject({ status: 403 });
    expect(onOrgSemLicenca).toHaveBeenCalledTimes(1);
  });
  it('ignores an unrelated 403', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res(403, { detail: 'nope' })));
    const onOrgSemLicenca = vi.fn();
    const client = createApiClient({ getBaseUrl: () => 'http://p', getAuthToken: async () => 't', onOrgSemLicenca });
    await expect(client.get('/api/x')).rejects.toMatchObject({ status: 403 });
    expect(onOrgSemLicenca).not.toHaveBeenCalled();
  });
});
