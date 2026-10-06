import { render, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SSOCallback } from './SSOCallback';

function makeSupabase() {
  return {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      refreshSession: vi.fn(),
      setSession: vi.fn().mockResolvedValue({ error: null }),
    },
  };
}

function mount(supabase: ReturnType<typeof makeSupabase>, productSlug?: string) {
  return render(
    <MemoryRouter initialEntries={['/sso?token=abc.def.ghi']}>
      <Routes>
        <Route
          path="/sso"
          element={<SSOCallback supabase={supabase} coreApiUrl="http://core" productSlug={productSlug} />}
        />
        <Route path="/" element={<div>home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SSOCallback token hygiene', () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => ({ access_token: 'a', refresh_token: 'r' }),
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sso?token=abc.def.ghi');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('strips ?token= from the address bar immediately', async () => {
    const spy = vi.spyOn(window.history, 'replaceState');
    mount(makeSupabase());
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(window.location.search).not.toContain('token');
    spy.mockRestore();
  });

  it('still redeems the token and sends the product slug', async () => {
    const supabase = makeSupabase();
    mount(supabase, 'erp');
    await waitFor(() => expect(supabase.auth.setSession).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ token: 'abc.def.ghi', product_slug: 'erp' });
  });
});

describe('SSOCallback license gate', () => {
  const fetchMock = vi.fn();
  afterEach(() => vi.unstubAllGlobals());

  function supabaseWithToken() {
    const sb = makeSupabase();
    // first call (existing-session probe) → none; after setSession → token
    sb.auth.getSession = vi.fn()
      .mockResolvedValueOnce({ data: { session: null } })
      .mockResolvedValue({ data: { session: { access_token: 'tok' } } });
    return sb;
  }

  function stub(hasAccess: boolean) {
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).endsWith('/api/me/access')) {
        return { ok: true, status: 200, headers: new Headers(), json: async () => ({ has_access: hasAccess }) };
      }
      return { ok: true, status: 200, headers: new Headers(), json: async () => ({ access_token: 'a', refresh_token: 'r' }) };
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sso?token=abc.def.ghi');
  }

  function mountGate(sb: ReturnType<typeof makeSupabase>) {
    return render(
      <MemoryRouter initialEntries={['/sso?token=abc.def.ghi']}>
        <Routes>
          <Route path="/sso" element={<SSOCallback supabase={sb} coreApiUrl="http://core" apiUrl="http://prod" />} />
          <Route path="/" element={<div>home</div>} />
          <Route path="/sem-acesso" element={<div>sem acesso</div>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('goes to /sem-acesso when the org has no license', async () => {
    stub(false);
    const { findByText } = mountGate(supabaseWithToken());
    expect(await findByText('sem acesso')).toBeTruthy();
  });

  it('goes home when the org is licensed', async () => {
    stub(true);
    const { findByText } = mountGate(supabaseWithToken());
    expect(await findByText('home')).toBeTruthy();
    expect(fetchMock.mock.calls.some((c) => c[0] === 'http://prod/api/me/access')).toBe(true);
  });
});
