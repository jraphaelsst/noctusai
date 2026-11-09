/**
 * brand-icons — the brand glyphs lucide-react 1.x removed (Instagram, Facebook, Youtube).
 *
 * lucide dropped every brand icon in 1.0 (trademark policy). The fleet uses
 * these three in 40+ files, often in places typed as `LucideIcon` (nav maps,
 * provider cards), so a plain SVG component would not type-check there.
 * Each glyph is therefore rebuilt with lucide's own `createLucideIcon` from the
 * exact icon node that shipped in lucide-react 0.462.0: same 24×24 grid,
 * stroke, sizing props and `LucideIcon` type — a drop-in replacement for the
 * old named import, pixel-identical to what the fleet rendered before.
 *
 * Import from here, never re-declare in a product (canonical-organ rule):
 *     import { Instagram, Facebook, Youtube } from '@noctusai/lib/brand-icons';
 *
 * Icon nodes copied from lucide-react 0.462.0 (dist/esm/icons/{instagram,
 * facebook,youtube}.js) — ISC License, Copyright (c) Lucide Icons and
 * Contributors. The trademarks belong to their owners; use them only to
 * identify the corresponding service.
 */
import { createLucideIcon, type LucideIcon } from 'lucide-react';

export const Instagram: LucideIcon = createLucideIcon('Instagram', [
  ['rect', { width: '20', height: '20', x: '2', y: '2', rx: '5', ry: '5', key: '2e1cvw' }],
  ['path', { d: 'M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z', key: '9exkf1' }],
  ['line', { x1: '17.5', x2: '17.51', y1: '6.5', y2: '6.5', key: 'r4j83e' }],
]);

export const Facebook: LucideIcon = createLucideIcon('Facebook', [
  ['path', { d: 'M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z', key: '1jg4f8' }],
]);

export const Youtube: LucideIcon = createLucideIcon('Youtube', [
  [
    'path',
    {
      d: 'M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17',
      key: '1q2vi4',
    },
  ],
  ['path', { d: 'm10 15 5-3-5-3z', key: '1jp15x' }],
]);
