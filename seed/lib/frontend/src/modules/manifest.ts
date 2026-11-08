/**
 * `moduleManifest(modules)` — the page-key contract, same shape as BE `noctusai_seed.modules.module_manifest`.
 * Deterministic (modules + pages sorted by key). A host commits the BE-generated JSON and asserts the FE modules
 * produce the identical manifest (`assertManifestMatches`); the seed pins the cross-language parity with a shared
 * fixture (`seed/lib/backend/tests/fixtures/module_manifest.json`).
 */
import type { DefinedModule } from './define';

export const MODULE_MANIFEST_VERSION = 1;

export interface ModuleManifest {
  version: number;
  modules: Array<{
    key: string;
    enablement_key: string;
    pages: Array<{ key: string; path: string; label: string; status: string }>;
  }>;
}

const byKey = <T extends { key: string }>(a: T, b: T) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0);

export function moduleManifest(modules: readonly DefinedModule[]): ModuleManifest {
  return {
    version: MODULE_MANIFEST_VERSION,
    modules: modules
      .map((m) => ({
        key: m.key as string,
        enablement_key: m.enablementKey,
        pages: m.pages
          .map((p) => ({ key: p.pageKey, path: p.path, label: p.label, status: p.status ?? 'producao' }))
          .sort(byKey),
      }))
      .sort(byKey),
  };
}

/** Throws a readable diff when the FE modules and the (BE-generated) manifest disagree. */
export function assertManifestMatches(modules: readonly DefinedModule[], expected: ModuleManifest): void {
  const actual = JSON.stringify(moduleManifest(modules), null, 2);
  const want = JSON.stringify(expected, null, 2);
  if (actual !== want) throw new Error(`module page-key contract diverged from the manifest.\n--- manifest\n${want}\n--- frontend\n${actual}`);
}
