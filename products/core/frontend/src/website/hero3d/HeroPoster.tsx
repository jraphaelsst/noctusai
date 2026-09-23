/**
 * Static poster — the hero's LCP element (P2/06 §3D hero). An inline SVG
 * gradient/constellation render standing in for "frame 0" of the scene: it
 * reads the SAME `--scene-*` CSS custom properties the live scene reads, so
 * light/dark and the eventual rebrand motif recolour both together with
 * zero extra network request (no PNG/AVIF round-trip — the brief explicitly
 * allows "inline SVG/CSS gradient render of frame 0" as the poster).
 *
 * `aria-hidden`: purely decorative; the crawlable message lives in the HTML
 * H1/subhead/CTAs rendered on top (P1).
 */
const NODES = [
  { cx: 18, cy: 30, r: 2.4 },
  { cx: 34, cy: 18, r: 1.6 },
  { cx: 52, cy: 34, r: 3 },
  { cx: 68, cy: 22, r: 1.8 },
  { cx: 78, cy: 42, r: 2.2 },
  { cx: 44, cy: 52, r: 1.4 },
  { cx: 60, cy: 58, r: 2 },
  { cx: 24, cy: 56, r: 1.6 },
];

const LINKS: [number, number][] = [
  [0, 1], [1, 2], [2, 3], [3, 4], [2, 5], [5, 6], [0, 7], [5, 7],
];

export function HeroPoster() {
  return (
    <svg
      className="nx-hero-poster"
      viewBox="0 0 100 70"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <radialGradient id="nx-poster-bg" cx="30%" cy="20%" r="90%">
          <stop offset="0%" stopColor="var(--scene-bg)" />
          <stop offset="100%" stopColor="var(--bg-inverse)" />
        </radialGradient>
        <linearGradient id="nx-poster-line" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--scene-accent)" stopOpacity="0.55" />
          <stop offset="100%" stopColor="var(--scene-accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="100" height="70" fill="url(#nx-poster-bg)" />
      {LINKS.map(([a, b], i) => (
        <line
          key={i}
          x1={NODES[a].cx}
          y1={NODES[a].cy}
          x2={NODES[b].cx}
          y2={NODES[b].cy}
          stroke="url(#nx-poster-line)"
          strokeWidth="0.25"
        />
      ))}
      {NODES.map((n, i) => (
        <circle key={i} cx={n.cx} cy={n.cy} r={n.r} fill="var(--scene-accent)" opacity="0.85" />
      ))}
      <rect x="0" y="0" width="100" height="70" fill="var(--scene-fog)" opacity="0.08" />
    </svg>
  );
}
