import { Children, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { m, useInView, useReducedMotion } from "motion/react";

/** `useLayoutEffect` warns during SSR; fall back to `useEffect` there. */
const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

/**
 * "Armed" = JS is running on the client AND the user accepts motion.
 *
 * SSR rule: until armed, content renders fully visible (`initial={false}`,
 * shown state), so it is readable with JS disabled, before hydration, and for
 * crawlers. Arming happens in a layout effect, i.e. before the first client
 * paint, and the hide step uses a zero-duration transition, so there is no
 * visible flash of the content-then-hidden.
 */
function useArmed(): boolean {
  const reduced = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  useIsoLayoutEffect(() => setMounted(true), []);
  return mounted && !reduced;
}

export interface RevealProps {
  children: ReactNode;
  className?: string;
  /** Seconds. */
  delay?: number;
  /** Initial vertical offset in px. */
  y?: number;
  /** Seconds. */
  duration?: number;
  /** Initial scale (e.g. 0.96 for a scale-in). Omitted = no scale animation (default). */
  scale?: number;
}

/** Fades/slides its children in once, when they scroll into view. */
export function Reveal({ children, className, delay = 0, y = 16, duration = 0.5, scale }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const armed = useArmed();
  const inView = useInView(ref, { once: true, margin: "0px 0px -10% 0px" });
  const hidden = armed && !inView;
  return (
    <m.div
      ref={ref}
      className={className}
      initial={false}
      animate={
        hidden
          ? { opacity: 0, y, ...(scale !== undefined ? { scale } : {}) }
          : { opacity: 1, y: 0, ...(scale !== undefined ? { scale: 1 } : {}) }
      }
      transition={hidden ? { duration: 0 } : { duration, delay, ease: "easeOut" }}
    >
      {children}
    </m.div>
  );
}

export interface StaggerProps {
  children: ReactNode;
  className?: string;
  /** Class applied to the per-child wrapper. */
  itemClassName?: string;
  /** Seconds between children. */
  gap?: number;
  y?: number;
  duration?: number;
}

/** Cascades its direct children in, one after another, when scrolled into view. */
export function Stagger({ children, className, itemClassName, gap = 0.08, y = 16, duration = 0.45 }: StaggerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const armed = useArmed();
  const inView = useInView(ref, { once: true, margin: "0px 0px -10% 0px" });
  const hidden = armed && !inView;
  return (
    <m.div
      ref={ref}
      className={className}
      initial={false}
      animate={hidden ? "hidden" : "visible"}
      variants={{ hidden: {}, visible: { transition: { staggerChildren: gap } } }}
    >
      {Children.toArray(children).map((child, i) => (
        <m.div
          key={i}
          className={itemClassName}
          variants={{
            hidden: { opacity: 0, y, transition: { duration: 0 } },
            visible: { opacity: 1, y: 0, transition: { duration, ease: "easeOut" } },
          }}
        >
          {child}
        </m.div>
      ))}
    </m.div>
  );
}
