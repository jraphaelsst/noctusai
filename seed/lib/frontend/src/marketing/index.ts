/**
 * `@noctusai/lib/marketing` — the ONLY entry point that exposes Motion.
 *
 * Never re-export from the root barrel (`src/index.ts`): the authenticated
 * app must not pay for animation code. Landing pages import this subpath
 * from a lazy route chunk.
 */
export { MotionProvider } from "./MotionProvider";
export type { MotionProviderProps } from "./MotionProvider";
export { Reveal, Stagger } from "./primitives";
export type { RevealProps, StaggerProps } from "./primitives";
