/**
 * MetaMilestoneBurst — dependency-free celebration burst.
 *
 * Pure CSS: 14 emoji particles fan out from the origin with staggered
 * delays, each fading + rotating. The host element pulses briefly. When
 * `active=false`, nothing renders — we mount/unmount to re-trigger the
 * animation cleanly (keys each particle so React replays the keyframes).
 *
 * Used by MetasAgentWidget + MetasDashboard when `useMetaMilestoneToast`
 * observes a new `meta_atingida` notification.
 */
import { useEffect, useState } from 'react';

const EMOJIS = ['🎉', '✨', '🏆', '🎯', '💎', '🚀', '⭐'];
const PARTICLE_COUNT = 14;

export function MetaMilestoneBurst({
  active,
  onDone,
  durationMs = 1800,
}: {
  active: boolean;
  onDone?: () => void;
  durationMs?: number;
}) {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (!active) return;
    setShown(true);
    const t = setTimeout(() => {
      setShown(false);
      onDone?.();
    }, durationMs);
    return () => clearTimeout(t);
  }, [active, durationMs, onDone]);

  if (!shown) return null;

  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center z-30">
      <style>{`
        @keyframes meta-burst {
          0%   { transform: translate(0, 0) rotate(0deg) scale(0.4); opacity: 0; }
          20%  { opacity: 1; }
          100% { transform: translate(var(--dx), var(--dy)) rotate(var(--r)) scale(1.1); opacity: 0; }
        }
        @keyframes meta-pulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.08); box-shadow: 0 0 0 8px rgba(250,204,21,0.2); }
        }
        .meta-particle {
          position: absolute;
          font-size: 20px;
          animation: meta-burst ${durationMs}ms cubic-bezier(0.2,0.6,0.3,1) forwards;
        }
      `}</style>
      {Array.from({ length: PARTICLE_COUNT }).map((_, i) => {
        const angle = (i / PARTICLE_COUNT) * Math.PI * 2;
        const dist = 80 + (i % 3) * 24;
        const dx = Math.cos(angle) * dist;
        const dy = Math.sin(angle) * dist;
        const r = (i % 2 === 0 ? 1 : -1) * (120 + (i * 17) % 120);
        const delay = (i % 5) * 30;
        const emoji = EMOJIS[i % EMOJIS.length];
        return (
          <span
            key={i}
            className="meta-particle"
            style={{
              ['--dx' as any]: `${dx}px`,
              ['--dy' as any]: `${dy}px`,
              ['--r' as any]: `${r}deg`,
              animationDelay: `${delay}ms`,
            }}
          >
            {emoji}
          </span>
        );
      })}
    </div>
  );
}

/** Helper: a wrapper that adds the pulse class when `active`. Drop around
 *  any badge / pill you want to pulse in sync with the burst. */
export function MetaPulseWrap({
  active,
  children,
  className = '',
  durationMs = 1800,
}: {
  active: boolean;
  children: React.ReactNode;
  className?: string;
  durationMs?: number;
}) {
  return (
    <span
      className={`inline-block ${className}`}
      style={{
        animation: active
          ? `meta-pulse ${durationMs}ms ease-in-out`
          : undefined,
      }}
    >
      {children}
    </span>
  );
}
