/**
 * ProductIcon — renders a product's `icone` field.
 *
 * The catalog stores `icone` as a lucide-react icon NAME (the scaffolder
 * convention; default "Box") — e.g. "Building2", "Share2", "BookOpen". Older
 * hand-seeded rows used an emoji ("🏠"); those are rendered verbatim as a
 * fallback. So a value that maps to a known Lucide icon renders the SVG; any
 * other value (emoji, or a not-yet-mapped name) renders as text.
 *
 * To add a new product icon: import it from lucide-react and add it to ICONS.
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
  Box, // scaffolder default for freshly-created products
};

export function ProductIcon({ name, color }: { name: string; color?: string }) {
  const Icon = ICONS[name];
  if (Icon) {
    return (
      <Icon
        className="h-8 w-8"
        strokeWidth={1.75}
        style={color ? { color } : undefined}
        aria-hidden
      />
    );
  }
  // Emoji or unmapped name — render verbatim.
  return <span className="text-3xl leading-none">{name}</span>;
}
