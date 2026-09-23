/**
 * `<Leads/>` — Website > Leads (`/admin/website/leads`).
 *
 * Contract: `src/website/docs/15-api-contract.md` §3 (list/stats endpoints)
 * / §6 ("Leads": stats strip, filtered+paginated table, CSV export
 * admin-only). Row click routes to `/admin/website/leads/:id`
 * (`LeadDetail.tsx`) for the activity timeline + quick actions.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, Mail, MessageCircle, TrendingUp, Users } from 'lucide-react';
import {
  Badge, Button, EmptyState, ErrorState, FilterBar, Skeleton, StatTile, StatTileRow, TableSkeleton,
} from '@noctusai/lib/design-system';
import type { FilterChip } from '@noctusai/lib/design-system';
import { useAuth } from '../../../lib/auth-context';
import {
  SOURCE_LABEL, STAGE_LABEL, formatDate, useExportLeadsCsv, useWebsiteLeadStats, useWebsiteLeads,
  type LeadSource, type LeadStage,
} from '../../../lib/website';

const STAGE_OPTIONS: LeadStage[] = ['novo', 'contatado', 'qualificado', 'proposta', 'ganho', 'perdido', 'descartado'];
const SOURCE_OPTIONS: LeadSource[] = ['waitlist', 'brief', 'contact', 'signup_intent'];
const PAGE_SIZE = 50;

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function StatsStrip() {
  const { data, isPending, isFetching, error } = useWebsiteLeadStats();
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) {
    return (
      <StatTileRow>
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}
      </StatTileRow>
    );
  }
  if (error && !data) return <p role="alert" className="text-sm text-destructive">{error.message}</p>;
  if (!data) return null;

  const topSource = Object.entries(data.by_source).sort((a, b) => b[1] - a[1])[0];

  return (
    <StatTileRow className={isRefreshing ? 'opacity-90' : undefined}>
      <StatTile icon={Users} label="Novos hoje" value={data.new_today} />
      <StatTile icon={TrendingUp} label="Novos (7 dias)" value={data.new_7d} />
      <StatTile
        icon={MessageCircle}
        label="Principal origem"
        value={topSource ? (SOURCE_LABEL[topSource[0] as LeadSource] ?? topSource[0]) : '—'}
        hint={topSource ? `${topSource[1]} leads` : undefined}
      />
      <StatTile
        icon={Mail}
        label="Eventos (7 dias)"
        value={Object.values(data.events_7d).reduce((a, b) => a + b, 0)}
      />
    </StatTileRow>
  );
}

export function Leads() {
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const [stage, setStage] = useState<LeadStage | ''>('');
  const [source, setSource] = useState<LeadSource | ''>('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const filters = { stage, source, q: search, limit: PAGE_SIZE, offset };
  const { data, isPending, isFetching, error } = useWebsiteLeads(filters);
  const exportCsv = useExportLeadsCsv();

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const total = data?.total ?? 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const chips: FilterChip[] = [];
  if (stage) chips.push({ key: 'stage', label: `Estágio: ${STAGE_LABEL[stage]}`, onClear: () => { setStage(''); setOffset(0); } });
  if (source) chips.push({ key: 'source', label: `Origem: ${SOURCE_LABEL[source]}`, onClear: () => { setSource(''); setOffset(0); } });
  if (search) chips.push({ key: 'q', label: `Busca: "${search}"`, onClear: () => { setSearch(''); setOffset(0); } });

  function clearAll() {
    setStage(''); setSource(''); setSearch(''); setOffset(0);
  }

  async function handleExport() {
    const blob = await exportCsv.mutateAsync(filters);
    downloadBlob(blob, `leads-${new Date().toISOString().slice(0, 10)}.csv`);
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Leads</h1>
          <p className="mt-1 text-muted-foreground">Waitlist, briefings e contatos do site</p>
        </div>
        {isAdmin && (
          <Button variant="outline" size="sm" disabled={exportCsv.isPending} onClick={handleExport}>
            <Download className="mr-1.5 h-4 w-4" />
            {exportCsv.isPending ? 'Exportando…' : 'Exportar CSV'}
          </Button>
        )}
      </header>

      {exportCsv.error && <p role="alert" className="text-sm text-destructive">{exportCsv.error.message}</p>}

      <StatsStrip />

      <FilterBar chips={chips} onClearAll={chips.length > 0 ? clearAll : undefined}>
        <select
          aria-label="Filtrar por estágio"
          className="rounded-md border border-input bg-background px-2 py-1 text-sm"
          value={stage}
          onChange={(e) => { setStage(e.target.value as LeadStage | ''); setOffset(0); }}
        >
          <option value="">Todos os estágios</option>
          {STAGE_OPTIONS.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
        </select>
        <select
          aria-label="Filtrar por origem"
          className="rounded-md border border-input bg-background px-2 py-1 text-sm"
          value={source}
          onChange={(e) => { setSource(e.target.value as LeadSource | ''); setOffset(0); }}
        >
          <option value="">Todas as origens</option>
          {SOURCE_OPTIONS.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
        </select>
        <input
          type="search"
          aria-label="Buscar por nome, e-mail, telefone ou empresa"
          placeholder="Buscar…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
          className="min-w-[200px] flex-1 rounded-md border border-input bg-background px-2.5 py-1 text-sm"
        />
      </FilterBar>

      {showSkeleton ? (
        <TableSkeleton rows={6} columns={6} />
      ) : error && !data ? (
        <ErrorState message={`Não foi possível carregar os leads: ${error.message}`} />
      ) : data && data.data.length === 0 ? (
        <EmptyState message="Nenhum lead encontrado." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card" aria-busy={isRefreshing}>
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="p-2">Nome</th><th>Origem</th><th>Estágio</th><th>Contato</th>
                <th>Consentimento</th><th>Criado em</th>
              </tr>
            </thead>
            <tbody>
              {data?.data.map((lead) => (
                <tr
                  key={lead.id}
                  className="cursor-pointer border-t border-border hover:bg-muted/40"
                  onClick={() => navigate(`/admin/website/leads/${lead.id}`)}
                >
                  <td className="p-2 font-medium text-foreground">{lead.name}</td>
                  <td>{SOURCE_LABEL[lead.source] ?? lead.source}</td>
                  <td><Badge variant="outline">{STAGE_LABEL[lead.stage] ?? lead.stage}</Badge></td>
                  <td>{lead.email ?? lead.phone_e164 ?? '—'}</td>
                  <td>
                    <Badge variant={lead.consent.marketing ? 'default' : 'muted'}>
                      {lead.consent.marketing ? 'consentiu' : 'sem consentimento'}
                    </Badge>
                  </td>
                  <td>{formatDate(lead.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center gap-2 text-sm">
        <Button size="sm" variant="outline" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Anterior
        </Button>
        <span>Página {page} de {lastPage}</span>
        <Button size="sm" variant="outline" disabled={page >= lastPage} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Próxima
        </Button>
      </div>
    </div>
  );
}

export default Leads;
