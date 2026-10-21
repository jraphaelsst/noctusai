/** Query-key root for Geração, kept dependency-free so hooks share it — and a test that
 *  `vi.mock`s one hook module (e.g. useHeadlineMutations) cannot strip it from the others. */
export const GERACAO_KEY = ["sw", "geracao"] as const;
