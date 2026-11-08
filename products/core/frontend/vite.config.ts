import { createViteConfig } from "../../../seed/framework/frontend/vite.config.factory";

/**
 * Privileged bundles (platform admin, website admin, the admin-only internal docs) are emitted under
 * `_p/` with an OPAQUE hash-only name, never `assets/<Readable>-<hash>.js`: the main bundle's preload
 * map must not spell out `AdminUsers`/`TemplatesAdmin`/`FleetControl`/`15-api-contract` for anyone to read.
 * Interim (one step short of serving the bundle from an authenticated route): the files are still
 * statically served, so this is obscurity of the NAME, not access control. The access control is that
 * the bundle URL is only ever requested after the server confirmed the role.
 */
const PRIVILEGED =
  /[\\/]src[\\/](admin|pages[\\/]admin|website[\\/]docs)[\\/]|[\\/]src[\\/]pages[\\/]FleetControl\.|[\\/]src[\\/]lib[\\/](website|operations|usage|token-settings|templates-contract|billing\.admin|credits\.admin)\.|[\\/]src[\\/]hooks[\\/]useTemplates\./;

const base = createViteConfig({ port: 5173 });

export default {
  ...base,
  build: {
    ...base.build,
    rollupOptions: {
      ...base.build?.rollupOptions,
      output: {
        chunkFileNames: (chunk: { moduleIds: string[] }) =>
          chunk.moduleIds.some((id) => PRIVILEGED.test(id)) ? "_p/[hash].js" : "assets/[name]-[hash].js",
      },
    },
  },
};
