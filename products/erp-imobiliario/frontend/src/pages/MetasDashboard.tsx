/**
 * MetasDashboard — the new Metas domain landing page (Phase 7 dashboard).
 *
 * Coexists with the legacy /metas individual-goals page at `Metas.tsx`.
 * Route: /metas/dashboard. Role-aware via RLS.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Info, Trophy, Target, Users, Award, TrendingUp } from 'lucide-react';
import {
  useEquipes, usePeriodos, useCascadeResumo, useRankings, useMetasConfig,
  useMetasEquipe,
} from '@/hooks/useMetasDomain';
import { RankBadge, ScorePill, ProgressRing } from '@noctusai/lib/design-system';

function InfoIcon({ title }: { title: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Info className="h-3.5 w-3.5 inline-block ml-1 text-muted-foreground cursor-help" />
        </TooltipTrigger>
        <TooltipContent className="max-w-xs text-sm">{title}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function formatBRL(n: number) {
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
}

export default function MetasDashboard() {
  const navigate = useNavigate();
  const [periodoId, setPeriodoId] = useState<string | null>(null);

  const equipesQ = useEquipes();
  const periodosQ = usePeriodos();
  const configQ = useMetasConfig();
  const cascade = useCascadeResumo(periodoId);
  const rankings = useRankings();

  const openPeriodos = (periodosQ.data ?? []).filter(p => p.status !== 'fechado');
  if (openPeriodos[0] && !periodoId) setPeriodoId(openPeriodos[0].id);

  return (
    <div className="p-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            Metas — Desempenho
            <InfoIcon title="Sistema de metas e gamificação: captações, visitas, vendas, locações, pontuação individual e por equipe." />
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Desempenho em tempo real — metas da empresa, equipes, ranking individual.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate('/metas')}>
            Metas individuais
          </Button>
          <Button variant="outline" onClick={() => navigate('/metas/ranking')}>
            <Trophy className="w-4 h-4 mr-2" /> Ranking completo
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
              Meta da empresa
              <InfoIcon title="VGV-alvo definido pelo proprietário para o período." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {cascade.data ? formatBRL(cascade.data.meta_empresa) : '—'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
              Alocado em equipes
              <InfoIcon title="Soma das metas de VGV distribuídas entre equipes." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {cascade.data ? formatBRL(cascade.data.alocado_em_equipes) : '—'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
              Saldo a alocar
              <InfoIcon title="Quanto da meta ainda não foi distribuído." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-emerald-600">
              {cascade.data ? formatBRL(cascade.data.saldo_a_alocar) : '—'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center">
              Equipes ativas
              <InfoIcon title="Total de equipes ativas no período." />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold flex items-center gap-2">
              <Users className="w-5 h-5 text-muted-foreground" />
              {equipesQ.data?.length ?? 0}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Award className="w-5 h-5" />
            Ranking
            <InfoIcon title="Três visões: Pontos (atividade), VGV (vendas em R$), Score Unificado (combinação)." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="unificado">
            <TabsList>
              <TabsTrigger value="unificado">
                <TrendingUp className="w-4 h-4 mr-1" /> Unificado
              </TabsTrigger>
              <TabsTrigger value="pontos">
                <Target className="w-4 h-4 mr-1" /> Pontos
              </TabsTrigger>
              <TabsTrigger value="vgv">VGV</TabsTrigger>
            </TabsList>

            {(['unificado', 'pontos', 'vgv'] as const).map(view => (
              <TabsContent key={view} value={view}>
                {rankings.isLoading && <p className="text-muted-foreground">Carregando...</p>}
                {rankings.data && (
                  <ul className="divide-y">
                    {rankings.data[view].slice(0, 10).map((r) => (
                      <li key={r.corretor_id} className="py-2 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <RankBadge rank={r.rank} size="sm" />
                          <span className="font-medium">{r.corretor_id.slice(0, 8)}…</span>
                        </div>
                        {view === 'vgv' ? (
                          <span className="text-sm tabular-nums">{formatBRL(r.metric)}</span>
                        ) : view === 'unificado' ? (
                          <ScorePill value={r.metric} precision={1} />
                        ) : (
                          <span className="text-sm tabular-nums">{r.metric.toFixed(1)}</span>
                        )}
                      </li>
                    ))}
                    {rankings.data[view].length === 0 && (
                      <li className="py-4 text-center text-muted-foreground text-sm">
                        Nenhum evento pontuado ainda.
                      </li>
                    )}
                  </ul>
                )}
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Equipes</CardTitle>
        </CardHeader>
        <CardContent>
          {equipesQ.data && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {equipesQ.data.map(e => (
                <Card
                  key={e.id}
                  className="cursor-pointer hover:shadow-md transition"
                  onClick={() => navigate(`/metas/equipes/${e.id}`)}
                  style={e.cor ? { borderLeft: `4px solid ${e.cor}` } : undefined}
                >
                  <CardContent className="pt-4">
                    <div className="font-semibold text-lg">{e.nome}</div>
                    <div className="text-xs text-muted-foreground mt-1">
                      {e.ativo ? 'Ativa' : 'Desativada'}
                    </div>
                  </CardContent>
                </Card>
              ))}
              {equipesQ.data.length === 0 && (
                <p className="text-sm text-muted-foreground col-span-3">
                  Nenhuma equipe criada ainda.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {configQ.data && (
        <p className="text-xs text-muted-foreground">
          Score unificado = Pontos × {configQ.data.peso_pontos} + (VGV ÷ R${' '}
          {Number(configQ.data.vgv_por_ponto).toLocaleString('pt-BR')}) × {configQ.data.peso_vgv}.
          Ajustável em Configurações.
        </p>
      )}
    </div>
  );
}
