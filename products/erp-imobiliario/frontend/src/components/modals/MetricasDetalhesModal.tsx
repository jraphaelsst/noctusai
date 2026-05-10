import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@noctusai/seed/components/ui/dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@noctusai/seed/components/ui/collapsible";
import { MetaCard } from "@/components/ui/meta-card";
import { Meta, TipoMeta, CategoriaMeta } from "@/types";
import { ChevronDown, Filter, CalendarIcon, X } from "lucide-react";
import { useState, useEffect } from "react";
import { MetaDetalhesModal } from "./MetaDetalhesModal";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@noctusai/seed/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@noctusai/seed/components/ui/card";
import { Label } from "@noctusai/seed/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@noctusai/seed/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@noctusai/seed/components/ui/popover";
import { Button } from "@noctusai/seed/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { format, startOfDay, endOfDay, startOfWeek, endOfWeek, startOfMonth, endOfMonth, startOfYear, endOfYear } from "date-fns";
import { ptBR } from "date-fns/locale";
import { cn } from "@/lib/utils";
import { useProfiles } from "@/hooks/useProfiles";
import { useUserRole } from "@/hooks/useUserRole";
import { Badge } from "@noctusai/seed/components/ui/badge";
import { categoriaLabels as categoriaMetaLabels, categoriaOrdem, sortMetasByCategoria } from "@/lib/categorias";

interface MetricasDetalhesModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  metas: Meta[];
  filterType: 'all' | 'concluidas' | 'abertas' | 'atrasadas';
  groupBy?: 'tipo' | 'categoria';
}

const tipoMetaLabels: Record<TipoMeta, string> = {
  diaria: "Metas Diárias",
  semanal: "Metas Semanais",
  mensal: "Metas Mensais",
  anual: "Metas Anuais",
};


export function MetricasDetalhesModal({
  open,
  onOpenChange,
  title,
  metas,
  filterType,
  groupBy = 'tipo',
}: MetricasDetalhesModalProps) {
  const [selectedMeta, setSelectedMeta] = useState<Meta | null>(null);
  const [activeTab, setActiveTab] = useState<string>("todas");
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    diaria: true,
    semanal: true,
    mensal: true,
    anual: true,
    captacao: true,
    visitas: true,
    contatos: true,
    propostas: true,
    fechamento: true,
  });

  // Filtros locais do modal
  const [periodo, setPeriodo] = useState<string>("global");
  const [dataInicio, setDataInicio] = useState<Date | undefined>(undefined);
  const [dataFim, setDataFim] = useState<Date | undefined>(undefined);
  const [filtroCorretor, setFiltroCorretor] = useState<string>("todos");
  const [filtroStatus, setFiltroStatus] = useState<string>("todos");
  const [filtroTipo, setFiltroTipo] = useState<string>("todos");

  useEffect(() => {
    const hoje = new Date();
    
    switch (periodo) {
      case 'global':
        setDataInicio(undefined);
        setDataFim(undefined);
        break;
      case 'diario':
        setDataInicio(startOfDay(hoje));
        setDataFim(endOfDay(hoje));
        break;
      case 'semanal':
        setDataInicio(startOfWeek(hoje, { weekStartsOn: 0 }));
        setDataFim(endOfWeek(hoje, { weekStartsOn: 0 }));
        break;
      case 'mensal':
        setDataInicio(startOfMonth(hoje));
        setDataFim(endOfMonth(hoje));
        break;
      case 'anual':
        setDataInicio(startOfYear(hoje));
        setDataFim(endOfYear(hoje));
        break;
    }
  }, [periodo]);

  const { data: corretores, isLoading: isLoadingCorretores } = useProfiles();
  const { data: userRole } = useUserRole();
  const canViewAllCorretores = userRole === 'admin';

  // Filtrar metas baseado no tipo principal e filtros locais
  let metasFiltradas = metas.filter((meta) => {
    switch (filterType) {
      case 'concluidas':
        return meta.status === 'concluida';
      case 'abertas':
        return meta.status === 'aberta';
      case 'atrasadas':
        return meta.status === 'atrasada';
      case 'all':
      default:
        return true;
    }
  });

  // Aplicar filtros locais
  if (dataInicio) {
    metasFiltradas = metasFiltradas.filter(meta => 
      new Date(meta.data_prazo) >= dataInicio
    );
  }

  if (dataFim) {
    metasFiltradas = metasFiltradas.filter(meta => 
      new Date(meta.data_prazo) <= dataFim
    );
  }

  if (filtroStatus !== "todos") {
    metasFiltradas = metasFiltradas.filter(meta => meta.status === filtroStatus);
  }

  if (filtroCorretor !== "todos") {
    metasFiltradas = metasFiltradas.filter(meta => meta.usuario_id === filtroCorretor);
  }

  if (filtroTipo !== "todos") {
    metasFiltradas = metasFiltradas.filter(meta => meta.tipo === filtroTipo);
  }

  // Função para ordenar metas por categoria e data de criação
  const sortMetas = (metas: Meta[]) => {
    return sortMetasByCategoria(metas);
  };

  // Agrupar metas por tipo e ordenar
  const metasPorTipo: Record<TipoMeta, Meta[]> = {
    diaria: sortMetas(metasFiltradas.filter(m => m.tipo === 'diaria')),
    semanal: sortMetas(metasFiltradas.filter(m => m.tipo === 'semanal')),
    mensal: sortMetas(metasFiltradas.filter(m => m.tipo === 'mensal')),
    anual: sortMetas(metasFiltradas.filter(m => m.tipo === 'anual')),
  };

  // Agrupar metas por categoria e ordenar usando categoriaOrdem
  const metasPorCategoria = categoriaOrdem.reduce((acc, categoria) => {
    acc[categoria] = sortMetas(metasFiltradas.filter(m => m.categoria === categoria));
    return acc;
  }, {} as Record<CategoriaMeta, Meta[]>);

  const toggleSection = (key: string) => {
    setOpenSections(prev => ({ ...prev, [key]: !prev[key] }));
  };
  
  // Calcular métricas adicionais
  const totalPretendido = metasFiltradas.reduce((sum, m) => sum + m.meta_pretendida, 0);
  const totalRealizado = metasFiltradas.reduce((sum, m) => sum + (m.meta_realizada || 0), 0);
  const taxaConclusao = metasFiltradas.length > 0 
    ? (metasFiltradas.filter(m => m.status === 'concluida').length / metasFiltradas.length) * 100 
    : 0;
  const taxaPerformance = totalPretendido > 0 ? (totalRealizado / totalPretendido) * 100 : 0;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-[95vw] sm:max-w-5xl max-h-[90vh] overflow-y-auto border-0 shadow-2xl">
          <DialogHeader className="border-b pb-4 space-y-3">
            <DialogTitle className="text-3xl font-light tracking-tight">{title}</DialogTitle>
            <div className="flex items-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-primary/40" />
                <span className="text-muted-foreground">
                  {metasFiltradas.length} {metasFiltradas.length === 1 ? 'meta' : 'metas'}
                </span>
              </div>
              {metasFiltradas.length > 0 && (
                <>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-success/40" />
                    <span className="text-muted-foreground">
                      <span className="font-medium text-foreground">{taxaConclusao.toFixed(0)}%</span> concluída
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-info/40" />
                    <span className="text-muted-foreground">
                      <span className="font-medium text-foreground">{taxaPerformance.toFixed(0)}%</span> performance
                    </span>
                  </div>
                </>
              )}
            </div>
          </DialogHeader>

          {/* Filtros com design minimalista */}
          <Card className="border-0 bg-accent/30 shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground uppercase tracking-wider">
                <Filter className="h-3.5 w-3.5" />
                Filtros
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-3">
                <div className="flex-1 min-w-[180px] space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">Período</Label>
                  <div className="relative">
                    <Select value={periodo} onValueChange={setPeriodo}>
                      <SelectTrigger className={cn("h-9 border-muted-foreground/20", periodo === "global" && "text-muted-foreground")}>
                        <SelectValue placeholder="Selecione o período" />
                      </SelectTrigger>
                      <SelectContent className="bg-background">
                        <SelectItem value="global">Global</SelectItem>
                        <SelectItem value="diario">Diário</SelectItem>
                        <SelectItem value="semanal">Semanal</SelectItem>
                        <SelectItem value="mensal">Mensal</SelectItem>
                        <SelectItem value="anual">Anual</SelectItem>
                      </SelectContent>
                    </Select>
                    {periodo !== "global" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setPeriodo("global");
                        }}
                        className="absolute right-8 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                      >
                        <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex-1 min-w-[180px] space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">Data Início</Label>
                  <div className="relative">
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button
                          variant="outline"
                          className={cn(
                            "w-full h-9 justify-start text-left font-normal border-muted-foreground/20",
                            !dataInicio && "text-muted-foreground"
                          )}
                        >
                          <CalendarIcon className="mr-2 h-4 w-4" />
                          {dataInicio ? format(dataInicio, "PPP", { locale: ptBR }) : <span>Selecione a data</span>}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0" align="start">
                        <Calendar
                          mode="single"
                          selected={dataInicio}
                          onSelect={setDataInicio}
                          initialFocus
                          className={cn("p-3 pointer-events-auto")}
                        />
                      </PopoverContent>
                    </Popover>
                    {dataInicio && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDataInicio(undefined);
                        }}
                        className="absolute right-2 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                      >
                        <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex-1 min-w-[180px] space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">Data Fim</Label>
                  <div className="relative">
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button
                          variant="outline"
                          className={cn(
                            "w-full h-9 justify-start text-left font-normal border-muted-foreground/20",
                            !dataFim && "text-muted-foreground"
                          )}
                        >
                          <CalendarIcon className="mr-2 h-4 w-4" />
                          {dataFim ? format(dataFim, "PPP", { locale: ptBR }) : <span>Selecione a data</span>}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0" align="start">
                        <Calendar
                          mode="single"
                          selected={dataFim}
                          onSelect={setDataFim}
                          initialFocus
                          className={cn("p-3 pointer-events-auto")}
                        />
                      </PopoverContent>
                    </Popover>
                    {dataFim && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDataFim(undefined);
                        }}
                        className="absolute right-2 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                      >
                        <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                      </button>
                    )}
                  </div>
                </div>
                {canViewAllCorretores && (
                  <div className="flex-1 min-w-[180px] space-y-1.5">
                    <Label className="text-xs font-medium text-muted-foreground">Usuário</Label>
                    <div className="relative">
                      <Select value={filtroCorretor} onValueChange={setFiltroCorretor}>
                        <SelectTrigger className={cn("h-9 border-muted-foreground/20", filtroCorretor === "todos" && "text-muted-foreground")}>
                          <SelectValue placeholder="Todos os usuários" />
                        </SelectTrigger>
                        <SelectContent className="bg-background">
                          <SelectItem value="todos">Todos os usuários</SelectItem>
                          {isLoadingCorretores ? (
                            <SelectItem value="loading" disabled>Carregando...</SelectItem>
                          ) : (
                            corretores?.map((corretor) => (
                              <SelectItem key={corretor.id} value={corretor.id}>
                                {corretor.nome}
                              </SelectItem>
                            ))
                          )}
                        </SelectContent>
                      </Select>
                      {filtroCorretor !== "todos" && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setFiltroCorretor("todos");
                          }}
                          className="absolute right-8 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                        >
                          <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                        </button>
                      )}
                    </div>
                  </div>
                )}
                <div className="flex-1 min-w-[180px] space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">Status</Label>
                  <div className="relative">
                    <Select value={filtroStatus} onValueChange={setFiltroStatus}>
                      <SelectTrigger className={cn("h-9 border-muted-foreground/20", filtroStatus === "todos" && "text-muted-foreground")}>
                        <SelectValue placeholder="Todos os status" />
                      </SelectTrigger>
                      <SelectContent className="bg-background">
                        <SelectItem value="todos">Todos os status</SelectItem>
                        <SelectItem value="aberta">Aberta</SelectItem>
                        <SelectItem value="concluida">Concluída</SelectItem>
                        <SelectItem value="atrasada">Atrasada</SelectItem>
                        <SelectItem value="no_prazo">No Prazo</SelectItem>
                      </SelectContent>
                    </Select>
                    {filtroStatus !== "todos" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setFiltroStatus("todos");
                        }}
                        className="absolute right-8 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                      >
                        <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex-1 min-w-[180px] space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">Periodicidade</Label>
                  <div className="relative">
                    <Select value={filtroTipo} onValueChange={setFiltroTipo}>
                      <SelectTrigger className={cn("h-9 border-muted-foreground/20", filtroTipo === "todos" && "text-muted-foreground")}>
                        <SelectValue placeholder="Todos os tipos" />
                      </SelectTrigger>
                      <SelectContent className="bg-background">
                        <SelectItem value="todos">Todos os tipos</SelectItem>
                        <SelectItem value="diaria">Diária</SelectItem>
                        <SelectItem value="semanal">Semanal</SelectItem>
                        <SelectItem value="mensal">Mensal</SelectItem>
                        <SelectItem value="anual">Anual</SelectItem>
                      </SelectContent>
                    </Select>
                    {filtroTipo !== "todos" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setFiltroTipo("todos");
                        }}
                        className="absolute right-8 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                      >
                        <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {metasFiltradas.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <p>Nenhuma meta encontrada com os filtros aplicados.</p>
            </div>
          ) : (
            <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
              <TabsList className="grid w-full grid-cols-5">
                <TabsTrigger value="todas">
                  Todas ({metasFiltradas.length})
                </TabsTrigger>
                <TabsTrigger value="diaria">
                  Diárias ({metasPorTipo.diaria.length})
                </TabsTrigger>
                <TabsTrigger value="semanal">
                  Semanais ({metasPorTipo.semanal.length})
                </TabsTrigger>
                <TabsTrigger value="mensal">
                  Mensais ({metasPorTipo.mensal.length})
                </TabsTrigger>
                <TabsTrigger value="anual">
                  Anuais ({metasPorTipo.anual.length})
                </TabsTrigger>
              </TabsList>

              {/* Aba Todas - Mostra todas as seções */}
              <TabsContent value="todas" className="mt-4">
                <div className="space-y-4">
                  {groupBy === 'categoria' ? (
                    (['captacao', 'visitas', 'contatos', 'propostas', 'fechamento'] as CategoriaMeta[]).map((categoria) => {
                      const metasDaCategoria = metasPorCategoria[categoria];
                      
                      if (metasDaCategoria.length === 0) return null;
                      
                      return (
                        <Collapsible 
                          key={categoria}
                          open={openSections[categoria]}
                          onOpenChange={() => toggleSection(categoria)}
                        >
                          <CollapsibleTrigger className="group flex items-center gap-2 w-full hover:bg-muted/50 rounded-md p-3 transition-colors">
                            <ChevronDown 
                              className={`h-5 w-5 transition-transform ${
                                openSections[categoria] ? 'rotate-0' : '-rotate-90'
                              }`}
                            />
                            <h3 className="text-lg font-semibold text-foreground">
                              {categoriaMetaLabels[categoria]} ({metasDaCategoria.length})
                            </h3>
                          </CollapsibleTrigger>
                          
                          <CollapsibleContent className="mt-3 ml-7">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                              {metasDaCategoria.map((meta) => (
                                <MetaCard 
                                  key={meta.id} 
                                  meta={meta}
                                  onEdit={(meta) => setSelectedMeta(meta)}
                                />
                              ))}
                            </div>
                          </CollapsibleContent>
                        </Collapsible>
                      );
                    })
                  ) : (
                    (['diaria', 'semanal', 'mensal', 'anual'] as TipoMeta[]).map((tipo) => {
                      const metasDoTipo = metasPorTipo[tipo];
                      
                      if (metasDoTipo.length === 0) return null;
                      
                      return (
                        <Collapsible 
                          key={tipo}
                          open={openSections[tipo]}
                          onOpenChange={() => toggleSection(tipo)}
                        >
                          <CollapsibleTrigger className="group flex items-center gap-2 w-full hover:bg-muted/50 rounded-md p-3 transition-colors">
                            <ChevronDown 
                              className={`h-5 w-5 transition-transform ${
                                openSections[tipo] ? 'rotate-0' : '-rotate-90'
                              }`}
                            />
                            <h3 className="text-lg font-semibold text-foreground">
                              {tipoMetaLabels[tipo]} ({metasDoTipo.length})
                            </h3>
                          </CollapsibleTrigger>
                          
                          <CollapsibleContent className="mt-3 ml-7">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                              {metasDoTipo.map((meta) => (
                                <MetaCard 
                                  key={meta.id} 
                                  meta={meta}
                                  onEdit={(meta) => setSelectedMeta(meta)}
                                />
                              ))}
                            </div>
                          </CollapsibleContent>
                        </Collapsible>
                      );
                    })
                  )}
                </div>
              </TabsContent>

              {/* Abas individuais por tipo */}
              {(['diaria', 'semanal', 'mensal', 'anual'] as TipoMeta[]).map((tipo) => {
                const metasDoTipo = metasPorTipo[tipo];
                
                return (
                  <TabsContent key={tipo} value={tipo} className="mt-4">
                    {metasDoTipo.length === 0 ? (
                      <Card>
                        <CardContent className="flex flex-col items-center justify-center py-12">
                          <div className="text-muted-foreground text-center">
                            <p className="text-lg mb-2">Nenhuma meta {tipoMetaLabels[tipo].toLowerCase()} encontrada</p>
                          </div>
                        </CardContent>
                      </Card>
                    ) : (
                      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {metasDoTipo.map((meta) => (
                          <MetaCard 
                            key={meta.id} 
                            meta={meta}
                            onEdit={(meta) => setSelectedMeta(meta)}
                          />
                        ))}
                      </div>
                    )}
                  </TabsContent>
                );
              })}
            </Tabs>
          )}
        </DialogContent>
      </Dialog>

      {/* Modal de Detalhes da Meta */}
      {selectedMeta && (
        <MetaDetalhesModal
          meta={selectedMeta}
          open={!!selectedMeta}
          onOpenChange={(open) => !open && setSelectedMeta(null)}
        />
      )}
    </>
  );
}