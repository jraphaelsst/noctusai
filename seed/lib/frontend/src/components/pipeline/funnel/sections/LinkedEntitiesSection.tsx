/**
 * `LinkedEntitiesSection` — the `linked` section kind: rows of ANOTHER entity tied to the card
 * (compradores, orçamentos, contratos …) fetched from a schema-declared endpoint. Four states:
 * skeleton (first load only) · error (QueryErrorState-style, before empty) · empty (what goes here)
 * · rows. A refetch over existing rows only shows a refreshing hint — never blanks them.
 */
import { useQuery } from '@tanstack/react-query';

import type { PipelineApi } from '../../types';
import type { FunnelCard, FunnelLinkedColumn } from '../types';

export interface LinkedEntitiesSectionProps<TCard extends FunnelCard> {
  card: TCard;
  api: Pick<PipelineApi, 'get'>;
  endpoint: string;
  columns: FunnelLinkedColumn[];
  rowId?: (row: Record<string, unknown>) => string;
  onOpen?: (row: Record<string, unknown>, card: TCard) => void;
  empty?: string;
  /** Query-key root so the cache entry is addressable (`[root, 'linked', endpoint]`). */
  queryKey: string;
}

const cell = (col: FunnelLinkedColumn, row: Record<string, unknown>) => {
  const v = row[col.key];
  if (v === null || v === undefined || v === '') return '—';
  return col.format ? col.format(v, row) : String(v);
};

export function LinkedEntitiesSection<TCard extends FunnelCard>({
  card,
  api,
  endpoint,
  columns,
  rowId = (r) => String(r.id ?? ''),
  onOpen,
  empty = 'Nada vinculado a este cartão ainda.',
  queryKey,
}: LinkedEntitiesSectionProps<TCard>) {
  const q = useQuery({
    queryKey: [queryKey, 'linked', endpoint],
    queryFn: async () => {
      const res = await api.get<unknown>(endpoint);
      const body = res && typeof res === 'object' && 'items' in res ? (res as { items: unknown }).items : res;
      const data = res && typeof res === 'object' && 'data' in res ? (res as { data: unknown }).data : body;
      return (Array.isArray(data) ? data : Array.isArray(body) ? body : []) as Record<string, unknown>[];
    },
  });

  if (q.isPending && !q.data) {
    return <div className="h-24 animate-pulse rounded bg-muted" role="status" aria-label="Carregando vínculos" />;
  }
  if (q.error) {
    return (
      <div role="alert" className="space-y-2 text-sm">
        <p className="text-destructive">Não foi possível carregar os vínculos. Verifique a conexão e tente de novo.</p>
        <button type="button" className="underline" onClick={() => void q.refetch()}>
          Tentar de novo
        </button>
      </div>
    );
  }
  const rows = q.data ?? [];
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;

  return (
    <div className="overflow-x-auto" aria-busy={q.isFetching}>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
            {columns.map((c) => (
              <th key={c.key} scope="col" className="py-2 pr-4 font-semibold">{c.label}</th>
            ))}
            {onOpen && <th scope="col" className="sr-only">Ações</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowId(row) || i} className="border-b last:border-0">
              {columns.map((c, ci) => (
                <td key={c.key} className="py-2 pr-4">
                  {onOpen && ci === 0 ? (
                    <button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => onOpen(row, card)}>
                      {cell(c, row)}
                    </button>
                  ) : (
                    cell(c, row)
                  )}
                </td>
              ))}
              {onOpen && <td />}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
