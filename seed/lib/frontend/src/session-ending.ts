/**
 * How a browser session ends — the ONE seed contract every product and core
 * routes through (2026-10-24 prod incident).
 *
 * Three endings, each with its own server reach:
 *
 *  - **Expiry** (inactivity timer, a refresh the server authoritatively refused,
 *    a dead-session verdict) — the user did not ask for it. It ends THIS tab's
 *    session state and sends the tab to the login prompt. It NEVER calls a
 *    server `/logout`: GoTrue `/logout` (any scope, `local` included) revokes the
 *    session's refresh tokens server-side, and that session is shared by every
 *    tab of the origin holding the same storage slot. One idle tab must never
 *    end the session for the tabs the user is actually working in.
 *  - **Voltar** (`leaveProduct`, the product's back-arrow to core; SSO session
 *    lifecycle S5) — the user asked to leave THIS product. GoTrue `/logout` with
 *    scope `local` deletes exactly this origin's session (minted for this product
 *    at SSO redemption) and NEVER the user's core session or other products'.
 *    Every tab of the product loses the session (shared slot); the others re-enter
 *    through core when looked at (`reentry.ts`, marker `left`).
 *  - **Explicit "Sair"** — the user asked to sign out. The server revocation runs
 *    first (it needs the bearer), then local state is cleared regardless of the
 *    outcome (unless `strict`, where a failed revocation is surfaced and nothing
 *    is cleared). Products revoke with scope `global` (every session, core too)
 *    and land on their own Landing (`product-landing.ts`).
 *
 * And one recovery that is NOT an ending: a refresh refused because ANOTHER tab
 * of the same origin already rotated the chain (`refresh_token_not_found`,
 * `refresh_token_already_used`, GoTrue reuse detection). The shared storage slot
 * then holds the winner's newer pair — adopt it (`adoptRotatedPair`), never
 * treat the refusal as a death.
 *
 * Scope note: storage is per ORIGIN. Core (`env.CORE_URL`) and each product
 * (its own origin) hold DIFFERENT GoTrue sessions — core's own login, and
 * a fresh session minted per SSO redemption (`products/core/backend/app/routers/
 * sso.py::_generate_session`). So "shared session" here means the tabs of one
 * origin; cross-origin there is nothing to adopt and nothing to coordinate.
 */
import { markLeaving, writeEntryMarker } from './reentry';

/** The access/refresh pair currently in an origin's shared session slot. */
export interface StoredSessionPair {
  accessToken: string | null;
  refreshToken: string | null;
}

/**
 * After the server AUTHORITATIVELY refused `presentedRefreshToken`: does the
 * shared slot now hold a DIFFERENT live pair (another tab rotated the chain while
 * this one was refreshing)? Returns the access token to adopt, or `null` when the
 * slot still holds the refused token (or nothing) — only then is the session dead.
 */
export function adoptRotatedPair(
  presentedRefreshToken: string | null,
  current: StoredSessionPair,
): string | null {
  if (!current.accessToken || !current.refreshToken) return null;
  if (current.refreshToken === presentedRefreshToken) return null;
  return current.accessToken;
}

function defaultNavigate(url: string): void {
  if (typeof window !== 'undefined') window.location.assign(url);
}

export interface EndSessionLocallyOptions {
  /**
   * Clear this tab's session state (in-memory store, and the origin's slot when
   * the session is genuinely over for every tab). Omit to leave storage alone —
   * e.g. a product tab that just leaves for core on inactivity.
   */
  clearLocal?: () => void;
  /** Where the tab goes next: the login prompt (or core). */
  redirectTo: string;
  /** Navigation seam (tests); defaults to `window.location.assign`. */
  navigate?: (url: string) => void;
}

/**
 * The ending the user did NOT ask for. Local only — never a server `/logout`.
 * See the module docstring for why (2026-10-24: an idle core tab's expiry
 * signed the user out of every product).
 */
export function endSessionLocally(opts: EndSessionLocallyOptions): void {
  opts.clearLocal?.();
  (opts.navigate ?? defaultNavigate)(opts.redirectTo);
}

export interface SignOutExplicitlyOptions {
  /** The server revocation (core `/api/auth/logout`, supabase-js `signOut`). */
  revoke: () => Promise<unknown>;
  /** Clear local session state — always, unless `strict` and `revoke` failed. */
  clearLocal: () => void;
  /** Rethrow a failed revocation instead of clearing (account switch at login). */
  strict?: boolean;
  /** Report a failed (non-strict) revocation; defaults to `console.error`. */
  onRevokeError?: (err: unknown) => void;
}

/**
 * The explicit "Sair" — the ONLY ending that revokes server-side. Revoke first
 * (it needs the bearer), then clear locally whatever the outcome, so a network
 * error never leaves the user signed in on this device.
 */
export async function signOutExplicitly(opts: SignOutExplicitlyOptions): Promise<void> {
  try {
    await opts.revoke();
  } catch (err) {
    if (opts.strict) throw err;
    (opts.onRevokeError ?? ((e: unknown) => {
      // eslint-disable-next-line no-console
      console.error('sign-out: server-side revocation failed; clearing local session anyway', e);
    }))(err);
  }
  opts.clearLocal();
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type LocalSignOutClient = { auth: { signOut: (opts: { scope: 'local' }) => Promise<any> } };

export interface LeaveProductOptions {
  /** This product's supabase-js client. `leaveProduct` itself picks scope `local`: the caller cannot widen it. */
  supabase: LocalSignOutClient;
  /** Leave for core (e.g. `location.href = env.CORE_APP_HOME`). Always runs, whatever the revoke did. */
  navigate: () => void;
  /** Drop the product's HttpOnly cookie session too (`dropProductCookieSession`); best-effort. */
  dropProductCookie?: () => Promise<unknown>;
  /** Report a failed revocation; defaults to `console.error`. */
  onRevokeError?: (err: unknown) => void;
}

/**
 * Voltar: end THIS product's session and go to core (SSO session lifecycle S5).
 *
 * Order matters: marker `left` + the per-tab "leaving" flag come first, so sibling
 * tabs that receive the SIGNED_OUT broadcast read `left` (re-enter through core),
 * while THIS tab's entry gate stays still instead of bouncing back in. The revoke
 * never strands the user: supabase-js removes the local session even when the
 * `/logout` call fails, and the navigation runs regardless.
 */
export async function leaveProduct(opts: LeaveProductOptions): Promise<void> {
  const report = opts.onRevokeError ?? ((e: unknown) => {
    // eslint-disable-next-line no-console
    console.error('voltar: revoking this product session failed; leaving anyway', e);
  });
  writeEntryMarker('left');
  markLeaving();
  try {
    const result = await opts.supabase.auth.signOut({ scope: 'local' });
    if (result?.error) report(result.error);
  } catch (err) {
    report(err);
  }
  if (opts.dropProductCookie) {
    try {
      await opts.dropProductCookie();
    } catch (err) {
      report(err);
    }
  }
  opts.navigate();
}

/**
 * Same-origin key carrying the most recent user interaction across tabs. The
 * inactivity timer reads the newest of this tab's and the shared value, so an
 * idle tab never expires while the user is active in another tab of the origin.
 */
export const SHARED_ACTIVITY_KEY = 'noctus:last-activity';

/** The newest interaction any tab of this origin recorded, or `0`. */
export function readSharedActivity(): number {
  try {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(SHARED_ACTIVITY_KEY) : null;
    const n = raw ? Number(raw) : 0;
    return Number.isFinite(n) ? n : 0;
  } catch {
    // Storage blocked (privacy mode): the timer degrades to per-tab activity.
    return 0;
  }
}

/** Record an interaction for every tab of this origin (best-effort). */
export function writeSharedActivity(at: number): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(SHARED_ACTIVITY_KEY, String(at));
  } catch {
    // Storage blocked: this tab's own timer still counts its interactions.
  }
}
