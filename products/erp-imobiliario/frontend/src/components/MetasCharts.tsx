/**
 * MetasCharts — Phase 7 visual polish for the Metas dashboard.
 *
 * Three charts using recharts (already in ERP deps v2.15.4):
 *  - MetaVsRealizadoChart  — bar chart comparing each team's meta VGV
 *    vs realized VGV for the selected period.
 *  - TopAgentsBarChart     — horizontal bar of the top 10 agents,
 *    switchable between pontos / VGV / unificado.
 *  - EquipeProgressRings   — per-team achievement rings using the
 *    shared `ProgressRing` gamification primitive.
 *
 * All three are role-aware via RLS (data hooks filter server-side).
 */
import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer,
  CartesianGrid, Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ProgressRing } from '@noctusai/lib/design-system';
import {
  useEquipes, useMetasEquipe, useRankings,
  type Rankings, type MetaEquipe, type Equipe,
} from '@/hooks/useMetasDomain';

const BRL_COMPACT = new Intl.NumberFormat('pt-BR', {
  notation: 'compact', maximumFractionDigits: 1,
});
const fmtBRL = (n: number) => `R$ ${BRL_COMPACT.format(n)}`;

// ── Team meta vs realized ─────────────────────────────────────────

export function MetaVsRealizadoChart({ periodoId }: { periodoId: string | null }) {
  const equipesQ = useEquipes();
  const metasQ = useMetasEquipe(periodoId ?? undefined);
  // Rankings scoped to each equipe give us realized VGV; fetch platform-wide
  // rankings once and group on the client — same data, fewer round-trips.
  const rankingsQ = useRankings();

  const data = useMemo(() => {
    const equipes: Equipe[] = equipesQ.data ?? [];
    const metas: MetaEquipe[] = metasQ.data ?? [];
    const vgvByCorretor = new Map<string, number>();
    (rankingsQ.data?.vgv ?? []).forEach(r => vgvByCorretor.set(r.corretor_id, r.metric));

    return equipes.map(e => {
      const meta = metas.find(m => m.equipe_id === e.id)?.valor_meta ?? 0;
      // Realized = sum of each team member's VGV metric (equipe_id_snapshot
      // on the ranking row preserves attribution across mid-period moves).
      const realizado = (rankingsQ.data?.vgv ?? [])
        .filter(r => r.equipe_id_snapshot === e.id)
        .reduce((acc, r) => acc + r.metric, 0);
      return {
        nome: e.nome,
        meta,
        realizado,
        pct: meta > 0 ? Math.round((realizado / meta) * 100) : 0,
        cor: e.cor ?? '#6366f1',
      };
    });
  }, [equipesQ.data, metasQ.data, rankingsQ.data]);

  if (!data.length) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Meta vs realizado — por equipe</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="nome" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={fmtBRL} tick={{ fontSize: 12 }} />
              <RTooltip
                formatter={(v: number) => fmtBRL(v)}
                cursor={{ fill: 'rgba(99,102,241,0.06)' }}
              />
              <Bar dataKey="meta" fill="#c7d2fe" radius={[4, 4, 0, 0]} name="Meta" />
              <Bar dataKey="realizado" radius={[4, 4, 0, 0]} name="Realizado">
                {data.map((d, i) => (
                  <Cell key={i} fill={d.cor} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Top 10 agents bar chart ───────────────────────────────────────

export function TopAgentsBarChart({ view }: { view: 'pontos' | 'vgv' | 'unificado' }) {
  const rankingsQ = useRankings();
  const rows = (rankingsQ.data?.[view] ?? []).slice(0, 10);

  const data = rows.map(r => ({
    nome: `#${r.rank}`,
    label: r.corretor_id.slice(0, 8),
    value: r.metric,
    color:
      r.rank === 1 ? '#eab308' :
      r.rank === 2 ? '#94a3b8' :
      r.rank === 3 ? '#b45309' :
      '#6366f1',
  }));

  if (!data.length) return null;

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            type="number"
            tickFormatter={v => view === 'vgv' ? fmtBRL(v) : Number(v).toFixed(0)}
            tick={{ fontSize: 12 }}
          />
          <YAxis type="category" dataKey="nome" tick={{ fontSize: 12 }} width={36} />
          <RTooltip
            formatter={(v: number) => view === 'vgv' ? fmtBRL(v) : Number(v).toFixed(1)}
            labelFormatter={(_, p: any) => p?.[0]?.payload?.label ?? ''}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {data.map((d, i) => <Cell key={i} fill={d.color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Team progress rings ───────────────────────────────────────────

export function EquipeProgressRings({ periodoId }: { periodoId: string | null }) {
  const equipesQ = useEquipes();
  const metasQ = useMetasEquipe(periodoId ?? undefined);
  const rankingsQ = useRankings();

  const rings = useMemo(() => {
    const equipes = equipesQ.data ?? [];
    const metas = metasQ.data ?? [];
    return equipes.map(e => {
      const meta = metas.find(m => m.equipe_id === e.id)?.valor_meta ?? 0;
      const realizado = (rankingsQ.data?.vgv ?? [])
        .filter(r => r.equipe_id_snapshot === e.id)
        .reduce((acc, r) => acc + r.metric, 0);
      const pct = meta > 0 ? Math.round((realizado / meta) * 100) : 0;
      return { id: e.id, nome: e.nome, pct, cor: e.cor };
    });
  }, [equipesQ.data, metasQ.data, rankingsQ.data]);

  if (!rings.length) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
      {rings.map(r => (
        <div key={r.id} className="flex flex-col items-center gap-1">
          <ProgressRing value={r.pct} label={`${r.pct}%`} size={72} />
          <span
            className="text-xs font-medium truncate max-w-[96px]"
            style={r.cor ? { color: r.cor } : undefined}
          >
            {r.nome}
          </span>
        </div>
      ))}
    </div>
  );
}
