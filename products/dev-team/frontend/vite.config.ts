/**
 * dev-team frontend Vite config.
 *
 * Uses the seed factory; passes `extend` to inject the dev_team schema +
 * the dev-team backend port (8009) since the product is not yet in the
 * factory's PRODUCT_MAP. Promoting a PRODUCT_MAP entry into the seed is a
 * cross-cutting change that belongs in the next master-tree pass — flagged
 * in the engineer-H findings, not applied here (out of scope per brief).
 *
 * Also extends `resolve.alias` to point bare imports of the seed's peer
 * deps (`clsx`, `tailwind-merge`, `recharts`, `react-hook-form`, `zod`)
 * at the product's `node_modules`. Without this, rollup's default
 * resolution can't walk out of `seed/lib/frontend/src/...` into the
 * product's `node_modules` and the build fails with
 *   `Rollup failed to resolve import "clsx" from "<seed>/utils.ts"`.
 * The factory's existing `dedupe` list covers react/router/etc — these
 * five deps were missing from it; flagged for the seed promotion pass.
 */
import path from "path";
import { createViteConfig } from "../../../seed/framework/frontend/vite.config.factory";

const PRODUCT_NODE_MODULES = path.resolve(__dirname, "node_modules");

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

export default createViteConfig({
  port: 8123,
  backendPort: 8009,
  extend: (config) => {
    // Override the schema injection — factory defaulted to "public" because
    // dev-team isn't in the PRODUCT_MAP yet.
    config.define = {
      ...(config.define ?? {}),
      "import.meta.env.VITE_PRODUCT_SCHEMA": JSON.stringify("dev_team"),
    };
    const existingAlias = (config.resolve?.alias ?? {}) as Record<string, string>;
    const peerAlias: Record<string, string> = {};
    for (const dep of PEER_DEPS) {
      peerAlias[dep] = path.resolve(PRODUCT_NODE_MODULES, dep);
    }
    config.resolve = {
      ...config.resolve,
      alias: { ...peerAlias, ...existingAlias },
      dedupe: [...(config.resolve?.dedupe ?? []), ...PEER_DEPS],
    };
    return config;
  },
});
