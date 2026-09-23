/**
 * Website > Documentação — doc source: path resolution + index building.
 *
 * Pure logic (no React) so it's cheaply unit-testable and so `Docs.tsx`
 * can inject a fixture `DocsSource` in tests without touching
 * `import.meta.glob` (a build-time-only construct vitest can't easily mock
 * per-test). The REAL source (`DEFAULT_DOCS_SOURCE`) glob-loads
 * `../../../website/docs/**` — content the tech-lead publishes on a
 * separate branch (`feat/noctus-website-docs`); until that lands, the glob
 * legitimately resolves to zero files and the page renders its empty state.
 */

export interface DocsSource {
  /**
   * Lazy loader per doc-relative path (code-split — content is only
   * fetched once this admin page is visited), e.g. "00-index.md" or
   * "03-reference-reports/linear.md".
   */
  markdown: Record<string, () => Promise<string>>;
  /**
   * Resolved asset URL per doc-relative path, e.g. "assets/refs/linear-home.webp".
   * EAGER (a plain string, not a loader): `MarkdownRenderer`'s `resolveImage`
   * seam is synchronous by contract, and a `?url` import resolves to a
   * statically-known hashed path at build time — no actual async I/O to
   * defer, so there is no async-loader/re-render dance to get right here.
   */
  images: Record<string, string>;
}

export interface DocEntry {
  /** Doc id used in the route + for cross-doc navigation — no folder prefix stripped, no `.md`. */
  docId: string;
  /** First `# ` heading in the doc, or a humanized filename fallback. */
  title: string;
  /** Top-level folder name (`null` for root-level docs). */
  folder: string | null;
  content: string;
}

export interface DocsIndexGroup {
  key: string;
  /** `null` for the root (folder-less) group — rendered without a header. */
  label: string | null;
  entries: DocEntry[];
}

const DOCS_BASE = '../../../website/docs/';

// Vite statically analyzes `import.meta.glob` at build time — the pattern
// argument MUST be an inline string literal (not a variable reference), or
// the "Could only use literals" build error fires. Keep both patterns and
// `DOCS_BASE` above in lockstep by hand.
const DEFAULT_MARKDOWN_GLOB = import.meta.glob('../../../website/docs/**/*.md', {
  query: '?raw',
  import: 'default',
}) as Record<string, () => Promise<string>>;
// `eager: true` here (unlike the markdown glob above): a `?url` import
// resolves to a statically-known hashed path with no real async I/O, and
// `MarkdownRenderer`'s `resolveImage` seam is synchronous by contract.
const DEFAULT_IMAGES_GLOB = import.meta.glob(
  '../../../website/docs/**/*.{webp,jpg,jpeg,png,svg}',
  { eager: true, query: '?url', import: 'default' },
) as Record<string, string>;

/** `../../../website/docs/03-reference-reports/linear.md` -> `03-reference-reports/linear.md`. */
function stripDocsBase(globKey: string): string {
  return globKey.startsWith(DOCS_BASE) ? globKey.slice(DOCS_BASE.length) : globKey;
}

function reindexKeysByRelativePath<T>(map: Record<string, T>): Record<string, T> {
  const out: Record<string, T> = {};
  for (const [key, value] of Object.entries(map)) {
    out[stripDocsBase(key)] = value;
  }
  return out;
}

export function buildDefaultDocsSource(): DocsSource {
  return {
    markdown: reindexKeysByRelativePath(DEFAULT_MARKDOWN_GLOB),
    images: reindexKeysByRelativePath(DEFAULT_IMAGES_GLOB),
  };
}

/** `03-reference-reports/linear.md` -> docId `03-reference-reports/linear`. */
export function pathToDocId(relPath: string): string {
  return relPath.replace(/\.md$/i, '');
}

/** `03-reference-reports/linear` -> docId `03-reference-reports/linear.md`. */
export function docIdToPath(docId: string): string {
  return `${docId}.md`;
}

/** Humanize a filename/folder segment: strip a leading `NN-`, replace dashes with spaces, title-case. */
export function humanizeSegment(segment: string): string {
  const stripped = segment.replace(/^\d+-/, '').replace(/-/g, ' ').trim();
  if (!stripped) return segment;
  return stripped.replace(/\b\w/g, (c) => c.toUpperCase());
}

/** First `# ` (h1) heading in a markdown doc, trimmed — or `null` if none. */
export function extractTitle(content: string): string | null {
  const match = content.match(/^\s*#\s+(.+?)\s*$/m);
  return match ? match[1].trim() : null;
}

/** Resolve a relative path (image src, or a `.md` link's path portion) against the CURRENT doc's location. */
export function resolveRelativePath(fromDocId: string, relPath: string): string {
  const fromDir = fromDocId.includes('/') ? fromDocId.slice(0, fromDocId.lastIndexOf('/')) : '';
  const combined = fromDir ? `${fromDir}/${relPath}` : relPath;
  const stack: string[] = [];
  for (const part of combined.split('/')) {
    if (part === '' || part === '.') continue;
    if (part === '..') stack.pop();
    else stack.push(part);
  }
  return stack.join('/');
}

/** Split `href` into its path + optional `#hash` (undefined when absent). */
export function splitHash(href: string): { path: string; hash?: string } {
  const idx = href.indexOf('#');
  if (idx === -1) return { path: href };
  return { path: href.slice(0, idx), hash: href.slice(idx + 1) };
}

/** Resolve a markdown cross-doc link's href (relative `.md` path, optional `#hash`) into a target docId + hash. */
export function resolveDocLink(
  fromDocId: string,
  href: string,
): { docId: string; hash?: string } {
  const { path, hash } = splitHash(href);
  // An empty path (a bare `#hash`) stays on the CURRENT doc — in practice
  // `MarkdownRenderer` never routes a bare `#hash` through `onNavigate` at
  // all (native anchor scroll), but this keeps the contract correct for
  // any other caller.
  if (path === '') return { docId: fromDocId, hash };
  const resolvedPath = resolveRelativePath(fromDocId, path);
  return { docId: pathToDocId(resolvedPath), hash };
}

/** Resolve a markdown image `src` (relative to the current doc) into the docs-root-relative asset path. */
export function resolveImagePath(fromDocId: string, src: string): string {
  return resolveRelativePath(fromDocId, src);
}

export async function loadAllDocs(source: DocsSource): Promise<DocEntry[]> {
  const paths = Object.keys(source.markdown).sort();
  const entries = await Promise.all(
    paths.map(async (relPath) => {
      const content = await source.markdown[relPath]();
      const docId = pathToDocId(relPath);
      const folder = docId.includes('/') ? docId.split('/')[0] : null;
      const title = extractTitle(content) ?? humanizeSegment(docId.split('/').pop() ?? docId);
      return { docId, title, folder, content } satisfies DocEntry;
    }),
  );
  return entries;
}

/** Group entries: root-level docs first (no header, `key: ''`), then one group per folder, both alpha-sorted. */
export function buildDocsIndex(entries: DocEntry[]): DocsIndexGroup[] {
  const root: DocEntry[] = [];
  const byFolder = new Map<string, DocEntry[]>();
  for (const entry of entries) {
    if (entry.folder === null) {
      root.push(entry);
    } else {
      const list = byFolder.get(entry.folder) ?? [];
      list.push(entry);
      byFolder.set(entry.folder, list);
    }
  }
  const sortByDocId = (a: DocEntry, b: DocEntry) => a.docId.localeCompare(b.docId);
  root.sort(sortByDocId);

  const groups: DocsIndexGroup[] = [];
  if (root.length > 0) {
    groups.push({ key: '', label: null, entries: root });
  }
  for (const folder of [...byFolder.keys()].sort((a, b) => a.localeCompare(b))) {
    const list = byFolder.get(folder)!;
    list.sort(sortByDocId);
    groups.push({ key: folder, label: humanizeSegment(folder), entries: list });
  }
  return groups;
}
