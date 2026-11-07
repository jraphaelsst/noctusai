/**
 * The Motion feature bundle, loaded lazily by `MotionProvider`.
 *
 * `domAnimation` (animations, variants, exit, tap/hover/focus, in-view) is
 * the small tier; it deliberately excludes drag/layout (`domMax`). It lives
 * in its own module so `import("./features")` becomes a separate chunk and
 * the landing's first paint does not wait on it.
 */
import { domAnimation } from "motion/react";

export default domAnimation;
