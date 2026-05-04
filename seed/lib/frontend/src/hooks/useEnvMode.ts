/**
 * `useEnvMode()` — surfaces the current backend-adapter mode to UI code.
 *
 * Backed by the `VITE_BACKEND_MODE` env var, which products inject at
 * build time to declare whether their backend is running real adapters,
 * fake adapters (Fake-first dev / CI), or a mix per vendor.
 *
 * Accepted values for `VITE_BACKEND_MODE`:
 *   - `"real"`   → all vendors real → mode='real'
 *   - `"fake"`   → all vendors fake → mode='fake'
 *   - comma-separated `vendor=mode` pairs (e.g. `"calendar=fake,maps=real"`)
 *                → mode='mixed'; vendors map populated per pair
 *   - missing / unrecognized → mode='unknown'
 *
 * Malformed input falls back to `mode='unknown'` and emits a single
 * `console.warn` in dev mode (silent in prod).
 *
 * Cements the Fake-first methodology as a seed-shipped UX surface — every
 * product Settings page mounts `<FakeModeBadge/>` and gets the right
 * "Mode: Fake" chip without per-product copy. Lifted from
 * `seed-hardening-from-youtube-crawler` Phase 3.1.
 */

export type EnvMode = 'real' | 'fake' | 'mixed' | 'unknown';

export type VendorMode = 'real' | 'fake';

export interface EnvModeResult {
  mode: EnvMode;
  vendors: { [name: string]: VendorMode };
}

const DEFAULT_VENDOR_LABELS = ['default'];

function getViteEnv(): Record<string, string | undefined> | undefined {
  const meta = (import.meta as unknown as { env?: Record<string, string | undefined> });
  return meta?.env;
}

function isDev(): boolean {
  const env = getViteEnv();
  return Boolean(env?.DEV);
}

function warnOnce(message: string): void {
  if (typeof console !== 'undefined' && console.warn && isDev()) {
    console.warn(`[useEnvMode] ${message}`);
  }
}

function parseVendorPair(pair: string): [string, VendorMode] | null {
  const [rawName, rawMode] = pair.split('=');
  if (!rawName || !rawMode) return null;
  const name = rawName.trim();
  const mode = rawMode.trim().toLowerCase();
  if (!name) return null;
  if (mode !== 'real' && mode !== 'fake') return null;
  return [name, mode as VendorMode];
}

/**
 * Reads `VITE_BACKEND_MODE` and returns the resolved {mode, vendors} pair.
 *
 * Pure function — does not call any React hook. Renamed `use*` to match
 * the conventional naming, but it is safe to call outside a component
 * (e.g. from a route loader or a class component).
 */
export function useEnvMode(): EnvModeResult {
  const env = getViteEnv();
  const raw = env?.VITE_BACKEND_MODE;

  if (raw === undefined || raw === null) {
    return { mode: 'unknown', vendors: {} };
  }

  const trimmed = String(raw).trim();
  if (trimmed === '') {
    return { mode: 'unknown', vendors: {} };
  }

  const lower = trimmed.toLowerCase();
  if (lower === 'real' || lower === 'fake') {
    const m = lower as VendorMode;
    const vendors: { [name: string]: VendorMode } = {};
    for (const name of DEFAULT_VENDOR_LABELS) {
      vendors[name] = m;
    }
    return { mode: m, vendors };
  }

  // Mixed: comma-separated vendor=mode pairs.
  if (trimmed.includes('=')) {
    const pairs = trimmed.split(',').map((p) => p.trim()).filter(Boolean);
    const vendors: { [name: string]: VendorMode } = {};
    let ok = true;
    for (const p of pairs) {
      const parsed = parseVendorPair(p);
      if (!parsed) {
        ok = false;
        break;
      }
      vendors[parsed[0]] = parsed[1];
    }
    if (!ok || Object.keys(vendors).length === 0) {
      warnOnce(`malformed VITE_BACKEND_MODE value: ${JSON.stringify(raw)} — falling back to 'unknown'`);
      return { mode: 'unknown', vendors: {} };
    }
    const values = Object.values(vendors);
    const allSame = values.every((v) => v === values[0]);
    if (allSame && values.length > 0) {
      // Shape `vendor=fake,other=fake` collapses to a uniform mode rather
      // than 'mixed'. This keeps the UX badge consistent with `"fake"` /
      // `"real"` literal values.
      return { mode: values[0], vendors };
    }
    return { mode: 'mixed', vendors };
  }

  warnOnce(`unrecognized VITE_BACKEND_MODE value: ${JSON.stringify(raw)} — falling back to 'unknown'`);
  return { mode: 'unknown', vendors: {} };
}
