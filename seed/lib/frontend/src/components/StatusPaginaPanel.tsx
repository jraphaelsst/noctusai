/**
 * `<StatusPaginaPanel/>` — shared admin organ for **page-visibility** control.
 *
 * Each product schema carries a `status_pagina` table whose rows gate route
 * visibility (`producao` → everyone · `desenvolvimento` → dev/owner only ·
 * `desativado` → hidden). The read side (nav filtering) is the sibling
 * `usePageStatus` hook in `../page-status`. This organ is the **write** side:
 * an owner/admin/dev surface that lists every page and lets the operator
 * change each page's status via a selector — no raw SQL, no script.
 *
 * It is deliberately **product-agnostic**: it takes the consuming product's
 * own `api` client (structurally `{ get, patch }`, satisfied by the seed
 * `ApiClient`) so it never reaches into any product-specific module. Gating
 * (owner/admin/dev) is the CONSUMER's responsibility — mount the panel only
 * where the caller has already established the operator is authorized; the
 * backend enforces the 403 regardless.
 *
 * Contract (built by the backend engineer to match, do not deviate):
 *   GET   /api/status-paginas        → 200 StatusPaginaRow[]  (admin/dev only)
 *   PATCH /api/status-paginas/{id}   body { status } → 200 the updated row
 *
 * Usage:
 * ```tsx
 * import { StatusPaginaPanel } from '@noctusai/lib';
 * import { api } from '@/lib/api';           // (or @noctusai/seed/infra)
 *
 * <StatusPaginaPanel api={api} enabled={isAdminOrDev} />
 * ```
 *
 * Requires a `QueryClientProvider` in the host tree (the seed framework
 * `createProductApp` provides one — same wiring the sibling `usePageStatus`
 * relies on).
 */
import * as React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';

import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { cn } from '../utils';

/** The three visibility states a page can hold. */
export type StatusPaginaStatus = 'producao' | 'desenvolvimento' | 'desativado';

/** A single page-visibility row as returned by `GET /api/status-paginas`. */
export interface StatusPaginaRow {
  id: string;
  nome_pagina: string;
  status: StatusPaginaStatus;
  descricao?: string | null;
  tipo_pagina?: string | null;
  updated_at?: string | null;
}

/**
 * The minimal fetch-client shape the panel needs. The seed `ApiClient`
 * (`@noctusai/lib/api`) satisfies this structurally, so any product can pass
 * its own `api` client directly.
 */
export interface StatusPaginaApi {
  get: <T = any>(path: string, params?: Record<string, any>) => Promise<T>;
  patch: <T = any>(path: string, body?: unknown) => Promise<T>;
}

export interface StatusPaginaPanelProps {
  /** The product's api client (from `@/lib/api` or `@noctusai/seed/infra`). */
  api: StatusPaginaApi;
  /** Whether the underlying query should run (gate to owner/admin/dev). Default `true`. */
  enabled?: boolean;
  /** Section title. Default `"Visibilidade de páginas"`. */
  title?: string;
  /** Optional subtitle under the title. A sensible default is provided. */
  description?: string;
  /** Called after a successful status change (e.g. refresh a parent stat). */
  onChanged?: (row: StatusPaginaRow) => void;
  /** Called when a status change fails (in addition to the toast). */
  onError?: (err: unknown) => void;
}

export const STATUS_PAGINAS_QUERY_KEY = ['status-paginas'] as const;

const STATUS_ORDER: StatusPaginaStatus[] = [
  'producao',
  'desenvolvimento',
  'desativado',
];

const STATUS_META: Record<
  StatusPaginaStatus,
  { label: string; dot: string; badgeClass: string }
> = {
  producao: {
    label: 'Produção',
    dot: 'bg-green-500',
    badgeClass:
      'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400',
  },
  desenvolvimento: {
    label: 'Desenvolvimento',
    dot: 'bg-amber-500',
    badgeClass:
      'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  },
  desativado: {
    label: 'Desativado',
    dot: 'bg-slate-400',
    badgeClass:
      'border-slate-400/40 bg-slate-400/10 text-slate-600 dark:text-slate-400',
  },
};

const SELECT_CLASS =
  'h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground ' +
  'focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:cursor-not-allowed disabled:opacity-60';

// ── Card shell (the lib design-system has no generic Card; build a token-aligned
// shell so the organ renders consistently inside every product's tailwind context).
function PanelShell({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <section className="rounded-lg border border-border bg-card text-card-foreground shadow-sm">
      <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <h3 className="text-base font-semibold leading-none tracking-tight">
            {title}
          </h3>
          {description && (
            <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {action}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function StatusPaginaPanel(
  props: StatusPaginaPanelProps,
): React.ReactElement {
  const {
    api,
    enabled = true,
    title = 'Visibilidade de páginas',
    description = 'Controle quais páginas ficam visíveis. Produção: todos · Desenvolvimento: apenas dev/owner · Desativado: oculto.',
    onChanged,
    onError,
  } = props;

  const queryClient = useQueryClient();

  const query = useQuery<StatusPaginaRow[]>({
    queryKey: STATUS_PAGINAS_QUERY_KEY,
    queryFn: () => api.get<StatusPaginaRow[]>('/api/status-paginas'),
    enabled,
  });

  const mutation = useMutation<
    StatusPaginaRow,
    unknown,
    { id: string; status: StatusPaginaStatus }
  >({
    mutationFn: ({ id, status }) =>
      api.patch<StatusPaginaRow>(`/api/status-paginas/${id}`, { status }),
    onSuccess: (row) => {
      void queryClient.invalidateQueries({ queryKey: STATUS_PAGINAS_QUERY_KEY });
      toast.success(
        `Página "${row.nome_pagina}" agora está em ${STATUS_META[row.status].label}.`,
      );
      onChanged?.(row);
    },
    onError: (err) => {
      const message =
        err instanceof Error ? err.message : 'Falha ao alterar status da página.';
      toast.error('Erro ao alterar status da página', { description: message });
      onError?.(err);
    },
  });

  const pendingId = mutation.isPending
    ? (mutation.variables?.id ?? null)
    : null;

  function handleChange(row: StatusPaginaRow, next: StatusPaginaStatus): void {
    if (next === row.status) return;
    mutation.mutate({ id: row.id, status: next });
  }

  // ── Loading ────────────────────────────────────────────────────────────
  if (query.isLoading) {
    return (
      <PanelShell title={title} description={description}>
        <div
          aria-busy="true"
          className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando páginas…
        </div>
      </PanelShell>
    );
  }

  // ── Error ──────────────────────────────────────────────────────────────
  if (query.isError) {
    const message =
      query.error instanceof Error
        ? query.error.message
        : 'Não foi possível carregar as páginas.';
    return (
      <PanelShell
        title={title}
        description={description}
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => void query.refetch()}
          >
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Tentar novamente
          </Button>
        }
      >
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{message}</span>
        </div>
      </PanelShell>
    );
  }

  const rows = query.data ?? [];

  // ── Empty ──────────────────────────────────────────────────────────────
  if (rows.length === 0) {
    return (
      <PanelShell title={title} description={description}>
        <p className="py-8 text-center text-sm text-muted-foreground">
          Nenhuma página cadastrada ainda.
        </p>
      </PanelShell>
    );
  }

  // ── Success ────────────────────────────────────────────────────────────
  return (
    <PanelShell title={title} description={description}>
      <ul className="divide-y divide-border rounded-md border border-border">
        {rows.map((row) => {
          const meta = STATUS_META[row.status];
          const busy = pendingId === row.id;
          return (
            <li
              key={row.id}
              className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn('h-2 w-2 flex-shrink-0 rounded-full', meta.dot)}
                    aria-hidden="true"
                  />
                  <p className="truncate font-medium">{row.nome_pagina}</p>
                  {row.tipo_pagina && (
                    <Badge variant="outline" className="font-normal">
                      {row.tipo_pagina}
                    </Badge>
                  )}
                  <Badge
                    variant="outline"
                    className={cn('font-medium', meta.badgeClass)}
                  >
                    {meta.label}
                  </Badge>
                </div>
                {row.descricao && (
                  <p className="mt-1 truncate text-xs text-muted-foreground">
                    {row.descricao}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2">
                {busy && (
                  <Loader2
                    className="h-4 w-4 animate-spin text-muted-foreground"
                    aria-label="Salvando"
                  />
                )}
                <label className="sr-only" htmlFor={`status-${row.id}`}>
                  Status de {row.nome_pagina}
                </label>
                <select
                  id={`status-${row.id}`}
                  className={SELECT_CLASS}
                  value={row.status}
                  disabled={busy}
                  onChange={(e) =>
                    handleChange(row, e.target.value as StatusPaginaStatus)
                  }
                >
                  {STATUS_ORDER.map((s) => (
                    <option key={s} value={s}>
                      {STATUS_META[s].label}
                    </option>
                  ))}
                </select>
              </div>
            </li>
          );
        })}
      </ul>
    </PanelShell>
  );
}

StatusPaginaPanel.displayName = 'StatusPaginaPanel';
