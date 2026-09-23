import path from "node:path";

import { createProductVitestConfig } from "../../../seed/framework/frontend/vitest.config.factory";

export default createProductVitestConfig({
  // jsdom Pointer Events polyfill (Radix Select under userEvent) — mirrors
  // seed/lib/frontend/tests/setup.ts.
  setupFilesExtra: [path.resolve(__dirname, "src/test/setup.ts")],
});
