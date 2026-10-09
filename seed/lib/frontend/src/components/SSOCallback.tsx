/**
 * Shared SSO Callback component.
 *
 * Handles the SSO flow that is identical across product frontends:
 * 1. ALWAYS redeem the core token via core's /api/sso/session (never decode
 *    the JWT client-side; core's response `user_id` is the only identity input)
 * 2. No local session, or same user -> setSession(fresh tokens)
 * 3. A DIFFERENT user than the one signed in on this origin -> ask before
 *    replacing (interstitial), then purge the previous identity
 * 4. Redeem failure while a session exists -> never silently sign out
 *    (logout-CSRF) and never silently continue: name the current user
 *
 * Products render this component on their `/sso` route, passing in
 * their Supabase client instance and environment-specific URLs. The token may
 * arrive as a URL fragment (`/sso#token=`) or query (`/sso?token=`).
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { checkProductAccess, SEM_ACESSO_PATH } from '../access';
import { env } from '../env';
import { clearLocalIdentity, dropProductCookieSession } from '../identity';
// Use a loose type so products with custom schema generics can pass their client
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySupabaseClient = { auth: any };

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SSOCallbackProps {
  /** The product's Supabase client instance. */
  supabase: AnySupabaseClient;
  /** Core backend API URL (e.g. http://localhost:8000). */
  coreApiUrl?: string;
  /** Core frontend URL for "back" links (e.g. http://localhost:5173). */
  coreUrl?: string;
  /** SSO endpoint path on the core backend (default: /api/sso/session). */
  ssoEndpoint?: string;
  /** Where to navigate after successful auth (default: /). */
  redirectPath?: string;
  /** This product's slug — sent so core can bind the token to its audience. */
  productSlug?: string;
  /**
   * Product backend base URL for the license-gate check
   * (`GET /api/me/access`, default `env.BACKEND_API_URL`).
   */
  apiUrl?: string;
  /**
   * Called when the signed-in identity is being REPLACED (account switch),
   * before the new session is set. The framework wires this to
   * `queryClient.clear()` so no previous-user data survives.
   */
  onIdentityChange?: () => void | Promise<void>;
}

type SSOState =
  | { status: 'loading'; message: string; email?: string }
  | { status: 'rate_limited'; retryIn: number }
  | { status: 'confirm_switch'; currentEmail: string; newEmail: string }
  | { status: 'error'; message: string; currentEmail?: string };

interface RedeemedSession {
  access_token: string;
  refresh_token: string;
  user_id?: string;
  email?: string;
}

type RedeemResult = { kind: 'ok'; session: RedeemedSession } | { kind: 'rate_limited'; retryAfter: number };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Read the SSO token from `#token=` (preferred) or `?token=`. */
function readTokenFromLocation(search: URLSearchParams): string | null {
  if (typeof window !== 'undefined') {
    const fromHash = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('token');
    if (fromHash) return fromHash;
  }
  return search.get('token');
}

/** Strip the bearer token from BOTH the fragment and the query, in history too. */
function stripTokenFromLocation(): void {
  if (typeof window === 'undefined') return;
  const clean = new URL(window.location.href);
  clean.searchParams.delete('token');
  const hash = new URLSearchParams(clean.hash.replace(/^#/, ''));
  hash.delete('token');
  const hashStr = hash.toString();
  window.history.replaceState(
    window.history.state,
    '',
    clean.pathname + clean.search + (hashStr ? `#${hashStr}` : ''),
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SSOCallback({
  supabase,
  coreApiUrl = 'http://localhost:8000',
  coreUrl = 'http://localhost:5173',
  ssoEndpoint = '/api/sso/session',
  redirectPath = '/',
  productSlug,
  apiUrl,
  onIdentityChange,
}: SSOCallbackProps) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [state, setState] = useState<SSOState>({
    status: 'loading',
    message: 'Verificando sessao...',
  });
  const cancelledRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // The token is read once and kept in memory (the URL is stripped at once).
  const tokenRef = useRef<string | null>(null);
  // Tokens are single-use: a remount (StrictMode double-effect) or an
  // interstitial re-render must reuse the one redemption, never fire a second
  // one that core would refuse (401). Dropped only when the redemption did
  // not consume the token (rate limit / failure) so a retry can re-run.
  const redeemedRef = useRef<Map<string, Promise<RedeemResult>>>(new Map());
  // The local user at the time the flow started (for failure/cancel screens).
  const currentRef = useRef<{ id: string; email: string } | null>(null);
  const handleSSORef = useRef<(token: string) => Promise<void>>(async () => {});

  const clearTimer = useCallback(() => {
    if (timerRef.current != null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const redeemOnce = useCallback(
    (token: string): Promise<RedeemResult> => {
      const existing = redeemedRef.current.get(token);
      if (existing) return existing;
      const p = (async (): Promise<RedeemResult> => {
        const response = await fetch(`${coreApiUrl}${ssoEndpoint}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(productSlug ? { token, product_slug: productSlug } : { token }),
        });

        if (response.status === 429) {
          return { kind: 'rate_limited', retryAfter: parseInt(response.headers.get('Retry-After') || '60', 10) };
        }
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.detail || data.error?.message || 'Erro ao validar token SSO');
        }
        const session = (await response.json()) as RedeemedSession;
        return { kind: 'ok', session };
      })();
      redeemedRef.current.set(token, p);
      p.then(
        (r) => { if (r.kind !== 'ok') redeemedRef.current.delete(token); },
        () => { redeemedRef.current.delete(token); },
      );
      return p;
    },
    [coreApiUrl, ssoEndpoint, productSlug],
  );

  const startCountdown = useCallback(
    (seconds: number, token: string) => {
      clearTimer();
      let remaining = seconds;
      setState({ status: 'rate_limited', retryIn: remaining });

      timerRef.current = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          clearTimer();
          void handleSSORef.current(token);
        } else {
          setState({ status: 'rate_limited', retryIn: remaining });
        }
      }, 1000);
    },
    [clearTimer],
  );

  /**
   * License gate (Round 2): once a session exists, ask the product whether the
   * user's org holds its license — no license => `/sem-acesso`, not the app.
   * A missing token skips the check (the server re-enforces on every call).
   */
  const finish = useCallback(async () => {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const token: string | null = session?.access_token ?? null;
    const ok = token
      ? await checkProductAccess({ baseUrl: apiUrl ?? env.BACKEND_API_URL, token })
      : true;
    if (cancelledRef.current) return;
    navigate(ok ? redirectPath : SEM_ACESSO_PATH, { replace: true });
  }, [supabase, apiUrl, navigate, redirectPath]);

  const adopt = useCallback(
    async (session: RedeemedSession) => {
      const { error } = await supabase.auth.setSession({
        access_token: session.access_token,
        refresh_token: session.refresh_token,
      });
      if (error) throw new Error(error.message);
      if (cancelledRef.current) return;
      await finish();
    },
    [supabase, finish],
  );

  const handleSSO = useCallback(
    async (token: string) => {
      if (cancelledRef.current) return;

      try {
        setState({ status: 'loading', message: 'Verificando sessao...' });
        const {
          data: { session: local },
        } = await supabase.auth.getSession();
        if (cancelledRef.current) return;
        currentRef.current = local?.user
          ? { id: local.user.id, email: local.user.email ?? '' }
          : null;

        setState({ status: 'loading', message: 'Autenticando via NoctusAI...' });
        // ALWAYS redeem: identity is decided only on core's response.
        const result = await redeemOnce(token);
        if (cancelledRef.current) return;
        if (result.kind === 'rate_limited') {
          startCountdown(result.retryAfter, token);
          return;
        }
        const incoming = result.session;
        const current = currentRef.current;

        if (current && incoming.user_id && incoming.user_id !== current.id) {
          // Different account: never replace silently.
          setState({
            status: 'confirm_switch',
            currentEmail: current.email,
            newEmail: incoming.email ?? '',
          });
          return;
        }

        setState({ status: 'loading', message: 'Autenticando via NoctusAI...', email: incoming.email });
        await adopt(incoming);
      } catch (err: any) {
        if (!cancelledRef.current) {
          setState({
            status: 'error',
            message: err.message || 'Erro ao processar login SSO.',
            currentEmail: currentRef.current?.email,
          });
        }
      }
    },
    [supabase, redeemOnce, startCountdown, adopt],
  );
  handleSSORef.current = handleSSO;

  const confirmSwitch = useCallback(async () => {
    const token = tokenRef.current;
    if (!token) return;
    try {
      setState({ status: 'loading', message: 'Trocando de conta...' });
      const result = await redeemOnce(token);
      if (result.kind !== 'ok') return;
      await supabase.auth.signOut({ scope: 'local' });
      await onIdentityChange?.();
      clearLocalIdentity();
      await dropProductCookieSession();
      await adopt(result.session);
    } catch (err: any) {
      if (!cancelledRef.current) {
        setState({
          status: 'error',
          message: err.message || 'Erro ao processar login SSO.',
        });
      }
    }
  }, [supabase, redeemOnce, onIdentityChange, adopt]);

  const keepCurrent = useCallback(async () => {
    // The redeemed tokens for the other account are discarded (single-use).
    setState({ status: 'loading', message: 'Continuando...' });
    await finish();
  }, [finish]);

  useEffect(() => {
    const token = tokenRef.current ?? readTokenFromLocation(searchParams);
    if (!token) {
      setState({ status: 'error', message: 'Token SSO nao encontrado na URL.' });
      return;
    }
    tokenRef.current = token;

    // The token is a bearer credential: strip it from the address bar (and
    // history) immediately so it cannot leak via history/referrer/screenshots.
    // The in-memory copy above is all the flow needs.
    stripTokenFromLocation();

    cancelledRef.current = false;
    void handleSSO(token);

    return () => {
      cancelledRef.current = true;
      clearTimer();
    };
  }, [searchParams, handleSSO, clearTimer]);

  // --- Account switch interstitial ---
  if (state.status === 'confirm_switch') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="max-w-md w-full bg-card rounded-lg shadow p-8 text-center space-y-4">
          <h1 className="text-xl font-semibold">
            Entrar como {state.newEmail || 'outra conta'}?
          </h1>
          <p className="text-muted-foreground">
            Voce esta conectado como {state.currentEmail || 'outra conta'}.
          </p>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => void confirmSwitch()}
              className="px-4 py-2 bg-primary text-primary-foreground rounded hover:opacity-90 transition"
            >
              Entrar como {state.newEmail || 'a nova conta'}
            </button>
            <button
              onClick={() => void keepCurrent()}
              className="px-4 py-2 text-muted-foreground hover:text-foreground transition"
            >
              Continuar como {state.currentEmail || 'a conta atual'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // --- Rate limited ---
  if (state.status === 'rate_limited') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="max-w-md w-full bg-card rounded-lg shadow p-8 text-center space-y-4">
          <div className="text-4xl">&#9202;</div>
          <h1 className="text-xl font-semibold">Aguardando limite de requisicoes</h1>
          <p className="text-muted-foreground">Tentando novamente em:</p>
          <div className="text-3xl font-bold text-primary">{state.retryIn}s</div>
          <div className="w-full bg-muted rounded-full h-2">
            <div
              className="bg-primary h-2 rounded-full transition-all duration-1000"
              style={{ width: `${Math.max(0, ((60 - state.retryIn) / 60) * 100)}%` }}
            />
          </div>
          <a
            href={coreUrl}
            className="inline-block mt-2 text-sm text-muted-foreground hover:text-foreground underline"
          >
            Voltar ao NoctusAI
          </a>
        </div>
      </div>
    );
  }

  // --- Error ---
  if (state.status === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="max-w-md w-full bg-card rounded-lg shadow p-8 text-center space-y-4">
          <div className="text-destructive text-4xl">!</div>
          <h1 className="text-xl font-semibold">Erro no login SSO</h1>
          <p className="text-muted-foreground">{state.message}</p>
          {state.currentEmail ? (
            <>
              <p className="text-sm text-muted-foreground">Voce esta conectado como {state.currentEmail}.</p>
              <div className="flex flex-col gap-2">
                <button
                  onClick={() => void keepCurrent()}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded hover:opacity-90 transition"
                >
                  Continuar como {state.currentEmail}
                </button>
                <a
                  href={coreUrl}
                  className="inline-block px-4 py-2 text-muted-foreground hover:text-foreground transition"
                >
                  Entrar novamente pelo NoctusAI
                </a>
              </div>
            </>
          ) : (
            <div className="flex flex-col gap-2">
              <button
                onClick={() => {
                  if (tokenRef.current) void handleSSO(tokenRef.current);
                }}
                className="px-4 py-2 bg-primary text-primary-foreground rounded hover:opacity-90 transition"
              >
                Tentar novamente
              </button>
              <a
                href={coreUrl}
                className="inline-block px-4 py-2 text-muted-foreground hover:text-foreground transition"
              >
                Voltar ao NoctusAI
              </a>
            </div>
          )}
        </div>
      </div>
    );
  }

  // --- Loading ---
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-4">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto" />
        <p className="text-muted-foreground">{state.message}</p>
        {state.email && <p className="text-xs text-muted-foreground">{state.email}</p>}
      </div>
    </div>
  );
}
