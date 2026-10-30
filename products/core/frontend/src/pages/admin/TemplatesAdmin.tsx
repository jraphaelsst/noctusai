/**
 * Admin > Templates -- the platform's editable, versioned template library at `/admin/templates/*`.
 * Left nav: kind -> scope (platform / product). Main: the scope's templates + editor, and the read-only
 * "Fontes" discovery of template-like assets that still live outside the DB. The filesystem scaffold
 * browser stays reachable at `/admin/templates/scaffolds`. `CoreLayout` already gates `/admin/*`; the
 * server enforces platform-admin on every call.
 */
import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { QueryErrorState } from '@noctusai/lib';
import { Badge, Button, Input, Skeleton } from '@noctusai/lib/design-system';

import { useTemplates, useTemplatesMeta } from '../../hooks/useTemplates';
import {
  KIND_LABEL, KIND_ORDER, PLATFORM_SCOPE, STATUS_LABEL, type TemplateFilters, type TemplateKind, type TemplatesMeta,
} from '../../lib/templates-contract';
import { AdminTemplates as ScaffoldBrowser } from './AdminTemplates';
import { TemplateCreate } from './templates/TemplateCreate';
import { TemplateEditor } from './templates/TemplateEditor';
import { TemplateSources } from './templates/TemplateSources';

const BASE = '/admin/templates';
const isKind = (s: string | undefined): s is TemplateKind => !!s && (KIND_ORDER as string[]).includes(s);

function NavTree({ meta, current }: { meta: TemplatesMeta; current: string }) {
  const item = (to: string, label: string, count?: number) => (
    <Link key={to} to={to} aria-current={current === to ? 'page' : undefined}
      className={`flex items-center justify-between rounded px-2 py-1 text-sm ${current === to ? 'bg-accent font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
      <span>{label}</span>{count ? <span className="text-xs">{count}</span> : null}
    </Link>
  );
  return (
    <nav aria-label="Templates" className="space-y-4">
      {meta.kinds.map((k) => (
        <div key={k.key}>
          {item(`${BASE}/${k.key}`, k.label, k.scopes.reduce((n, s) => n + s.templates, 0))}
          <div className="ml-3 border-l border-border pl-2">
            {k.scopes.map((s) => item(`${BASE}/${k.key}/${s.scope}`, s.label, s.templates + s.sources))}
          </div>
        </div>
      ))}
      <div className="border-t border-border pt-3">
        {item(`${BASE}/fontes`, 'Fontes (descoberta)')}
        {item(`${BASE}/scaffolds`, 'Scaffolds de projeto')}
      </div>
    </nav>
  );
}

function TemplateList({ filters, selectedId, onOpen }: { filters: TemplateFilters; selectedId: string | null; onOpen: (id: string) => void }) {
  const query = useTemplates(filters);
  if (query.isPending && !query.data) return <div data-testid="templates-loading" className="space-y-2"><Skeleton className="h-12 w-full" /><Skeleton className="h-12 w-full" /></div>;
  if (!query.data) return <QueryErrorState query={query} title="Não foi possível carregar os templates" />;
  if (query.data.length === 0) {
    return <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground" data-testid="templates-empty">Nenhum template neste escopo ainda. Crie um, ou veja as fontes abaixo para o que já existe fora do banco.</p>;
  }
  return (
    <ul className="divide-y divide-border rounded-md border border-border" data-testid="templates-list">
      {query.data.map((t) => (
        <li key={t.id}>
          <button type="button" onClick={() => onOpen(t.id)} aria-current={selectedId === t.id ? 'true' : undefined}
            className={`flex w-full items-center gap-3 px-3 py-2 text-left text-sm ${selectedId === t.id ? 'bg-accent' : 'hover:bg-muted'}`}>
            <span className="flex-1">
              <span className="block font-medium text-foreground">{t.title}</span>
              <span className="block text-xs text-muted-foreground">{t.key} · {t.product ?? 'plataforma'} · v{t.version}{t.has_draft && t.status !== 'draft' ? ' (há rascunho novo)' : ''}</span>
            </span>
            <Badge>{STATUS_LABEL[t.status]}</Badge>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function TemplatesAdmin() {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const meta = useTemplatesMeta();
  const [q, setQ] = useState('');
  const [segKind, segScope] = pathname.replace(/^\/admin\/templates\/?/, '').split('/').filter(Boolean);
  const params = new URLSearchParams(search);
  const selectedId = params.get('t');
  const creating = params.has('new');

  if (!segKind) return <Navigate to={`${BASE}/design_system`} replace />;
  if (segKind === 'scaffolds') return <Shell meta={meta} current={pathname}><ScaffoldBrowser /></Shell>;

  const here = pathname.replace(/\/$/, '');
  const open = (id: string) => navigate(`${here}?t=${id}`);

  if (segKind === 'fontes') {
    return (
      <Shell meta={meta} current={here}>
        <h2 className="text-lg font-semibold text-foreground">Fontes</h2>
        <p className="mb-4 text-sm text-muted-foreground">Prompts, mensagens, documentos e modelos que existem hoje fora do banco — onde vivem, somente leitura. Migrar um para a biblioteca = criar o template aqui e retirar a fonte.</p>
        <TemplateSources filters={{}} grouped />
      </Shell>
    );
  }
  if (!isKind(segKind)) return <Navigate to={`${BASE}/design_system`} replace />;

  const filters: TemplateFilters = { kind: segKind, ...(segScope ? { product: segScope } : {}), ...(q.trim() ? { q: q.trim() } : {}) };
  const scopeLabel = !segScope ? 'todos os escopos' : segScope === PLATFORM_SCOPE ? 'Plataforma' : meta.data?.products.find((p) => p.slug === segScope)?.label ?? segScope;
  return (
    <Shell meta={meta} current={here}>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="flex-1 text-lg font-semibold text-foreground">{KIND_LABEL[segKind]} <span className="text-sm font-normal text-muted-foreground">· {scopeLabel}</span></h2>
        <Input aria-label="Buscar" placeholder="Buscar…" value={q} onChange={(e) => setQ(e.target.value)} className="w-48" />
        <Button variant="primary" onClick={() => navigate(`${here}?new=1`)}>Novo template</Button>
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="space-y-6">
          <TemplateList filters={filters} selectedId={selectedId} onOpen={open} />
          <section aria-label="Fontes relacionadas">
            <h3 className="mb-2 text-sm font-semibold text-foreground">Fontes (fora do banco)</h3>
            <TemplateSources filters={{ kind: segKind, ...(segScope ? { product: segScope } : {}) }} />
          </section>
        </div>
        <div>
          {creating && meta.data
            ? <TemplateCreate meta={meta.data} kind={segKind} scope={segScope ?? null} onCreated={(t) => open(t.id)} onCancel={() => navigate(here)} />
            : selectedId ? <TemplateEditor id={selectedId} onOpen={open} />
            : <p className="text-sm text-muted-foreground" data-testid="editor-empty">Selecione um template para editar ou criar uma nova versão.</p>}
        </div>
      </div>
    </Shell>
  );
}

function Shell({ meta, current, children }: { meta: ReturnType<typeof useTemplatesMeta>; current: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <h1 className="mb-1 text-2xl font-bold text-foreground">Templates</h1>
      <p className="mb-6 text-sm text-muted-foreground">Biblioteca versionada da plataforma: design system, agentes, mensagens, documentos e modelos de repositório — por produto e por tipo.</p>
      <div className="grid gap-8 md:grid-cols-[14rem_minmax(0,1fr)]">
        <aside>
          {meta.isPending && !meta.data ? <div data-testid="nav-loading" className="space-y-2"><Skeleton className="h-6 w-full" /><Skeleton className="h-6 w-full" /></div> : null}
          <QueryErrorState query={meta} title="Não foi possível carregar a navegação" />
          {meta.data && <NavTree meta={meta.data} current={current} />}
        </aside>
        <main>{children}</main>
      </div>
    </div>
  );
}
