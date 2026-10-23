/**
 * Refresh-token ownership guard for the browser's shared supabase-js session.
 *
 * Every tab of one origin shares ONE localStorage slot (`sb-<ref>-auth-token`)
 * holding ONE GoTrue refresh-token chain, and supabase-js (>= 2.10x) refreshes
 * it LOCKLESS across tabs. When tab B presents a refresh token that tab A has
 * already rotated (a frozen/background tab, a laptop waking up), GoTrue answers
 * `400 refresh_token_already_used` -- about B's SUPERSEDED token, not about the
 * session. supabase-js then runs `_removeSession()`, which deletes the slot
 * that now holds A's LIVE pair: every tab of the product is signed out and the
 * user lands on the public Landing (prod 2026-10-23 17:22, owner report).
 *
 * The guard is two public supabase-js seams sharing one fact -- the refresh
 * token THIS client last presented and had refused:
 *
 *  - `fetch` (`global.fetch`): records the `refresh_token` of a
 *    `/token?grant_type=refresh_token` request that GoTrue answered with a 4xx.
 *  - `storage` (`auth.storage`): a removal of the session slot that follows
 *    such a refusal is honoured ONLY when the slot still holds the refused
 *    token. If the slot holds a different refresh token, another holder rotated
 *    the chain after we read it -- the session is alive -- so the removal is
 *    refused (logged), and the `SIGNED_OUT` that supabase-js emits is resolved
 *    by `useSupabaseAuthInit`, which re-reads the slot and keeps the user.
 *
 * Every other removal (an explicit sign-out, a truly dead chain whose refused
 * token is still the stored one, the `-user` / `-code-verifier` side keys) is
 * honoured unchanged. Nothing here talks to GoTrue.
 */

/** The `refresh_token` inside a stored supabase-js session value, or `null`. */
function refreshTokenOf(raw: string | null): string | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    const token = value?.refresh_token;
    return typeof token === 'string' && token ? token : null;
  } catch {
    return null; // not a session value (side keys hold other shapes)
  }
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

/** The refresh token a GoTrue refresh request presents, or `null`. */
function presentedRefreshToken(input: RequestInfo | URL, init?: RequestInit): string | null {
  if (!/\/token\?grant_type=refresh_token\b/.test(requestUrl(input))) return null;
  if (typeof init?.body !== 'string') return null;
  try {
    const token = JSON.parse(init.body)?.refresh_token;
    return typeof token === 'string' && token ? token : null;
  } catch {
    return null;
  }
}

/** Minimal synchronous storage the guard wraps (`window.localStorage`). */
export interface GuardableStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface RefreshOwnershipGuard {
  fetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
  storage: GuardableStorage;
}

export function createRefreshOwnershipGuard(
  baseFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
  baseStorage: GuardableStorage,
): RefreshOwnershipGuard {
  // The refresh token this client presented and GoTrue refused, until the next
  // removal decision (one-shot) or the next refresh answer.
  let refusedRefreshToken: string | null = null;

  const guardedFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const presented = presentedRefreshToken(input, init);
    const response = await baseFetch(input, init);
    if (presented) {
      refusedRefreshToken = response.status >= 400 && response.status < 500 ? presented : null;
    }
    return response;
  };

  const storage: GuardableStorage = {
    getItem: (key) => baseStorage.getItem(key),
    setItem: (key, value) => baseStorage.setItem(key, value),
    removeItem: (key) => {
      const refused = refusedRefreshToken;
      const stored = refreshTokenOf(baseStorage.getItem(key));
      if (refused && stored) {
        refusedRefreshToken = null;
        if (stored !== refused) {
          // eslint-disable-next-line no-console
          console.warn(
            '[auth] refresh refused for a superseded token; another tab holds the rotated session -- keeping it',
          );
          return;
        }
      }
      baseStorage.removeItem(key);
    },
  };

  return { fetch: guardedFetch, storage };
}
