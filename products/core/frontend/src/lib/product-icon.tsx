/**
 * ProductIcon — renders a product's `icone` field.
 *
 * The catalog stores `icone` as a lucide-react icon NAME (the scaffolder
 * convention; default "Box") — e.g. "Building2", "Share2", "BookOpen". Older
 * hand-seeded rows used an emoji ("🏠"); those are rendered verbatim. Anything
 * else (empty, or an unregistered name) falls back to the Box default icon so a
 * bare lucide NAME never shows as text (the "Sprout" bug, 2026-05-25).
 *
 * `ICONS` is the single source of truth for "renders as a real icon". The
 * `check_product_icon_registered` keeper enforces that every product's seeded
 * icone is a key here (or an emoji) — so to add a new product icon, import it
 * from lucide-react and add it to ICONS below.
 */
import {
  Building2,
  Wallet,
  Brain,
  CalendarCheck,
  Share2,
  Store,
  Bot,
  BookOpen,
  Sprout,
  Box,
  type LucideIcon,
} from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
  Building2,
  Wallet,
  Brain,
  CalendarCheck,
  Share2,
  Store,
  Bot,
  BookOpen,
  Sprout, // seed (reference) product
  Box, // scaffolder default for freshly-created products
};

// Size presets so the same component fits both the dashboard cards (md) and
// dense admin table rows / inline headers (sm).
const SIZES = {
  sm: { icon: 'h-5 w-5', text: 'text-xl' },
  md: { icon: 'h-8 w-8', text: 'text-3xl' },
} as const;

/** An emoji icone is any value carrying a non-ASCII code point. */
function isEmoji(value: string): boolean {
  return [...value].some((ch) => (ch.codePointAt(0) ?? 0) > 127);
}

export function ProductIcon({
  name,
  color,
  size = 'md',
}: {
  name: string;
  color?: string;
  size?: keyof typeof SIZES;
}) {
  const preset = SIZES[size];
  // A registered name renders as an actual SVG icon.
  const Icon = ICONS[name];
  if (Icon) {
    return (
      <Icon
        className={preset.icon}
        strokeWidth={1.75}
        style={color ? { color } : undefined}
        aria-hidden
      />
    );
  }
  // A legacy emoji row renders verbatim.
  if (name && isEmoji(name)) {
    return <span className={`${preset.text} leading-none`}>{name}</span>;
  }
  // Empty or an unregistered lucide NAME — never show the bare name as text
  // (the "Sprout" bug). Fall back to the Box default icon. Seed data is kept
  // honest by the `check_product_icon_registered` keeper.
  return (
    <Box
      className={preset.icon}
      strokeWidth={1.75}
      style={color ? { color } : undefined}
      aria-hidden
    />
  );
}
