import { LazyMotion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

export interface MotionProviderProps {
  children: ReactNode;
  /** CSP nonce forwarded to Motion's injected styles. */
  nonce?: string;
}

/**
 * Marketing motion root. `strict` makes any full `motion.*` component (which
 * would defeat the lazy feature bundle) throw in dev; only `m.*` is legal
 * underneath. `reducedMotion="user"` makes transform/layout animations
 * honour the OS `prefers-reduced-motion` setting.
 */
export function MotionProvider({ children, nonce }: MotionProviderProps) {
  return (
    <LazyMotion features={() => import("./features").then((m) => m.default)} strict>
      <MotionConfig reducedMotion="user" nonce={nonce}>
        {children}
      </MotionConfig>
    </LazyMotion>
  );
}
