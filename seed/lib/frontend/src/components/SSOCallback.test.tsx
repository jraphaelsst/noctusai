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
