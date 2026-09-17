/**
 * `<WhatsAppConnectionsPage/>` — the canonical UI for
 * `createWhatsAppConnectionsHooks`: a list of WAHA connection "lines" +
 * "Nova conexão" + per-line detail (status, QR, actions).
 *
 * Lifted from `products/social-wiring`'s `Conexoes.tsx` +
 * `ConnectionDetailDialog.tsx` as a PURE ADDITION — social-wiring keeps its
 * own richer copy (marca scoping, auto-reply, bound chats) for now; this
 * organ ships the generic connection-lifecycle subset only.
 *
 * Composable: `WhatsAppConnectionsPage` is the batteries-included page, but
 * `CreateConnectionDialog` and `ConnectionDetailDialog` are also exported
 * standalone for a product that wants its own list layout.
 *
 * Usage:
 * ```tsx
 * import { createWhatsAppConnectionsHooks, WhatsAppConnectionsPage } from '@noctusai/lib/components';
 * import { api } from '@/lib/api';
 *
 * const wa = createWhatsAppConnectionsHooks(api);
 * <WhatsAppConnectionsPage
 *   hooks={wa}
 *   emptyState={<p>Integração futura — nenhuma conexão pareada.</p>}
 * />
 * ```
 */
import * as React from 'react';
import { AlertCircle, Plus, RefreshCw, Trash2 } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { Skeleton } from '../../design-system/ui/Skeleton';
import { ApiError } from '../../api';
import type {
  WhatsAppConnectionLine,
  WhatsAppConnectionsHooks,
} from '../../whatsapp';
import { CreateConnectionDialog } from './CreateConnectionDialog';
import { ConnectionDetailDialog } from './ConnectionDetailDialog';

/** Best-effort status → badge mapping, mirrors social-wiring's own copy. */
function StatusBadge({ hooks, connectionId }: { hooks: WhatsAppConnectionsHooks; connectionId: string }) {
  const { data } = hooks.useConnectionStatus(connectionId);
  if (data?.paired) {
    return (
      <Badge variant="default" data-testid={`wa-status-${connectionId}`}>
        {data.status ?? 'WORKING'}
      </Badge>
    );
  }
  return (
    <Badge variant="muted" data-testid={`wa-status-${connectionId}`}>
      {data?.status ?? 'desconectado'}
    </Badge>
  );
}

function ConnectionRow({
  line,
  hooks,
  onOpen,
  onDelete,
  deleting,
}: {
  line: WhatsAppConnectionLine;
  hooks: WhatsAppConnectionsHooks;
  onOpen: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <li
      className="flex items-center justify-between gap-3 rounded-md border border-border p-3"
      data-testid={`wa-connection-row-${line.id}`}
    >
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-2 text-left"
        onClick={onOpen}
      >
        <span className="truncate text-sm font-medium">{line.label}</span>
        <StatusBadge hooks={hooks} connectionId={line.id} />
      </button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={`Remover ${line.label}`}
        onClick={onDelete}
        disabled={deleting}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </li>
  );
}

export interface WhatsAppConnectionsPageProps {
  hooks: WhatsAppConnectionsHooks;
  className?: string;
  /** Heading text. Default "Conexões WhatsApp". */
  title?: string;
  /** Rendered above the list — e.g. an availability notice. */
  banner?: React.ReactNode;
  /**
   * Rendered instead of the default empty-state copy when there are zero
   * connections, e.g. `<p>Integração futura — nenhuma conexão pareada.</p>`.
   */
  emptyState?: React.ReactNode;
}

export function WhatsAppConnectionsPage({
  hooks,
  className,
  title = 'Conexões WhatsApp',
  banner,
  emptyState,
}: WhatsAppConnectionsPageProps) {
  const { data, error, showSkeleton, isRefreshing, refetch } = hooks.useConnections();
  const mutations = hooks.useConnectionMutations();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [detailId, setDetailId] = React.useState<string | null>(null);

  const detailLine = data?.find((l) => l.id === detailId) ?? null;

  const handleDelete = (line: WhatsAppConnectionLine) => {
    if (!window.confirm(`Excluir a conexão "${line.label}"?`)) return;
    mutations.remove.mutate(line.id);
  };

  return (
    <div className={className} data-testid="whatsapp-connections-page">
      {banner}

      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold">{title}</h2>
          {isRefreshing && (
            <RefreshCw className="h-3.5 w-3.5 animate-spin text-muted-foreground" data-testid="wa-refreshing" />
          )}
        </div>
        <Button type="button" size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          Nova conexão
        </Button>
      </div>

      {showSkeleton && (
        <div aria-busy="true" className="grid gap-2">
          <Skeleton height={56} announce label="Carregando conexões" />
          <Skeleton height={56} announce={false} />
        </div>
      )}

      {!showSkeleton && error && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <span className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4" />
            {error instanceof ApiError && error.status === 503
              ? 'WhatsApp (WAHA) não configurado neste servidor.'
              : error instanceof Error
                ? error.message
                : 'Falha ao carregar as conexões.'}
          </span>
          <Button type="button" variant="outline" size="sm" onClick={() => refetch()}>
            Tentar de novo
          </Button>
        </div>
      )}

      {!showSkeleton && !error && data && data.length === 0 && (
        <div data-testid="wa-empty-state">
          {emptyState ?? (
            <p className="text-sm text-muted-foreground">
              Nenhuma conexão. Crie a primeira para conectar um número de WhatsApp.
            </p>
          )}
        </div>
      )}

      {!showSkeleton && !error && data && data.length > 0 && (
        <ul className="grid gap-2">
          {data.map((line) => (
            <ConnectionRow
              key={line.id}
              line={line}
              hooks={hooks}
              onOpen={() => setDetailId(line.id)}
              onDelete={() => handleDelete(line)}
              deleting={mutations.remove.isPending}
            />
          ))}
        </ul>
      )}

      <CreateConnectionDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        mutations={mutations}
        onCreated={(line) => setDetailId(line.id)}
      />

      {detailLine && (
        <ConnectionDetailDialog
          open={!!detailLine}
          onClose={() => setDetailId(null)}
          line={detailLine}
          hooks={hooks}
        />
      )}
    </div>
  );
}
