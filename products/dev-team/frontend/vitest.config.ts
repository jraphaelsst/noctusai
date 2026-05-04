import path from "path";
import { createProductVitestConfig } from "../../../seed/framework/frontend/vitest.config.factory";

const PRODUCT_NODE_MODULES = path.resolve(__dirname, "node_modules");

// Same peer-dep alias dance as `vite.config.ts` — the seed factory's
// dedupe list doesn't cover clsx / tailwind-merge / recharts / etc, so
// when vitest transforms the seed sources it can't resolve them without
// an explicit alias into the product's node_modules.
const PEER_DEPS = [
  "clsx",
  "tailwind-merge",
  "recharts",
  "react-hook-form",
  "@hookform/resolvers",
  "zod",
  "date-fns",
  "class-variance-authority",
  "tailwindcss-animate",
];

export default createProductVitestConfig({
  extend: (config) => {
    const peerAlias: Record<string, string> = {};
    for (const dep of PEER_DEPS) {
      peerAlias[dep] = path.resolve(PRODUCT_NODE_MODULES, dep);
    }
    config.resolve = {
      ...config.resolve,
      alias: {
        ...peerAlias,
        ...((config.resolve?.alias ?? {}) as Record<string, string>),
      },
    };
    config.test = {
      ...config.test,
      setupFiles: [
        ...(config.test?.setupFiles ?? []),
        path.resolve(__dirname, "tests/setup.ts"),
      ],
    };
    return config;
  },
});
