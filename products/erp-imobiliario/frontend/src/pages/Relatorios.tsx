import { useState } from 'react';
import {
  useRankingCorretores,
  useConversaoFunil,
  useAtividadeMensal,
  useExportCSV,
} from '@/hooks/useRelatorios';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { TableSkeleton } from '@/components/ui/page-skeleton';
import {
  Trophy,
  TrendingDown,
  CalendarDays,
  Download,
  ArrowRight,
  BarChart3,
  Users,
  Loader2,
} from 'lucide-react';
import { formatCurrency } from '@/lib/utils';

const formatPercent = (v: number | null) => {
  if (v === null || v === undefined) return '-';
  return `${v.toFixed(1)}%`;
};

export default function Relatorios() {
  const [activeTab, setActiveTab] = useState('ranking');
  const [periodoRanking, setPeriodoRanking] = useState<number>(30);
  const [mesesAtividade, setMesesAtividade] = useState<number>(6);

  const rankingQuery = useRankingCorretores(periodoRanking);
  const conversaoQuery = useConversaoFunil();
  const atividadeQuery = useAtividadeMensal(mesesAtividade);
  const { data: ranking } = rankingQuery;
  const { data: conversao } = conversaoQuery;
  const { data: atividade } = atividadeQuery;
  // isPending && !data — never isLoading — per
  // KB § PATTERNS/frontend/lying-loading-state.md (Shape 5).
  const showRankingSkeleton = rankingQuery.isPending && !rankingQuery.data;
  const showConversaoSkeleton = conversaoQuery.isPending && !conversaoQuery.data;
  const showAtividadeSkeleton = atividadeQuery.isPending && !atividadeQuery.data;
  const { exportCSV } = useExportCSV();

  const [exporting, setExporting] = useState(false);

  const handleExportCSV = async () => {
    setExporting(true);
    try {
      if (activeTab === 'ranking') {
        await exportCSV('ranking-corretores', { periodo: periodoRanking });
      } else if (activeTab === 'conversao') {
        await exportCSV('conversao-funil');
      } else {
        await exportCSV('atividade-mensal', { meses: mesesAtividade });
      }
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Relatorios</h1>
          <p className="text-muted-foreground">
            Analise o desempenho da equipe, conversoes do funil e atividades mensais
          </p>
        </div>
        <Button onClick={handleExportCSV} disabled={exporting} variant="outline">
          {exporting ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Download className="h-4 w-4 mr-2" />
          )}
          Exportar CSV
        </Button>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="ranking" className="flex items-center gap-2">
            <Trophy className="h-4 w-4" />
            Ranking Corretores
          </TabsTrigger>
          <TabsTrigger value="conversao" className="flex items-center gap-2">
            <TrendingDown className="h-4 w-4" />
            Conversao Funil
          </TabsTrigger>
          <TabsTrigger value="atividade" className="flex items-center gap-2">
            <CalendarDays className="h-4 w-4" />
            Atividade Mensal
          </TabsTrigger>
        </TabsList>

        {/* Ranking Corretores */}
        <TabsContent value="ranking" className="mt-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Users className="h-5 w-5" />
              Desempenho dos Corretores
            </h2>
            <Select
              value={String(periodoRanking)}
              onValueChange={(v) => setPeriodoRanking(Number(v))}
            >
              <SelectTrigger className="w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Ultimos 7 dias</SelectItem>
                <SelectItem value="15">Ultimos 15 dias</SelectItem>
                <SelectItem value="30">Ultimos 30 dias</SelectItem>
                <SelectItem value="60">Ultimos 60 dias</SelectItem>
                <SelectItem value="90">Ultimos 90 dias</SelectItem>
                <SelectItem value="365">Ultimo ano</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Summary cards */}
          {ranking && ranking.length > 0 && (
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Total de Vendas</CardTitle>
                  <BarChart3 className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {ranking.reduce((sum, r) => sum + r.clientes_fechados, 0)}
                  </div>
                  <p className="text-xs text-muted-foreground">no periodo selecionado</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Valor Total</CardTitle>
                  <BarChart3 className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {formatCurrency(ranking.reduce((sum, r) => sum + r.valor_total_fechados, 0))}
                  </div>
                  <p className="text-xs text-muted-foreground">em negocios fechados</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Corretores Ativos</CardTitle>
                  <Users className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{ranking.length}</div>
                  <p className="text-xs text-muted-foreground">com atividade no periodo</p>
                </CardContent>
              </Card>
            </div>
          )}

          <Card>
            <CardContent className="pt-6">
              {showRankingSkeleton ? (
                <TableSkeleton rows={3} />
              ) : !ranking || ranking.length === 0 ? (
                <div className="py-12 text-center text-muted-foreground">
                  <Trophy className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg">Nenhum dado de ranking disponivel</p>
                  <p className="text-sm">Altere o periodo para ver resultados</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[60px]">Pos.</TableHead>
                      <TableHead>Nome</TableHead>
                      <TableHead className="text-right">Vendas Fechadas</TableHead>
                      <TableHead className="text-right">Comissoes (valor)</TableHead>
                      <TableHead className="text-right">Clientes Ativos</TableHead>
                      <TableHead className="text-right">Atividades</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ranking.map((corretor, index) => (
                      <TableRow key={corretor.usuario_id}>
                        <TableCell>
                          {index < 3 ? (
                            <Badge
                              variant={index === 0 ? 'default' : 'secondary'}
                              className={
                                index === 0
                                  ? 'bg-yellow-500 hover:bg-yellow-600'
                                  : index === 1
                                    ? 'bg-gray-400 hover:bg-gray-500'
                                    : 'bg-amber-700 hover:bg-amber-800'
                              }
                            >
                              {index + 1}
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground font-medium">{index + 1}</span>
                          )}
                        </TableCell>
                        <TableCell className="font-medium">{corretor.nome}</TableCell>
                        <TableCell className="text-right font-semibold">
                          {corretor.clientes_fechados}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(corretor.valor_total_fechados)}
                        </TableCell>
                        <TableCell className="text-right">{corretor.total_clientes}</TableCell>
                        <TableCell className="text-right">{corretor.total_atividades}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Conversao Funil */}
        <TabsContent value="conversao" className="mt-6 space-y-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <TrendingDown className="h-5 w-5" />
            Conversao entre Etapas do Funil
          </h2>

          <Card>
            <CardContent className="pt-6">
              {showConversaoSkeleton ? (
                <TableSkeleton rows={3} />
              ) : !conversao || conversao.length === 0 ? (
                <div className="py-12 text-center text-muted-foreground">
                  <TrendingDown className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg">Nenhum dado de funil disponivel</p>
                  <p className="text-sm">Os dados aparecerao quando houver clientes no funil</p>
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Visual funnel representation */}
                  <div className="space-y-3">
                    {conversao.map((etapa, index) => {
                      const maxTotal = Math.max(...conversao.map((e) => e.total), 1);
                      const widthPercent = Math.max((etapa.total / maxTotal) * 100, 15);

                      return (
                        <div key={etapa.etapa}>
                          <div className="flex items-center gap-4">
                            <div
                              className="relative rounded-md bg-primary/10 border border-primary/20 p-4 transition-all"
                              style={{ width: `${widthPercent}%`, minWidth: '200px' }}
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-medium text-sm">{etapa.label}</span>
                                <Badge variant="secondary" className="ml-2">
                                  {etapa.total}
                                </Badge>
                              </div>
                            </div>
                          </div>

                          {/* Conversion arrow between stages */}
                          {index < conversao.length - 1 && (
                            <div className="flex items-center gap-2 ml-8 my-1">
                              <ArrowRight className="h-4 w-4 text-muted-foreground" />
                              <span
                                className={`text-sm font-medium ${
                                  (conversao[index + 1].taxa_conversao ?? 0) >= 50
                                    ? 'text-green-600'
                                    : (conversao[index + 1].taxa_conversao ?? 0) >= 25
                                      ? 'text-yellow-600'
                                      : 'text-red-600'
                                }`}
                              >
                                {formatPercent(conversao[index + 1].taxa_conversao)} de conversao
                              </span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Conversion table */}
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Etapa</TableHead>
                        <TableHead className="text-right">Total</TableHead>
                        <TableHead className="text-right">Taxa de Conversao</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {conversao.map((etapa) => (
                        <TableRow key={etapa.etapa}>
                          <TableCell className="font-medium">{etapa.label}</TableCell>
                          <TableCell className="text-right font-semibold">{etapa.total}</TableCell>
                          <TableCell className="text-right">
                            {etapa.taxa_conversao !== null ? (
                              <Badge
                                variant={
                                  etapa.taxa_conversao >= 50
                                    ? 'default'
                                    : etapa.taxa_conversao >= 25
                                      ? 'secondary'
                                      : 'destructive'
                                }
                              >
                                {formatPercent(etapa.taxa_conversao)}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Atividade Mensal */}
        <TabsContent value="atividade" className="mt-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <CalendarDays className="h-5 w-5" />
              Resumo de Atividade Mensal
            </h2>
            <Select
              value={String(mesesAtividade)}
              onValueChange={(v) => setMesesAtividade(Number(v))}
            >
              <SelectTrigger className="w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="3">Ultimos 3 meses</SelectItem>
                <SelectItem value="6">Ultimos 6 meses</SelectItem>
                <SelectItem value="12">Ultimo ano</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Summary cards for activity */}
          {atividade && atividade.length > 0 && (
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Total de Atividades</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {atividade.reduce((sum, a) => sum + a.total_atividades, 0)}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Novos Clientes</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {atividade.reduce((sum, a) => sum + a.novos_clientes, 0)}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Negocios Fechados</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {atividade.reduce((sum, a) => sum + a.fechados, 0)}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          <Card>
            <CardContent className="pt-6">
              {showAtividadeSkeleton ? (
                <TableSkeleton rows={3} />
              ) : !atividade || atividade.length === 0 ? (
                <div className="py-12 text-center text-muted-foreground">
                  <CalendarDays className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg">Nenhum dado de atividade disponivel</p>
                  <p className="text-sm">Os dados aparecerao conforme atividades forem registradas</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Periodo</TableHead>
                      <TableHead className="text-right">Atividades</TableHead>
                      <TableHead className="text-right">Novos Clientes</TableHead>
                      <TableHead className="text-right">Negocios Fechados</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {atividade.map((mes) => (
                      <TableRow key={mes.mes}>
                        <TableCell className="font-medium">{mes.periodo}</TableCell>
                        <TableCell className="text-right">{mes.total_atividades}</TableCell>
                        <TableCell className="text-right">
                          <Badge variant="secondary">{mes.novos_clientes}</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge variant="default">{mes.fechados}</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
