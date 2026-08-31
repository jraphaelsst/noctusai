import { MetricCard } from "@/components/ui/metric-card";
import { Target, TrendingUp, CheckCircle, Clock, Award, Activity, BarChart3, TrendingDown, Percent, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@noctusai/seed/components/ui/card";
import { Progress } from "@noctusai/seed/components/ui/progress";
import { Skeleton } from "@noctusai/seed/components/ui/skeleton";
import { useMetas } from "@/hooks/useMetas";
import { TipoMeta, CategoriaMeta, Meta } from "@/types";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Legend, ResponsiveContainer, LineChart, Line, Tooltip } from "recharts";
import { MetricasDetalhesModal } from "@/components/modals/MetricasDetalhesModal";
import { ImpedimentosModal } from "@/components/modals/ImpedimentosModal";
import { useState, useMemo } from "react";
import { useFiltrosStore } from "@/store/filtrosStore";
import { format, startOfWeek, endOfWeek } from "date-fns";
import { ptBR } from "date-fns/locale";
import { Badge } from "@noctusai/seed/components/ui/badge";
import { FiltrosDashboard } from "@/components/filtros/FiltrosDashboard";
import { MetasAgentWidget } from "@/components/MetasAgentWidget";
import { categoriaLabels as categoriaMetaLabels } from "@/lib/categorias";
import { useIsAdminOrCoordenador } from "@/hooks/useIsAdminOrCoordenador";
import { cn } from "@/lib/utils";

const tipoMetaLabels: Record<TipoMeta, string> = {
  diaria: "Metas Diárias",
  semanal: "Metas Semanais",
  mensal: "Metas Mensais",
  anual: "Metas Anuais",
};

// Função para determinar a cor baseada na porcentagem
const getProgressColor = (percentage: number): string => {
  if (percentage >= 80) return "hsl(var(--success))"; // Verde
  if (percentage >= 50) return "hsl(var(--warning))"; // Amarelo
  return "hsl(var(--danger))"; // Vermelho
};


const statusColors = {
  aberta: "hsl(var(--primary))",
  concluida: "hsl(var(--success))",
  atrasada: "hsl(var(--danger))",
  no_prazo: "hsl(var(--warning))",
};

const categoriaColors = {
  captacao: "hsl(200, 60%, 75%)",      // Azul pastel
  visitas: "hsl(280, 50%, 75%)",       // Roxo pastel
  contatos: "hsl(160, 50%, 70%)",      // Verde pastel
  propostas: "hsl(40, 60%, 75%)",      // Amarelo pastel
  fechamento: "hsl(340, 50%, 75%)",    // Rosa pastel
};

export default function Dashboard() {
  const metasQuery = useMetas();
  const { data: metas } = metasQuery;
  const showMetasSkeleton = metasQuery.isPending && !metasQuery.data;
  const [modalAberto, setModalAberto] = useState(false);
  const [impedimentosModalAberto, setImpedimentosModalAberto] = useState(false);
  const [filtroModal, setFiltroModal] = useState<'all' | 'concluidas' | 'abertas' | 'atrasadas' | 'concluidas_no_prazo' | 'melhor_categoria' | 'vencem_amanha'>('all');
  const [tituloModal, setTituloModal] = useState('');
  const [metasModal, setMetasModal] = useState<Meta[]>([]);
  const { isAdminOrCoordenador } = useIsAdminOrCoordenador();
  
  // Estados dos filtros (global)
  const { dataInicio, dataFim, filtroCorretor, filtroStatus, filtroTipo, filtroConclusaoPrazo } = useFiltrosStore();
  
  // Memoizar filtros para evitar recálculos desnecessários
  const metasFiltradas = useMemo(() => {
    const resultado = metas || [];
    
    // Aplicar todos os filtros de uma vez
    return resultado.filter(meta => {
      // Filtro de data início
      if (dataInicio && new Date(meta.data_prazo) < dataInicio) return false;
      
      // Filtro de data fim
      if (dataFim && new Date(meta.data_prazo) > dataFim) return false;
      
      // Filtro de corretor
      if (filtroCorretor !== "todos" && meta.usuario_id !== filtroCorretor) return false;
      
      // Filtro de status
      if (filtroStatus !== "todos" && meta.status !== filtroStatus) return false;
      
      // Filtro de tipo
      if (filtroTipo !== "todos" && meta.tipo !== filtroTipo) return false;
      
      // Filtro de conclusão no prazo
      if (filtroConclusaoPrazo !== "todos" && 
          (meta.conclusao_prazo !== filtroConclusaoPrazo || meta.conclusao_prazo === null)) return false;
      
      return true;
    });
  }, [metas, dataInicio, dataFim, filtroCorretor, filtroStatus, filtroTipo, filtroConclusaoPrazo]);
  
  // Memoizar todas as métricas para evitar recálculos
  const metricas = useMemo(() => {
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    const amanha = new Date(hoje);
    amanha.setDate(amanha.getDate() + 1);
    const amanhaTime = amanha.getTime();

    // Calcular todas as métricas em uma única iteração
    const resultado = metasFiltradas.reduce((acc, meta) => {
      // Contadores de status
      if (meta.status !== 'concluida') acc.totalMetas++;
      if (meta.status === 'concluida') acc.metasConcluidas++;
      if (meta.status === 'atrasada') acc.metasAtrasadas++;
      if (meta.status === 'aberta') acc.metasAbertas++;
      
      // Metas concluídas no prazo
      if (meta.status === 'concluida' && meta.finalizada_no_prazo) {
        acc.metasConcluidasNoPrazo++;
      }
      
      // Impedimentos
      if (meta.tem_impedimento) acc.metasComImpedimento++;
      
      // Metas que vencem amanhã
      const prazo = new Date(meta.data_prazo);
      prazo.setHours(0, 0, 0, 0);
      if (prazo.getTime() === amanhaTime && meta.status !== 'concluida') {
        acc.metasVencemAmanha++;
      }
      
      // Totais
      acc.totalPretendido += meta.meta_pretendida;
      acc.totalRealizado += (meta.meta_realizada || 0);
      
      return acc;
    }, {
      totalMetas: 0,
      metasConcluidas: 0,
      metasAtrasadas: 0,
      metasAbertas: 0,
      metasConcluidasNoPrazo: 0,
      metasComImpedimento: 0,
      metasVencemAmanha: 0,
      totalPretendido: 0,
      totalRealizado: 0,
    });

    const totalGeralMetas = resultado.totalMetas + resultado.metasConcluidas;
    
    return {
      ...resultado,
      percentualConclusao: resultado.totalMetas > 0 ? (resultado.metasConcluidas / resultado.totalMetas) * 100 : 0,
      taxaConclusaoNoPrazo: resultado.metasConcluidas > 0 ? (resultado.metasConcluidasNoPrazo / resultado.metasConcluidas) * 100 : 0,
      totalGeralMetas,
      taxaPerformance: totalGeralMetas > 0 ? (resultado.metasConcluidas / totalGeralMetas) * 100 : 0,
    };
  }, [metasFiltradas]);
  
  // Performance por categoria
  const performancePorCategoria = useMemo(() => {
    return (['captacao', 'visitas', 'contatos', 'propostas', 'fechamento'] as CategoriaMeta[]).map(categoria => {
      const metasCategoria = metasFiltradas.filter(m => m.categoria === categoria);
      const pretendido = metasCategoria.reduce((sum, m) => sum + m.meta_pretendida, 0);
      const realizado = metasCategoria.reduce((sum, m) => sum + (m.meta_realizada || 0), 0);
      const concluidas = metasCategoria.filter(m => m.status === 'concluida').length;
      const concluidasNoPrazo = metasCategoria.filter(m => m.status === 'concluida' && m.finalizada_no_prazo === true).length;
      const total = metasCategoria.length;
      
      return {
        categoria,
        nome: categoriaMetaLabels[categoria],
        pretendido,
        realizado,
        total,
        concluidas,
        concluidasNoPrazo,
        performance: pretendido > 0 ? (realizado / pretendido) * 100 : 0,
        taxaConclusao: total > 0 ? (concluidas / total) * 100 : 0,
        taxaConclusaoNoPrazo: concluidas > 0 ? (concluidasNoPrazo / concluidas) * 100 : 0,
        color: categoriaColors[categoria],
      };
    }).filter(item => item.total > 0 || item.pretendido > 0);
  }, [metasFiltradas]);
  
  // Evolução semanal (últimas 4 semanas)
  const evolucaoSemanal = useMemo(() => {
    const hoje = new Date();
    const semanas = [];
    
    for (let i = 3; i >= 0; i--) {
      const inicioSemana = startOfWeek(new Date(hoje.getTime() - i * 7 * 24 * 60 * 60 * 1000), { weekStartsOn: 0 });
      const fimSemana = endOfWeek(inicioSemana, { weekStartsOn: 0 });
      
      const metasSemana = metasFiltradas.filter(meta => {
        const dataMeta = new Date(meta.data_prazo);
        return dataMeta >= inicioSemana && dataMeta <= fimSemana;
      });
      
      const concluidas = metasSemana.filter(m => m.status === 'concluida').length;
      const total = metasSemana.length;
      
      semanas.push({
        semana: `${format(inicioSemana, 'dd/MM', { locale: ptBR })}`,
        concluidas,
        total,
        pendentes: total - concluidas,
        taxa: total > 0 ? (concluidas / total) * 100 : 0,
      });
    }
    
    return semanas;
  }, [metasFiltradas]);
  
  // Calcular melhor categoria (baseado na taxa de conclusão no prazo)
  const melhorCategoria = useMemo(() => {
    if (performancePorCategoria.length === 0) return null;
    return performancePorCategoria.reduce((melhor, atual) => 
      atual.taxaConclusaoNoPrazo > melhor.taxaConclusaoNoPrazo ? atual : melhor
    );
  }, [performancePorCategoria]);

  const handleOpenModal = (tipo: 'all' | 'concluidas' | 'abertas' | 'atrasadas' | 'concluidas_no_prazo' | 'melhor_categoria' | 'vencem_amanha', titulo: string) => {
    let metasFiltrar = metasFiltradas;
    
    // Aplicar filtros especiais para novos tipos
    if (tipo === 'atrasadas') {
      metasFiltrar = metasFiltradas.filter(m => m.status === 'atrasada');
    } else if (tipo === 'abertas') {
      metasFiltrar = metasFiltradas.filter(m => m.status === 'aberta');
    } else if (tipo === 'concluidas') {
      metasFiltrar = metasFiltradas.filter(m => m.status === 'concluida');
    } else if (tipo === 'concluidas_no_prazo') {
      metasFiltrar = metasFiltradas.filter(m => m.status === 'concluida' && m.finalizada_no_prazo === true);
    } else if (tipo === 'melhor_categoria' && melhorCategoria) {
      metasFiltrar = metasFiltradas.filter(m => m.categoria === melhorCategoria.categoria);
    } else if (tipo === 'vencem_amanha') {
      const hoje = new Date();
      hoje.setHours(0, 0, 0, 0);
      const amanha = new Date(hoje);
      amanha.setDate(amanha.getDate() + 1);
      
      metasFiltrar = metasFiltradas.filter(m => {
        const prazo = new Date(m.data_prazo);
        prazo.setHours(0, 0, 0, 0);
        return prazo.getTime() === amanha.getTime() && m.status !== 'concluida';
      });
    }
    
    setMetasModal(metasFiltrar);
    setFiltroModal(tipo);
    setTituloModal(titulo);
    setModalAberto(true);
  };

  // Dados para gráficos
  const statusData = [
    { name: "Concluídas", value: metricas.metasConcluidas, color: statusColors.concluida },
    { name: "Abertas", value: metricas.metasAbertas, color: statusColors.aberta },
    { name: "Atrasadas", value: metricas.metasAtrasadas, color: statusColors.atrasada },
  ].filter(item => item.value > 0);

  const categoriaData = (['captacao', 'visitas', 'contatos', 'propostas', 'fechamento'] as CategoriaMeta[]).map(categoria => {
    const metasCategoria = metas?.filter(m => m.categoria === categoria) || [];
    const totalPretendido = metasCategoria.reduce((sum, m) => sum + m.meta_pretendida, 0);
    const totalRealizado = metasCategoria.reduce((sum, m) => sum + (m.meta_realizada || 0), 0);
    
    return {
      name: categoriaMetaLabels[categoria],
      pretendido: totalPretendido,
      realizado: totalRealizado,
      fill: categoriaColors[categoria],
    };
  }).filter(item => item.pretendido > 0);

  // Dados por tipo de meta individual
  const tipoDataIndividual = useMemo(() => {
    return (['diaria', 'semanal', 'mensal', 'anual'] as TipoMeta[]).map(tipo => {
      const metasTipo = metasFiltradas.filter(m => m.tipo === tipo);
      const totalPretendido = metasTipo.reduce((sum, m) => sum + m.meta_pretendida, 0);
      const totalRealizado = metasTipo.reduce((sum, m) => sum + (m.meta_realizada || 0), 0);
      const concluidas = metasTipo.filter(m => m.status === 'concluida').length;
      const total = metasTipo.length;
      const percentualRealizacao = totalPretendido > 0 ? (totalRealizado / totalPretendido) * 100 : 0;
      const percentualConclusao = total > 0 ? (concluidas / total) * 100 : 0;
      
      return {
        tipo,
        nome: tipoMetaLabels[tipo],
        pretendido: totalPretendido,
        realizado: totalRealizado,
        concluidas,
        total,
        percentualRealizacao,
        percentualConclusao,
        cor: getProgressColor(percentualRealizacao),
      };
    }).filter(item => item.total > 0 || item.pretendido > 0);
  }, [metasFiltradas]);

  return (
    <div className="space-y-4 sm:space-y-6">
      <MetasAgentWidget />
      <FiltrosDashboard />

      {/* Métricas Principais - Linha 1 */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {showMetasSkeleton ? (
          <>
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </>
        ) : (
          <>
            <MetricCard
              title="Total de Metas"
              value={metricas.totalMetas + metricas.metasConcluidas}
              icon={Target}
              description={`${metricas.totalMetas} ativas`}
              onClick={() => handleOpenModal('all', 'Todas as Metas')}
            />
            <MetricCard
              title="Metas Concluídas"
              value={metricas.metasConcluidas}
              icon={CheckCircle}
              description={`${metricas.percentualConclusao.toFixed(1)}% do total`}
              onClick={() => handleOpenModal('concluidas', 'Metas Concluídas')}
            />
            <MetricCard
              title="Metas Abertas"
              value={metricas.metasAbertas}
              icon={Clock}
              description="Em andamento"
              onClick={() => handleOpenModal('abertas', 'Metas Abertas')}
            />
            <MetricCard
              title="Vencem Amanhã"
              value={metricas.metasVencemAmanha}
              icon={Clock}
              description="Atenção ao prazo"
              onClick={() => handleOpenModal('vencem_amanha', 'Metas que Vencem Amanhã')}
              variant={metricas.metasVencemAmanha > 0 ? "warning" : "default"}
            />
          </>
        )}
      </div>

      {/* Métricas de Performance - Linha 2 */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-5">
        {showMetasSkeleton ? (
          <>
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </>
        ) : (
          <>
            <MetricCard
              title="Performance"
              value={`${metricas.taxaPerformance.toFixed(1)}%`}
              icon={Activity}
              description={`${metricas.metasConcluidas} de ${metricas.totalGeralMetas} concluídas`}
              onClick={() => handleOpenModal('all', 'Análise de Performance')}
            />
            <MetricCard
              title="Conclusão no Prazo"
              value={`${metricas.taxaConclusaoNoPrazo.toFixed(0)}%`}
              icon={Award}
              description={`${metricas.metasConcluidasNoPrazo}/${metricas.metasConcluidas} no prazo`}
              onClick={() => handleOpenModal('concluidas_no_prazo' as any, 'Metas Concluídas no Prazo')}
            />
            <MetricCard
              title="Melhor Categoria"
              value={melhorCategoria?.nome || "-"}
              icon={TrendingUp}
              description={melhorCategoria ? `${melhorCategoria.taxaConclusaoNoPrazo.toFixed(0)}% no prazo` : "Sem dados"}
              onClick={() => melhorCategoria && handleOpenModal('melhor_categoria' as any, `Comparação de Categorias`)}
            />
            <MetricCard
              title="Impedimentos"
              value={metricas.metasComImpedimento}
              icon={AlertTriangle}
              description={`${metricas.metasComImpedimento} ${metricas.metasComImpedimento === 1 ? 'meta bloqueada' : 'metas bloqueadas'}`}
              onClick={() => setImpedimentosModalAberto(true)}
              variant={metricas.metasComImpedimento > 0 ? "warning" : "default"}
            />
            <MetricCard
              title="Atrasadas"
              value={metricas.metasAtrasadas}
              icon={TrendingDown}
              description="Necessitam atenção"
              onClick={() => handleOpenModal('atrasadas', 'Metas Atrasadas')}
              variant={metricas.metasAtrasadas > 0 ? "danger" : "default"}
            />
          </>
        )}
      </div>


      {/* Métricas Adicionais - Linha 3 */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {showMetasSkeleton ? (
          <>
            <Skeleton className="h-32" />
          </>
        ) : (
          <>
            <MetricCard
              title="Fechamentos Realizados"
              value={metasFiltradas.filter(m => m.categoria === 'fechamento' && m.status === 'concluida').reduce((sum, m) => sum + (m.meta_realizada || 0), 0)}
              icon={BarChart3}
              description={`${metasFiltradas.filter(m => m.categoria === 'fechamento' && m.status === 'concluida').length} metas concluídas`}
            />
          </>
        )}
      </div>

      {/* Resumo de Progresso */}
      <Card 
        className={cn(
          "transition-all",
          isAdminOrCoordenador && "cursor-pointer hover:shadow-lg hover:scale-[1.01]"
        )}
        onClick={() => isAdminOrCoordenador && handleOpenModal('all', 'Detalhes do Resumo de Progresso')}
      >
        <CardHeader>
          <CardTitle className="text-2xl font-semibold mb-4">
            Resumo de Progresso
          </CardTitle>
          <CardDescription>Visão geral do desempenho atual</CardDescription>
        </CardHeader>
        <CardContent>
            <div className="space-y-6">
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Taxa de Conclusão</span>
                <span className="font-medium" style={{ color: getProgressColor(metricas.percentualConclusao) }}>
                  {metricas.percentualConclusao.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                <div 
                  className="h-full transition-all duration-500 rounded-full"
                  style={{ 
                    width: `${Math.min(metricas.percentualConclusao, 100)}%`,
                    backgroundColor: getProgressColor(metricas.percentualConclusao)
                  }}
                />
              </div>
            </div>
            
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Performance Geral</span>
                <span className="font-medium" style={{ color: getProgressColor(metricas.taxaPerformance) }}>
                  {metricas.taxaPerformance.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                <div 
                  className="h-full transition-all duration-500 rounded-full"
                  style={{ 
                    width: `${Math.min(metricas.taxaPerformance, 100)}%`,
                    backgroundColor: getProgressColor(metricas.taxaPerformance)
                  }}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                {metricas.totalRealizado} realizados de {metricas.totalPretendido} pretendidos
              </p>
            </div>
            
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Conclusão no Prazo</span>
                <span className="font-medium" style={{ color: getProgressColor(metricas.taxaConclusaoNoPrazo) }}>
                  {metricas.taxaConclusaoNoPrazo.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                <div 
                  className="h-full transition-all duration-500 rounded-full"
                  style={{ 
                    width: `${Math.min(metricas.taxaConclusaoNoPrazo, 100)}%`,
                    backgroundColor: getProgressColor(metricas.taxaConclusaoNoPrazo)
                  }}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                {metricas.metasConcluidasNoPrazo} de {metricas.metasConcluidas} metas concluídas no prazo
              </p>
            </div>
            
            <div className="grid grid-cols-3 gap-4 text-center text-sm">
              <div>
                <div className="font-medium text-success">{metricas.metasConcluidas}</div>
                <div className="text-muted-foreground">Concluídas</div>
              </div>
              <div>
                <div className="font-medium text-primary">{metricas.metasAbertas}</div>
                <div className="text-muted-foreground">Abertas</div>
              </div>
              <div>
                <div className="font-medium text-danger">{metricas.metasAtrasadas}</div>
                <div className="text-muted-foreground">Atrasadas</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Performance por Categoria */}
      <Card 
        className={cn(
          "transition-all",
          isAdminOrCoordenador && "cursor-pointer hover:shadow-lg hover:scale-[1.01]"
        )}
        onClick={() => isAdminOrCoordenador && handleOpenModal('all', 'Detalhes de Performance por Categoria')}
      >
        <CardHeader>
          <CardTitle className="text-2xl font-semibold mb-4">
            Performance por Categoria
          </CardTitle>
          <CardDescription>Análise detalhada de cada categoria de metas</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {performancePorCategoria.map((cat) => (
              <div 
                key={cat.categoria} 
                className={cn(
                  "space-y-2 p-3 rounded-lg transition-all",
                  isAdminOrCoordenador && "cursor-pointer hover:bg-muted/50"
                )}
                onClick={(e) => {
                  if (isAdminOrCoordenador) {
                    e.stopPropagation();
                    const metasCategoria = metasFiltradas.filter(m => m.categoria === cat.categoria);
                    setMetasModal(metasCategoria);
                    setFiltroModal('all');
                    setTituloModal(`Metas de ${cat.nome}`);
                    setModalAberto(true);
                  }
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div 
                      className="w-3 h-3 rounded-full" 
                      style={{ backgroundColor: cat.color }}
                    />
                    <span className="font-medium">{cat.nome}</span>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <Badge 
                      variant={cat.performance >= 80 ? "default" : "secondary"}
                      style={{ 
                        backgroundColor: cat.performance >= 80 ? getProgressColor(cat.performance) : undefined 
                      }}
                    >
                      {cat.performance.toFixed(0)}% performance
                    </Badge>
                    <span className="text-muted-foreground">
                      {cat.realizado}/{cat.pretendido}
                    </span>
                  </div>
                </div>
                <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                  <div 
                    className="h-full transition-all duration-500 rounded-full"
                    style={{ 
                      width: `${Math.min(cat.performance, 100)}%`,
                      backgroundColor: getProgressColor(cat.performance)
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Evolução Semanal */}
      <Card 
        className={cn(
          "transition-all",
          isAdminOrCoordenador && "cursor-pointer hover:shadow-lg hover:scale-[1.01]"
        )}
        onClick={() => isAdminOrCoordenador && handleOpenModal('all', 'Detalhes da Evolução Semanal')}
      >
        <CardHeader>
          <CardTitle className="text-2xl font-semibold mb-4">
            Evolução Semanal
          </CardTitle>
          <CardDescription>Últimas 4 semanas de atividade</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={evolucaoSemanal}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis 
                dataKey="semana" 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <YAxis 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                }}
              />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="concluidas" 
                stroke="hsl(var(--success))" 
                strokeWidth={2}
                name="Concluídas"
                dot={{ fill: 'hsl(var(--success))' }}
              />
              <Line 
                type="monotone" 
                dataKey="pendentes" 
                stroke="hsl(var(--warning))" 
                strokeWidth={2}
                name="Pendentes"
                dot={{ fill: 'hsl(var(--warning))' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Gráficos de Análise */}
      {!showMetasSkeleton && metas && metas.length > 0 && (
        <div className="grid gap-4 sm:gap-6 grid-cols-1 lg:grid-cols-2">
          {/* Gráfico de Status */}
          <Card 
            className={cn(
              "transition-all",
              isAdminOrCoordenador && "cursor-pointer hover:shadow-lg hover:scale-[1.01]"
            )}
            onClick={() => isAdminOrCoordenador && handleOpenModal('all', 'Detalhes da Distribuição por Status')}
          >
            <CardHeader>
              <CardTitle className="text-2xl font-semibold mb-4">
                Distribuição por Status
              </CardTitle>
            </CardHeader>
            <CardContent className="pb-4">
              <ChartContainer
                config={{
                  concluidas: { label: "Concluídas", color: statusColors.concluida },
                  abertas: { label: "Abertas", color: statusColors.aberta },
                  atrasadas: { label: "Atrasadas", color: statusColors.atrasada },
                }}
                className="h-[250px] w-full"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={statusData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                      outerRadius={60}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {statusData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <ChartTooltip content={<ChartTooltipContent />} />
                  </PieChart>
                </ResponsiveContainer>
              </ChartContainer>
            </CardContent>
          </Card>

          {/* Progresso Individual por Tipo de Meta */}
          {tipoDataIndividual.map((tipoMeta) => (
            <Card 
              key={tipoMeta.tipo}
              className={cn(
                "transition-all",
                isAdminOrCoordenador && "cursor-pointer hover:shadow-lg hover:scale-[1.01]"
              )}
              onClick={() => {
                if (isAdminOrCoordenador) {
                  const metasTipo = metasFiltradas.filter(m => m.tipo === tipoMeta.tipo);
                  setMetasModal(metasTipo);
                  setFiltroModal('all');
                  setTituloModal(`Metas ${tipoMeta.nome}`);
                  setModalAberto(true);
                }
              }}
            >
              <CardHeader>
                <CardTitle className="text-2xl font-semibold mb-4">
                  {tipoMeta.nome}
                </CardTitle>
                <CardDescription>
                  {tipoMeta.concluidas} de {tipoMeta.total} concluídas
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Realização</span>
                    <span className="font-semibold" style={{ color: tipoMeta.cor }}>
                      {tipoMeta.percentualRealizacao.toFixed(0)}%
                    </span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                    <div 
                      className="h-full transition-all duration-500 rounded-full"
                      style={{ 
                        width: `${Math.min(tipoMeta.percentualRealizacao, 100)}%`,
                        backgroundColor: tipoMeta.cor
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Realizado: {tipoMeta.realizado}</span>
                    <span>Meta: {tipoMeta.pretendido}</span>
                  </div>
                </div>
                
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Conclusão</span>
                    <span className="font-semibold" style={{ color: getProgressColor(tipoMeta.percentualConclusao) }}>
                      {tipoMeta.percentualConclusao.toFixed(0)}%
                    </span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                    <div 
                      className="h-full transition-all duration-500 rounded-full"
                      style={{ 
                        width: `${Math.min(tipoMeta.percentualConclusao, 100)}%`,
                        backgroundColor: getProgressColor(tipoMeta.percentualConclusao)
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Concluídas: {tipoMeta.concluidas}</span>
                    <span>Total: {tipoMeta.total}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Modal de Detalhes das Métricas */}
      {filtroModal === 'melhor_categoria' ? (
        <Card className={modalAberto ? "fixed inset-4 z-50 overflow-auto" : "hidden"}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-2xl font-semibold mb-4">{tituloModal}</CardTitle>
              <button 
                onClick={() => setModalAberto(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                ✕
              </button>
            </div>
            <CardDescription>Comparação de desempenho por categoria (% de conclusão no prazo)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {performancePorCategoria.map((cat) => (
              <div key={cat.categoria} className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div 
                      className="w-4 h-4 rounded-full" 
                      style={{ backgroundColor: cat.color }}
                    />
                    <span className="font-semibold text-lg">{cat.nome}</span>
                  </div>
                  <Badge 
                    variant="default"
                    style={{ 
                      backgroundColor: getProgressColor(cat.taxaConclusaoNoPrazo)
                    }}
                  >
                    {cat.taxaConclusaoNoPrazo.toFixed(1)}% no prazo
                  </Badge>
                </div>
                
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <div className="text-muted-foreground">Total</div>
                    <div className="font-semibold text-lg">{cat.total}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Concluídas</div>
                    <div className="font-semibold text-lg">{cat.concluidas}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">No Prazo</div>
                    <div className="font-semibold text-lg">{cat.concluidasNoPrazo}</div>
                  </div>
                </div>
                
                <div className="space-y-2">
                  <div className="text-sm text-muted-foreground">Taxa de Conclusão no Prazo</div>
                  <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                    <div 
                      className="h-full transition-all duration-500 rounded-full"
                      style={{ 
                        width: `${Math.min(cat.taxaConclusaoNoPrazo, 100)}%`,
                        backgroundColor: getProgressColor(cat.taxaConclusaoNoPrazo)
                      }}
                    />
                  </div>
                </div>
                
                <div className="space-y-2">
                  <div className="text-sm text-muted-foreground">Performance (Realizado/Pretendido)</div>
                  <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                    <div 
                      className="h-full transition-all duration-500 rounded-full"
                      style={{ 
                        width: `${Math.min(cat.performance, 100)}%`,
                        backgroundColor: cat.color
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Realizado: {cat.realizado}</span>
                    <span>Meta: {cat.pretendido}</span>
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : (
        <MetricasDetalhesModal
          open={modalAberto}
          onOpenChange={setModalAberto}
          title={tituloModal}
          metas={metasModal.length > 0 ? metasModal : metasFiltradas}
          filterType={filtroModal === 'concluidas_no_prazo' || filtroModal === 'vencem_amanha' ? 'all' : filtroModal}
        />
      )}
      
      {/* Modal de Impedimentos */}
      <ImpedimentosModal
        open={impedimentosModalAberto}
        onOpenChange={setImpedimentosModalAberto}
        metas={metasFiltradas}
      />
    </div>
  );
}