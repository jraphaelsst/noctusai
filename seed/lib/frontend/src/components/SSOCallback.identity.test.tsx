import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SSOCallback } from './SSOCallback';
import { getOrgPin, setOrgPin } from '../org-pin';
import { ACTIVITY_REFRESH_STORAGE_KEY } from '../design-system/useActivityRefresh';

const SESSION_A = { access_token: 'ta', user: { id: 'user-a', email: 'a@x.com' } };

function makeSupabase(session: unknown = null) {
  return {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session } }),
      setSession: vi.fn().mockResolvedValue({ error: null }),
      signOut: vi.fn().mockResolvedValue({ error: null }),
    },
  };
}

function core(body: unknown, status = 200) {
  return vi.fn(async (url: string, _init?: RequestInit) => {
    if (String(url).endsWith('/api/me/access')) {
      return { ok: true, status: 200, headers: new Headers(), json: async () => ({ has_access: true }) };
    }
    if (String(url).endsWith('/api/auth/logout')) {
      return { ok: true, status: 204, headers: new Headers(), json: async () => ({}) };
    }
    return { ok: status < 400, status, headers: new Headers(), json: async () => body };
  });
}

/** An unsigned JWT-shaped token carrying `claims` (only the payload is read client-side). */
function jwt(claims: Record<string, unknown>): string {
  const b64 = (o: unknown) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64(claims)}.sig`;
}

const B = { access_token: 'tb', refresh_token: 'rb', user_id: 'user-b', email: 'b@x.com' };

function mount(supabase: ReturnType<typeof makeSupabase>, entry = '/sso?token=abc', extra: object = {}, strict = false) {
  const tree = (
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route
          path="/sso"
          element={<SSOCallback supabase={supabase} coreApiUrl="http://core" apiUrl="http://prod" productSlug="demo" {...extra} />}
        />
        <Route path="/" element={<div>home</div>} />
      </Routes>
    </MemoryRouter>
  );
  return render(tree);
}

const redeemCalls = (f: ReturnType<typeof core>) =>
  f.mock.calls.filter((c) => String(c[0]).endsWith('/api/sso/session'));

describe('SSOCallback identity handling', () => {
  let fetchMock: ReturnType<typeof core>;
  let store: Map<string, string>;
  beforeEach(() => {
    store = new Map();
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    });
    window.history.replaceState({}, '', '/sso?token=abc');
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    setOrgPin(null);
  });

  it('same user: redeems, setSession, no interstitial', async () => {
    fetchMock = core({ ...B, user_id: 'user-a', email: 'a@x.com' });
    vi.stubGlobal('fetch', fetchMock);
    const sb = makeSupabase(SESSION_A);
    const { findByText, queryByText } = mount(sb);
    expect(await findByText('home')).toBeTruthy();
    expect(redeemCalls(fetchMock)).toHaveLength(1);
    expect(sb.auth.setSession).toHaveBeenCalledWith({ access_token: 'tb', refresh_token: 'rb' });
    expect(queryByText(/Entrar como/)).toBeNull();
  });

  it('same GoTrue session re-issued by core: KEEPS the local (rotated) session, never rolls it back', async () => {
    // Core's SSO cache re-issues the pair it handed this origin minutes ago; the
    // local slot already holds a ROTATED refresh token for that same session.
    // Adopting the re-issued pair would put a spent refresh token back in the
    // shared slot -> next refresh = reuse -> GoTrue revokes the session for every tab.
    const reissued = { access_token: jwt({ sub: 'user-a', session_id: 'sess-1' }), refresh_token: 'r0-spent',
      user_id: 'user-a', email: 'a@x.com' };
    fetchMock = core(reissued);
    vi.stubGlobal('fetch', fetchMock);
    const sb = makeSupabase({ access_token: jwt({ sub: 'user-a', session_id: 'sess-1' }), refresh_token: 'r1-live',
      user: { id: 'user-a', email: 'a@x.com' } });
    const { findByText } = mount(sb);
    expect(await findByText('home')).toBeTruthy();
    expect(redeemCalls(fetchMock)).toHaveLength(1);
    expect(sb.auth.setSession).not.toHaveBeenCalled();
    expect(sb.auth.signOut).not.toHaveBeenCalled();
  });

  it('same user, a DIFFERENT GoTrue session: adopts the fresh pair', async () => {
    const fresh = { access_token: jwt({ sub: 'user-a', session_id: 'sess-2' }), refresh_token: 'r-new',
      user_id: 'user-a', email: 'a@x.com' };
    fetchMock = core(fresh);
    vi.stubGlobal('fetch', fetchMock);
    const sb = makeSupabase({ access_token: jwt({ sub: 'user-a', session_id: 'sess-1' }),
      user: { id: 'user-a', email: 'a@x.com' } });
    const { findByText } = mount(sb);
    expect(await findByText('home')).toBeTruthy();
    expect(sb.auth.setSession).toHaveBeenCalledWith({ access_token: fresh.access_token, refresh_token: 'r-new' });
  });

  it('different user: interstitial; confirm purges identity then sets B', async () => {
    fetchMock = core(B);
    vi.stubGlobal('fetch', fetchMock);
    localStorage.setItem(ACTIVITY_REFRESH_STORAGE_KEY, '123');
    setOrgPin('org-of-a');
    const onIdentityChange = vi.fn();
    const sb = makeSupabase(SESSION_A);
    const { findByText, getByText } = mount(sb, '/sso?token=abc', { onIdentityChange });

    expect(await findByText('Entrar como b@x.com?')).toBeTruthy();
    expect(getByText(/conectado como a@x.com/)).toBeTruthy();
    expect(sb.auth.setSession).not.toHaveBeenCalled();
    expect(sb.auth.signOut).not.toHaveBeenCalled();

    fireEvent.click(getByText('Entrar como b@x.com'));
    expect(await findByText('home')).toBeTruthy();
    expect(sb.auth.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(onIdentityChange).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(ACTIVITY_REFRESH_STORAGE_KEY)).toBeNull();
    expect(getOrgPin()).toBeNull();
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith('/api/auth/logout'))).toBe(true);
    expect(sb.auth.setSession).toHaveBeenCalledWith({ access_token: 'tb', refresh_token: 'rb' });
    expect(redeemCalls(fetchMock)).toHaveLength(1);
  });

  it('different user: cancel keeps A and never sets the redeemed tokens', async () => {
    fetchMock = core(B);
    vi.stubGlobal('fetch', fetchMock);
    const sb = makeSupabase(SESSION_A);
    const { findByText, getByText } = mount(sb);
    await findByText('Entrar como b@x.com?');
    fireEvent.click(getByText('Continuar como a@x.com'));
    expect(await findByText('home')).toBeTruthy();
    expect(sb.auth.setSession).not.toHaveBeenCalled();
    expect(sb.auth.signOut).not.toHaveBeenCalled();
  });

  it('redeem failure with a session: error screen naming A, no signOut', async () => {
    fetchMock = core({ detail: 'token invalido' }, 401);
    vi.stubGlobal('fetch', fetchMock);
    const sb = makeSupabase(SESSION_A);
    const { findByText, getByText } = mount(sb);
    expect(await findByText(/conectado como a@x.com/)).toBeTruthy();
    expect(getByText('Entrar novamente pelo NoctusAI')).toBeTruthy();
    expect(sb.auth.signOut).not.toHaveBeenCalled();
    expect(sb.auth.setSession).not.toHaveBeenCalled();
    fireEvent.click(getByText('Continuar como a@x.com'));
    expect(await findByText('home')).toBeTruthy();
  });

  it('redeem failure with no session keeps the retry screen', async () => {
    fetchMock = core({ detail: 'token invalido' }, 401);
    vi.stubGlobal('fetch', fetchMock);
    const { findByText } = mount(makeSupabase(null));
    expect(await findByText('Tentar novamente')).toBeTruthy();
  });

  it('accepts #token= and strips it from the URL; sends product_slug', async () => {
    fetchMock = core({ ...B, user_id: 'user-a' });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sso#token=frag.tok');
    const sb = makeSupabase(SESSION_A);
    const { findByText } = mount(sb, '/sso#token=frag.tok');
    expect(await findByText('home')).toBeTruthy();
    expect(JSON.parse(String(redeemCalls(fetchMock)[0][1]?.body))).toEqual({ token: 'frag.tok', product_slug: 'demo' });
    expect(window.location.hash).not.toContain('token');
  });

  it('double mount (StrictMode) redeems exactly once', async () => {
    fetchMock = core({ ...B, user_id: 'user-a' });
    vi.stubGlobal('fetch', fetchMock);
    const sb = makeSupabase(SESSION_A);
    const { StrictMode } = await import('react');
    const { findByText } = render(
      <StrictMode>
        <MemoryRouter initialEntries={['/sso?token=abc']}>
          <Routes>
            <Route path="/sso" element={<SSOCallback supabase={sb} coreApiUrl="http://core" apiUrl="http://prod" productSlug="demo" />} />
            <Route path="/" element={<div>home</div>} />
          </Routes>
        </MemoryRouter>
      </StrictMode>,
    );
    expect(await findByText('home')).toBeTruthy();
    await waitFor(() => expect(redeemCalls(fetchMock)).toHaveLength(1));
  });
});
