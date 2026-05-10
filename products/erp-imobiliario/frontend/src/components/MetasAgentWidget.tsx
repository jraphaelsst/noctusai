/**
 * Agent-scoped Metas widget for the ERP homepage + agent profile pages.
 *
 * Reads the current open period + agent's own ranking row. Shows pontos,
 * VGV, score unificado, and rank in a compact 4-stat strip. Clicking
 * "ver painel" navigates to /metas/dashboard.
 *
 * Consumes `useAuthStore()` to scope `rankings` to the current agent. If
 * the agent has no events in the period, renders a "sem atividade" state.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Target, TrendingUp, Trophy, Sparkles } from 'lucide-react';
import { RankBadge, ScorePill } from '@noctusai/lib/design-system';
import { usePeriodos, useRankings } from '@/hooks/useMetasDomain';
import { useAuthStore } from '@noctusai/seed/infra';
import { useMetaMilestoneToast } from '@/hooks/useMetaMilestoneToast';
import { MetaMilestoneBurst, MetaPulseWrap } from '@/components/MetaMilestoneBurst';

function brl(n: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency', currency: 'BRL', maximumFractionDigits: 0,
  }).format(n || 0);
}

export function MetasAgentWidget({ userId: userIdProp }: { userId?: string } = {}) {
  const { user } = useAuthStore();
  const userId = userIdProp ?? user?.id;
  const { data: periodos = [] } = usePeriodos();
  const openPeriod = periodos.find((p: any) => p.status === 'aberto') ?? periodos[0];
  const { data: rankings } = useRankings({
    data_inicio: openPeriod?.data_inicio,
    data_fim: openPeriod?.data_fim,
  });

  const myRow = rankings?.unificado?.find((r) => r.corretor_id === userId);
  const [burst, setBurst] = useState(false);
  useMetaMilestoneToast(() => setBurst(true));

  if (!openPeriod) {
    return null;
  }

  return (
    <Card className="relative overflow-hidden border-l-4 border-l-primary">
      <MetaMilestoneBurst active={burst} onDone={() => setBurst(false)} />
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <span>Seu Desempenho — período {openPeriod.tipo} (até {openPeriod.data_fim})</span>
          </div>
          {!myRow ? (
            <p className="text-sm text-muted-foreground">
              Sem atividade registrada neste período. Visitas, vendas e captações começarão a contar aqui.
            </p>
          ) : (
            <div className="flex flex-wrap items-baseline gap-4">
              <Stat icon={<Trophy className="h-4 w-4" />} label="Rank">
                <MetaPulseWrap active={burst}>
                  <RankBadge rank={myRow.rank} title="Sua posição atual no ranking unificado" />
                </MetaPulseWrap>
              </Stat>
              <Stat icon={<Target className="h-4 w-4" />} label="Score">
                <MetaPulseWrap active={burst}>
                  <ScorePill value={myRow.score_unificado ?? null} precision={1} />
                </MetaPulseWrap>
              </Stat>
              <Stat icon={<TrendingUp className="h-4 w-4" />} label="VGV">
                <strong>{brl(Number(myRow.vgv))}</strong>
              </Stat>
              <Stat label="Pontos">
                <strong>{myRow.pontos_atividade}</strong>
              </Stat>
            </div>
          )}
        </div>
        <Link
          to="/metas/dashboard"
          className="shrink-0 rounded border border-primary/40 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10"
        >
          Ver painel →
        </Link>
      </CardContent>
    </Card>
  );
}

function Stat({ icon, label, children }: { icon?: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      {icon}
      <span className="text-xs text-muted-foreground">{label}:</span>
      {children}
    </div>
  );
}
