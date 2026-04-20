/**
 * /metas/equipes/:id — leader drill-down.
 *
 * KPI cards (meta VGV / realizado / % atingimento / membros) + ranking
 * per-member + member-quota inline editor.
 */
import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  ArrowLeft, Target, TrendingUp, Users, Trophy, Crown,
} from 'lucide-react';
import {
  useEquipe,
  useEquipeMembros,
  useEquipes,
  useMetasEquipe,
  usePeriodos,
  useRankings,
} from '@/hooks/useMetasDomain';

function brl(n: number): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(n || 0);
}

export default function MetasEquipeDrilldown() {
  const { id } = useParams<{ id: string }>();
  const { data: equipe } = useEquipe(id ?? null);
  const { data: equipes = [] } = useEquipes();
  const { data: membros = [] } = useEquipeMembros(id ?? null);
  const { data: periodos = [] } = usePeriodos();

  const [periodoId, setPeriodoId] = useState<string | null>(null);
  useEffect(() => {
    if (!periodoId && periodos.length > 0) {
      const aberto = periodos.find((p: any) => p.status === 'aberto') ?? periodos[0];
      setPeriodoId(aberto.id);
    }
  }, [periodos, periodoId]);

  const periodo = periodos.find((p: any) => p.id === periodoId);

  const { data: metasEquipeAll = [] } = useMetasEquipe(periodoId ?? undefined);
  const metaVgv = metasEquipeAll.find((m: any) => m.equipe_id === id && m.categoria === 'vgv');

  const { data: rankings } = useRankings({
    equipe_id: id,
    data_inicio: periodo?.data_inicio,
    data_fim: periodo?.data_fim,
  });

  const fallbackEquipe = equipes.find((e: any) => e.id === id);
  const e = equipe ?? fallbackEquipe;

  const vgvMeta = metaVgv?.valor_meta ?? 0;
  const vgvRealizado = (rankings?.vgv ?? []).reduce((acc, r) => acc + (Number(r.vgv) || 0), 0);
  const atingimento = vgvMeta > 0 ? Math.round((vgvRealizado / vgvMeta) * 100) : 0;
  const liderRow = (rankings?.unificado ?? [])[0];

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8 lg:py-10">
      <Link
        to="/metas/dashboard"
        className="mb-4 inline-flex items-center gap-1 text-sm text-primary hover:underline"
      >
        <ArrowLeft className="h-4 w-4" />
        Voltar ao painel
      </Link>

      <div className="mb-6 flex items-center gap-2">
        <div
          className="h-4 w-4 rounded-full"
          style={{ background: e?.cor || '#999' }}
        />
        <h1 className="text-2xl font-bold text-foreground">{e?.nome ?? 'Equipe'}</h1>
        {!e?.ativo && e && <Badge variant="outline">inativa</Badge>}
      </div>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="text-base">Período</CardTitle>
        </CardHeader>
        <CardContent>
          <select
            value={periodoId ?? ''}
            onChange={(ev) => setPeriodoId(ev.target.value || null)}
            className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="">Selecione um período…</option>
            {periodos.map((p: any) => (
              <option key={p.id} value={p.id}>
                {p.tipo} — {p.data_inicio} a {p.data_fim} ({p.status})
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          icon={<Target className="h-4 w-4 text-primary" />}
          label="Meta VGV"
          value={brl(vgvMeta)}
        />
        <KpiCard
          icon={<TrendingUp className="h-4 w-4 text-primary" />}
          label="Realizado"
          value={brl(vgvRealizado)}
        />
        <KpiCard
          icon={<Trophy className="h-4 w-4 text-primary" />}
          label="Atingimento"
          value={`${atingimento}%`}
          highlight={atingimento >= 100 ? 'good' : atingimento >= 80 ? 'warn' : atingimento > 0 ? 'neutral' : 'none'}
        />
        <KpiCard
          icon={<Users className="h-4 w-4 text-primary" />}
          label="Membros ativos"
          value={String(membros.length)}
        />
      </div>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Crown className="h-4 w-4" />
            Líder atual do ranking (unificado)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {liderRow ? (
            <p className="text-sm">
              <span className="font-mono">{liderRow.corretor_id.slice(0, 8)}…</span> —{' '}
              score <strong>{liderRow.score_unificado?.toFixed?.(1) ?? '—'}</strong> ·{' '}
              {brl(Number(liderRow.vgv))} · {liderRow.pontos_atividade} pts
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">Sem dados no período.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ranking da equipe</CardTitle>
          <CardDescription>
            Ordenado por score unificado. Pontos = atividades;
            VGV = valor geral de vendas no período.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!rankings?.unificado?.length ? (
            <p className="text-sm text-muted-foreground">Sem eventos neste período.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="border-b text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 text-left">Rank</th>
                    <th className="py-2 text-left">Agente</th>
                    <th className="py-2 text-right">Pontos</th>
                    <th className="py-2 text-right">VGV</th>
                    <th className="py-2 text-right">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {rankings.unificado.map((row) => (
                    <tr key={row.corretor_id} className="border-b last:border-0">
                      <td className="py-2">
                        <Badge variant={row.rank === 1 ? 'default' : 'outline'}>#{row.rank}</Badge>
                      </td>
                      <td className="py-2 font-mono text-xs">{row.corretor_id.slice(0, 12)}…</td>
                      <td className="py-2 text-right">{row.pontos_atividade}</td>
                      <td className="py-2 text-right">{brl(Number(row.vgv))}</td>
                      <td className="py-2 text-right font-medium">{row.score_unificado?.toFixed?.(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function KpiCard({ icon, label, value, highlight }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  highlight?: 'good' | 'warn' | 'neutral' | 'none';
}) {
  const accent = highlight === 'good'
    ? 'text-green-600 dark:text-green-400'
    : highlight === 'warn'
      ? 'text-amber-600 dark:text-amber-400'
      : '';
  return (
    <Card>
      <CardContent className="p-4">
        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
          {icon}
          <span>{label}</span>
        </div>
        <p className={`text-xl font-bold ${accent}`}>{value}</p>
      </CardContent>
    </Card>
  );
}
