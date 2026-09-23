/**
 * The interactive 3D hero — mounts the scene chunk (dynamic `import()`
 * only) after LCP + idle + in-view, on capable devices; otherwise stays on
 * the poster with an "Explorar em 3D" opt-in (P2/06 §3D hero, 09 §Budgets).
 *
 * The scene chunk itself (`./scene.ts`) is never statically imported here —
 * only ever reached through `import("./scene")`, so it lands in its own
 * lazy chunk and the app bundle can never pull it in by accident (P2 guard).
 */
import { useEffect, useRef, useState } from "react";
import { HeroPoster } from "./HeroPoster";
import type { SceneHandle, SceneNode } from "./scene";

export interface HeroModule {
  slug: string;
  label: string;
  href: string;
}

function isLowPower(): boolean {
  if (typeof navigator === "undefined") return false;
  const nav = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } };
  const saveData = !!nav.connection?.saveData;
  const lowMemory = typeof nav.deviceMemory === "number" && nav.deviceMemory <= 4;
  const reducedMotion =
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const narrow = typeof window !== "undefined" && window.innerWidth < 760;
  return saveData || lowMemory || !!reducedMotion || narrow;
}

export function HeroScene({ modules }: { modules: HeroModule[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<SceneHandle | null>(null);
  const [mounted, setMounted] = useState(false);
  const [optedIn, setOptedIn] = useState(false);
  const [inView, setInView] = useState(false);
  const [labelPositions, setLabelPositions] = useState<
    Record<string, { x: number; y: number; visible: boolean }>
  >({});
  const lowPower = typeof window !== "undefined" ? isLowPower() : false;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const obs = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.2 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (lowPower && !optedIn) return;
    if (!inView || mounted) return;
    const el = containerRef.current;
    if (!el) return;

    let cancelled = false;
    function idle(cb: () => void): void {
      const w = window as unknown as { requestIdleCallback?: (cb: () => void) => number };
      if (typeof w.requestIdleCallback === "function") {
        w.requestIdleCallback(cb);
      } else {
        window.setTimeout(cb, 200);
      }
    }

    idle(() => {
      if (cancelled) return;
      import("./scene").then(({ createConstellationScene }) => {
        if (cancelled || !el) return;
        const nodes: SceneNode[] = modules.map((m, i) => {
          const angle = (i / modules.length) * Math.PI * 2;
          return {
            slug: m.slug,
            label: m.label,
            position: [Math.cos(angle) * 3.4, Math.sin(angle) * 2.2, Math.sin(angle * 2) * 1.2],
          };
        });
        const handle = createConstellationScene(el, nodes, document.documentElement);
        handle.onProjectedPositions(setLabelPositions);
        handleRef.current = handle;
        setMounted(true);
      });
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, lowPower, optedIn]);

  useEffect(() => {
    return () => {
      handleRef.current?.dispose();
    };
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const onVisibility = () => {
      if (document.hidden) handleRef.current?.pause();
      else handleRef.current?.resume();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const showCanvas = mounted;

  return (
    <>
      <HeroPoster />
      <div ref={containerRef} className="nx-hero-scene" style={{ opacity: showCanvas ? 1 : 0 }} aria-hidden="true" />
      {lowPower && !optedIn && (
        <button type="button" className="nx-btn nx-explore-3d" onClick={() => setOptedIn(true)}>
          Explorar em 3D
        </button>
      )}
      {showCanvas &&
        modules.map((m) => {
          const pos = labelPositions[m.slug];
          if (!pos || !pos.visible) return null;
          return (
            <a
              key={m.slug}
              href={m.href}
              className="nx-hero-hud-label nx-visually-hidden-when-static"
              style={{
                position: "absolute",
                left: pos.x,
                top: pos.y,
                zIndex: 3,
                transform: "translate(-50%, -50%)",
                fontSize: 12,
                fontFamily: "var(--nx-mono, monospace)",
                background: "rgba(0,0,0,0.5)",
                color: "#fff",
                padding: "2px 8px",
                borderRadius: 999,
                pointerEvents: "auto",
              }}
            >
              {m.label}
            </a>
          );
        })}
    </>
  );
}
