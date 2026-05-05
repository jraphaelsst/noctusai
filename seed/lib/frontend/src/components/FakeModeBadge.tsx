/**
 * `<FakeModeBadge/>` — surfaces the current backend-adapter mode on every
 * product Settings page (and anywhere else a product wants the signal).
 *
 *   <FakeModeBadge />               // auto: full chip when fake, hidden when real
 *   <FakeModeBadge variant="dot" /> // small amber dot only
 *   <FakeModeBadge variant="full" />// always-show chip even if mode='real'
 *   <FakeModeBadge variant="none" />// renders nothing (escape hatch)
 *
 * Reads `VITE_BACKEND_MODE` via `useEnvMode()`. Mixed mode shows a partial
 * "Mode: Mixed" chip with a `title=` attribute listing the vendor map so
 * power users can hover for the breakdown. No emoji — plain Tailwind chip
 * matching the look-and-feel of `LLMSpendBadge` + `AIIndicator`.
 *
 * Keeps Fake-first as a seed-shipped UX, not per-product copy. Lifted from
 * `seed-hardening-from-youtube-crawler` Phase 3.1.
 */
import { useEnvMode, type EnvMode } from '../hooks/useEnvMode';

export type FakeModeBadgeVariant = 'auto' | 'full' | 'dot' | 'none';

export interface FakeModeBadgeProps {
  /**
   * Render strategy.
   *   - `auto` (default) — full chip when mode='fake' or 'mixed', hidden when 'real',
   *                        small grey "Mode: Unknown" chip when 'unknown'
   *   - `full` — always-show full chip with the resolved mode label
   *   - `dot`  — small amber dot (icon-only) when fake/mixed, hidden otherwise
   *   - `none` — render nothing (escape hatch for opt-out call sites)
   */
  variant?: FakeModeBadgeVariant;
  /** Optional className appended to the root element. */
  className?: string;
}

const BASE_CHIP_CLASSES =
  'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ring-1';

const TONE_BY_MODE: Record<EnvMode, string> = {
  fake: 'bg-amber-50 text-amber-800 ring-amber-200',
  mixed: 'bg-amber-50 text-amber-800 ring-amber-200',
  real: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  unknown: 'bg-slate-50 text-slate-700 ring-slate-200',
};

const LABEL_BY_MODE: Record<EnvMode, string> = {
  fake: 'Mode: Fake',
  mixed: 'Mode: Mixed',
  real: 'Mode: Real',
  unknown: 'Mode: Unknown',
};

function formatVendorTitle(vendors: { [name: string]: 'real' | 'fake' }): string {
  const entries = Object.entries(vendors);
  if (entries.length === 0) return '';
  return entries.map(([name, mode]) => `${name}=${mode}`).join(', ');
}

export function FakeModeBadge({ variant = 'auto', className = '' }: FakeModeBadgeProps) {
  const { mode, vendors } = useEnvMode();

  if (variant === 'none') return null;

  if (variant === 'dot') {
    if (mode !== 'fake' && mode !== 'mixed') return null;
    const title = mode === 'mixed' ? formatVendorTitle(vendors) : 'Mode: Fake';
    return (
      <span
        className={`inline-block h-2 w-2 rounded-full bg-amber-500 ring-1 ring-amber-200 ${className}`}
        title={title}
        aria-label={title}
        role="img"
      />
    );
  }

  // `auto` hides the chip when running fully real.
  if (variant === 'auto' && mode === 'real') return null;

  const tone = TONE_BY_MODE[mode];
  const label = LABEL_BY_MODE[mode];
  const title = mode === 'mixed' ? formatVendorTitle(vendors) : undefined;

  return (
    <span
      className={`${BASE_CHIP_CLASSES} ${tone} ${className}`}
      title={title}
      aria-label={label}
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-current opacity-70" aria-hidden="true" />
      {label}
    </span>
  );
}

export default FakeModeBadge;
