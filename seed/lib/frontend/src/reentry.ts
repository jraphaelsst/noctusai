/**
 * Product entry and silent re-entry through core (SSO session lifecycle, slice S4).
 *
 * A product never collects credentials: a visitor without a session is sent to core's central login
 * (`CORE_URL/login?produto=<slug>&next=<path>&prompt=none|login`, contract
 * `products/core/CONTRACTS/sso-entry.md`). Core either launches the product at once (it has a session),
 * shows its login form, or — for `prompt=none` with no core session — bounces back with `#sso=login_required`.
 *
 * Everything here is framework-free and takes its browser dependencies as an argument (storage, document,
 * Web Locks, clock, navigate) so each rule of the decision table is testable without patching globals.
 *
 * Marker `noctus:entry` (product-origin localStorage): `active` (redeemed here) | `left` (Voltar, S5) |
 * `signed-out` (Sair). It only decides whether a visit to `/` bounces; it grants nothing.
 */

export type EntryMarker = 'active' | 'left' | 'signed-out';
export type CorePrompt = 'none' | 'login';

export const ENTRY_MARKER_KEY = 'noctus:entry';
export const REENTRY_INFLIGHT_KEY = 'noctus:reentry-inflight';
/** Per-tab (sessionStorage): timestamps of the core round trips not yet followed by a redeem. */
export const REENTRY_TRIPS_KEY = 'noctus:reentry-trips';
export const INFLIGHT_TTL_MS = 60_000;
export const LOOP_MAX_TRIPS = 3;
export const LOOP_WINDOW_MS = 2 * 60_000;
/** The fragment core appends when `prompt=none` finds no core session. */
export const LOGIN_REQUIRED_FRAGMENT = 'sso=login_required';

// --- Marker ------------------------------------------------------------------------------------

export function readEntryMarker(storage: Pick<Storage, 'getItem'> = localStorage): EntryMarker | null {
  try {
    const v = storage.getItem(ENTRY_MARKER_KEY);
    return v === 'active' || v === 'left' || v === 'signed-out' ? v : null;
  } catch {
    return null;
  }
}

export function writeEntryMarker(marker: EntryMarker, storage: Pick<Storage, 'setItem'> = localStorage): void {
  try {
    storage.setItem(ENTRY_MARKER_KEY, marker);
  } catch {
    /* storage blocked: the marker is an optimisation (no bounce on `/`), never a requirement */
  }
}

// --- "This tab lost its session" (set by auth.ts once a SIGNED_OUT is confirmed) ----------------

let sessionLost = false;

export function markSessionLost(): void {
  sessionLost = true;
}
export function clearSessionLost(): void {
  sessionLost = false;
}
export function wasSessionLost(): boolean {
  return sessionLost;
}

// --- "This tab is leaving for core" (set by session-ending.ts `leaveProduct`, i.e. Voltar) -------

let leaving = false;

/**
 * Voltar revokes this tab's session and then navigates to core. The revoke makes supabase-js emit
 * SIGNED_OUT in THIS tab too, which mounts the entry gate; without this flag the gate would read marker
 * `left` and send the tab to core's login, which launches the product again (Voltar bounced back in).
 * Sibling tabs never see it (module state is per tab), so they still re-enter as the decision table says.
 */
export function markLeaving(): void {
  leaving = true;
}
export function clearLeaving(): void {
  leaving = false;
}
export function isLeaving(): boolean {
  return leaving;
}

// --- URLs --------------------------------------------------------------------------------------

/** Path-only ("/x"); never "//host", a scheme, a backslash or a control char. Else `null`. */
export function sanitizeNextPath(raw: string | null | undefined): string | null {
  if (!raw) return null;
  // eslint-disable-next-line no-control-regex
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\') || /[\u0000-\u001f\u007f]/.test(raw)) {
    return null;
  }
  return raw;
}

export interface CoreEntryUrlOptions {
  coreUrl: string;
  slug: string;
  /** Post-entry path (`pathname + search`). `/` and anything non-path are omitted. */
  next?: string | null;
  /** Omitted from the URL when `undefined` (core defaults to `login`). */
  prompt?: CorePrompt;
  /** Core route: the central login (default) or the central password reset. */
  route?: '/login' | '/esqueci-senha';
}

export function buildCoreEntryUrl({ coreUrl, slug, next, prompt, route = '/login' }: CoreEntryUrlOptions): string {
  const q = new URLSearchParams({ produto: slug });
  const safe = sanitizeNextPath(next);
  if (safe && safe !== '/') q.set('next', safe);
  if (prompt) q.set('prompt', prompt);
  return `${coreUrl.replace(/\/+$/, '')}${route}?${q.toString()}`;
}

// --- Decision table ----------------------------------------------------------------------------

export type EntryDecision =
  /** Show the product's public landing (strangers and crawlers never bounce). */
  | { kind: 'landing' }
  /** Go to core now / once the tab is visible. */
  | { kind: 'core'; prompt: CorePrompt }
  /** `signed-out` on a non-root path: land on the product's `/`. */
  | { kind: 'product-landing' };

export interface DecideEntryInput {
  /** `lost`: this tab HAD a session and a SIGNED_OUT was confirmed; `fresh`: a plain page load. */
  phase: 'fresh' | 'lost';
  pathname: string;
  marker: EntryMarker | null;
}

/** The S4 decision table (design record D). Only called when the tab has no session. */
export function decideEntry({ phase, pathname, marker }: DecideEntryInput): EntryDecision {
  const atRoot = pathname === '/';
  if (phase === 'lost' && marker === 'signed-out') {
    return atRoot ? { kind: 'landing' } : { kind: 'product-landing' };
  }
  if (!atRoot) return { kind: 'core', prompt: 'login' };
  if (marker === 'left' || marker === 'active') return { kind: 'core', prompt: phase === 'lost' ? 'login' : 'none' };
  return { kind: 'landing' };
}

/** `true` when the URL fragment is core's "no session" bounce. */
export function isLoginRequiredBounce(hash: string): boolean {
  return new URLSearchParams(hash.replace(/^#/, '')).get('sso') === 'login_required';
}

/** Core said "no session": remember it (so `/` stays the Landing) and close the round trip. */
export function applyLoginRequiredBounce(
  hash: string,
  deps: { local?: Storage; session?: Storage } = {},
): boolean {
  if (!isLoginRequiredBounce(hash)) return false;
  writeEntryMarker('signed-out', deps.local ?? localStorage);
  clearInflight(deps.local ?? localStorage);
  return true;
}

// --- Loop guard (per tab) ----------------------------------------------------------------------

function readTrips(session: Pick<Storage, 'getItem'>, now: number): number[] {
  try {
    const parsed = JSON.parse(session.getItem(REENTRY_TRIPS_KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((t): t is number => typeof t === 'number' && now - t < LOOP_WINDOW_MS) : [];
  } catch {
    return [];
  }
}

export function isLoopTripped(session: Pick<Storage, 'getItem'> = sessionStorage, now = Date.now()): boolean {
  return readTrips(session, now).length >= LOOP_MAX_TRIPS;
}

function recordTrip(session: Pick<Storage, 'getItem' | 'setItem'>, now: number): void {
  try {
    session.setItem(REENTRY_TRIPS_KEY, JSON.stringify([...readTrips(session, now), now]));
  } catch {
    /* no storage = no counter; the inflight stamp and the lock still bound the damage */
  }
}

/** A successful redeem (or an explicit "Entrar" click) closes the loop window. */
export function clearReentryTrips(session: Pick<Storage, 'removeItem'> = sessionStorage): void {
  try {
    session.removeItem(REENTRY_TRIPS_KEY);
  } catch {
    /* nothing to clear */
  }
}

// --- Multi-tab ---------------------------------------------------------------------------------

function inflightRemainingMs(local: Pick<Storage, 'getItem'>, now: number): number {
  try {
    const at = Number(local.getItem(REENTRY_INFLIGHT_KEY));
    if (!Number.isFinite(at) || at <= 0) return 0;
    return Math.max(0, INFLIGHT_TTL_MS - (now - at));
  } catch {
    return 0;
  }
}

export function clearInflight(local: Pick<Storage, 'removeItem'> = localStorage): void {
  try {
    local.removeItem(REENTRY_INFLIGHT_KEY);
  } catch {
    /* nothing to clear */
  }
}

/** SSOCallback success: the round trip ended in a session. */
export function recordSuccessfulRedeem(): void {
  writeEntryMarker('active');
  clearInflight();
  clearReentryTrips();
  clearSessionLost();
}

/** Resolves once the tab is visible (immediately if it already is). `cancel()` abandons the wait. */
export function whenVisible(doc: Pick<Document, 'visibilityState' | 'addEventListener' | 'removeEventListener'> = document) {
  let cancel = () => {};
  const promise = new Promise<boolean>((resolve) => {
    if (doc.visibilityState === 'visible') return resolve(true);
    const onChange = () => {
      if (doc.visibilityState !== 'visible') return;
      doc.removeEventListener('visibilitychange', onChange);
      resolve(true);
    };
    cancel = () => {
      doc.removeEventListener('visibilitychange', onChange);
      resolve(false);
    };
    doc.addEventListener('visibilitychange', onChange);
  });
  return { promise, cancel: () => cancel() };
}

export type EnterCoreOutcome =
  | { status: 'navigated'; url: string }
  /** A sibling window is already on its way (lock held or a fresh inflight stamp): adopt its SIGNED_IN. */
  | { status: 'deferred'; retryInMs: number }
  /** 3 round trips in 2 min without a redeem: stop, the visitor clicks "Entrar". */
  | { status: 'loop' };

export interface EnterCoreDeps {
  doc?: Pick<Document, 'visibilityState'>;
  local?: Storage;
  session?: Storage;
  locks?: Pick<LockManager, 'request'> | null;
  now?: () => number;
  navigate: (url: string) => void;
}

/**
 * ONE navigation to core for this product, no matter how many tabs ask. Call it only once the tab is
 * visible (see `whenVisible`); a hidden tab that gets here anyway does nothing.
 */
export async function enterViaCore(url: string, slug: string, deps: EnterCoreDeps): Promise<EnterCoreOutcome | { status: 'hidden' }> {
  const doc = deps.doc ?? document;
  const local = deps.local ?? localStorage;
  const session = deps.session ?? sessionStorage;
  const now = deps.now ?? Date.now;
  const locks = deps.locks === undefined ? (typeof navigator !== 'undefined' ? (navigator.locks ?? null) : null) : deps.locks;

  if (doc.visibilityState !== 'visible') return { status: 'hidden' };

  const attempt = (): EnterCoreOutcome => {
    const t = now();
    const remaining = inflightRemainingMs(local, t);
    if (remaining > 0) return { status: 'deferred', retryInMs: remaining };
    if (isLoopTripped(session, t)) return { status: 'loop' };
    try {
      local.setItem(REENTRY_INFLIGHT_KEY, String(t));
    } catch {
      /* no storage: the lock alone serialises same-browser tabs */
    }
    recordTrip(session, t);
    deps.navigate(url);
    return { status: 'navigated', url };
  };

  if (!locks) return attempt();
  const result = await locks.request(`noctus-reentry:${slug}`, { ifAvailable: true }, async (lock) =>
    lock ? attempt() : ({ status: 'deferred', retryInMs: INFLIGHT_TTL_MS } as EnterCoreOutcome),
  );
  return result as EnterCoreOutcome;
}
