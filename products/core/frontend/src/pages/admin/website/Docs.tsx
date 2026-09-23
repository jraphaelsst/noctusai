/**
 * `<Docs/>` — Website > Documentação viewer (`/admin/website/docs/*`).
 *
 * Renders the website design+tech documentation the tech-lead writes into
 * `products/core/frontend/src/website/docs/**` (a SEPARATE branch — this
 * page never imports from `./website/` directly; it code-splits the
 * corpus via `import.meta.glob` inside `docsSource.ts` so it works against
 * whatever `.md`/image tree lands there after integration).
 *
 * Left pane: index grouped by folder, ordered by filename, title = first
 * `# ` heading (fallback: humanized filename). Right pane: the active doc
 * via the seed `MarkdownRenderer`, wired to in-app navigation for relative
 * `.md` links and resolved URLs for relative images.
 *
 * DI test seam: `docsSource` defaults to the real glob maps
 * (`buildDefaultDocsSource()`) but is an injectable prop so tests feed
 * fixture docs without touching `import.meta.glob` (a build-time-only
 * construct).
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Search } from 'lucide-react';
import { MarkdownRenderer } from '@noctusai/lib/components';
import { Skeleton, EmptyState, ErrorState } from '@noctusai/lib/design-system';

import {
  buildDefaultDocsSource,
  buildDocsIndex,
  loadAllDocs,
  resolveDocLink,
  resolveImagePath,
  type DocEntry,
  type DocsIndexGroup,
  type DocsSource,
} from './docsSource';

const DEFAULT_DOC_ID = '00-index';

export interface DocsProps {
  docsSource?: DocsSource;
}

type LoadState =
  | { status: 'pending' }
  | { status: 'error'; error: Error }
  | { status: 'ready'; entries: DocEntry[] };

function useDocsCorpus(docsSource: DocsSource): LoadState {
  const [state, setState] = useState<LoadState>({ status: 'pending' });

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'pending' });
    loadAllDocs(docsSource)
      .then((entries) => {
        if (!cancelled) setState({ status: 'ready', entries });
      })
      .catch((error: Error) => {
        if (!cancelled) setState({ status: 'error', error });
      });
    return () => {
      cancelled = true;
    };
    // `docsSource` is expected to be referentially stable within a mount
    // (the default is a module-level constant; tests pass a fixture once).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return state;
}

function filterGroups(groups: DocsIndexGroup[], query: string): DocsIndexGroup[] {
  if (!query.trim()) return groups;
  const needle = query.trim().toLowerCase();
  return groups
    .map((group) => ({
      ...group,
      entries: group.entries.filter((entry) => entry.title.toLowerCase().includes(needle)),
    }))
    .filter((group) => group.entries.length > 0);
}

export function Docs({ docsSource }: DocsProps = {}) {
  const source = useMemo(() => docsSource ?? buildDefaultDocsSource(), [docsSource]);
  const state = useDocsCorpus(source);
  const params = useParams();
  const navigate = useNavigate();
  const [filter, setFilter] = useState('');

  const rawDocId = params['*'] ?? '';
  const docId = rawDocId || DEFAULT_DOC_ID;

  const entries = state.status === 'ready' ? state.entries : [];
  const groups = useMemo(() => buildDocsIndex(entries), [entries]);
  const filteredGroups = useMemo(() => filterGroups(groups, filter), [groups, filter]);
  const activeDoc = entries.find((e) => e.docId === docId) ?? null;

  useEffect(() => {
    if (state.status !== 'ready' || !activeDoc) return;
    const hash = window.location.hash.replace(/^#/, '');
    if (!hash) return;
    // Wait a tick for MarkdownRenderer to mount the heading before scrolling.
    const id = window.requestAnimationFrame(() => {
      document.getElementById(hash)?.scrollIntoView({ block: 'start' });
    });
    return () => window.cancelAnimationFrame(id);
  }, [state.status, activeDoc, docId]);

  function handleNavigate(href: string) {
    const { docId: targetDocId, hash } = resolveDocLink(docId, href);
    navigate(`/admin/website/docs/${targetDocId}${hash ? `#${hash}` : ''}`);
  }

  function resolveImage(src: string): string | undefined {
    return source.images[resolveImagePath(docId, src)];
  }

  if (state.status === 'pending') {
    return (
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr]">
        <Skeleton height={320} announce label="Carregando documentação" />
        <Skeleton height={480} announce={false} />
      </div>
    );
  }

  if (state.status === 'error') {
    return <ErrorState message={`Não foi possível carregar a documentação: ${state.error.message}`} />;
  }

  if (entries.length === 0) {
    return <EmptyState message="Nenhuma documentação publicada ainda." />;
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr]">
      <nav aria-label="Índice da documentação" className="lg:sticky lg:top-4 lg:self-start">
        <div className="relative mb-3">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filtrar por título..."
            aria-label="Filtrar por título"
            className="w-full rounded-md border border-input bg-background py-2 pl-8 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
        {filteredGroups.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum resultado.</p>
        ) : (
          <div className="space-y-4">
            {filteredGroups.map((group) => (
              <div key={group.key}>
                {group.label && (
                  <div className="mb-1.5 px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {group.label}
                  </div>
                )}
                <ul className="space-y-0.5">
                  {group.entries.map((entry) => (
                    <li key={entry.docId}>
                      <button
                        type="button"
                        onClick={() => navigate(`/admin/website/docs/${entry.docId}`)}
                        aria-current={entry.docId === docId ? 'page' : undefined}
                        className={
                          entry.docId === docId
                            ? 'w-full rounded-md bg-primary/10 px-2 py-1.5 text-left text-sm font-medium text-primary'
                            : 'w-full rounded-md px-2 py-1.5 text-left text-sm text-foreground hover:bg-muted'
                        }
                      >
                        {entry.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </nav>

      <div className="min-w-0 rounded-lg border border-border bg-card p-6">
        {activeDoc ? (
          <MarkdownRenderer
            content={activeDoc.content}
            onNavigate={handleNavigate}
            resolveImage={resolveImage}
          />
        ) : (
          <EmptyState message={`Documento "${docId}" não encontrado.`} />
        )}
      </div>
    </div>
  );
}
