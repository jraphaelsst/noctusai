import { useState } from "react";
import { MetaCard } from "@/components/ui/meta-card";
import { ChevronDown, Loader2, CheckSquare, Trash2 } from "lucide-react";
import { MetaDetalhesModal } from "@/components/modals/MetaDetalhesModal";
import { NovaMetaModal } from "@/components/modals/NovaMetaModal";
import { toast } from "@/hooks/use-toast";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useMetas, useDeleteMeta } from "@/hooks/useMetas";
import { useUserRole } from "@/hooks/useUserRole";
import { Meta, TipoMeta } from "@/types";
import { useFiltrosStore } from "@/store/filtrosStore";
import { Button } from "@/components/ui/button";
import { FiltrosMetas } from "@/components/filtros/FiltrosMetas";
import { MetasDraggableSection } from "@/components/metas/MetasDraggableSection";
import { useMetasOrdem } from "@/hooks/useMetasOrdem";
import { ConfiguracoesMetasModal } from "@/components/modals/ConfiguracoesMetasModal";
import { sortMetasByCategoria } from "@/lib/categorias";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

const tipoMetaLabels: Record<TipoMeta, string> = {
  diaria: "Metas Diárias",
  semanal: "Metas Semanais",
  mensal: "Metas Mensais",
  anual: "Metas Anuais",
};

const tipoLabels: Record<TipoMeta, string> = {
  diaria: "Diárias",
  semanal: "Semanais",
  mensal: "Mensais",
  anual: "Anuais",
};

export default function Metas() {
  const [selectedMeta, setSelectedMeta] = useState<Meta | null>(null);
  const [activeTab, setActiveTab] = useState<string>("todas");
  const [openSections, setOpenSections] = useState<Record<TipoMeta, boolean>>({
    diaria: true,
    semanal: true,
    mensal: true,
    anual: true,
  });
  const [modoSelecao, setModoSelecao] = useState(false);
  const [metasSelecionadas, setMetasSelecionadas] = useState<Set<string>>(new Set());
  const [metaParaExcluir, setMetaParaExcluir] = useState<string | null>(null);
  const [confirmarExclusaoMassa, setConfirmarExclusaoMassa] = useState(false);

  const { data: metas, isLoading } = useMetas();
  const { data: userRole } = useUserRole();
  const deleteMeta = useDeleteMeta();
  const { reordenarMetas, getMetasOrdenadas } = useMetasOrdem();

  // Estados dos filtros (global)
  const { dataInicio, dataFim, filtroCorretor, filtroStatus, filtroTipo, filtroReferencia, filtroConclusaoPrazo } = useFiltrosStore();

  // Verificar se o usuário é admin
  const canViewAllCorretores = userRole === "admin";

  // Aplicar filtros
  let metasFiltradas = metas || [];

  // Separar metas ativas e concluídas
  const metasAtivas = metasFiltradas.filter((m) => m.status !== "concluida" || !m.finalizada_em);
  const metasConcluidas = metasFiltradas.filter((m) => m.status === "concluida" && m.finalizada_em);

  // Preparar também a lista de concluídas filtrada (para o Histórico)
  let metasConcluidasFiltradas = metasConcluidas;
  if (dataInicio) {
    metasConcluidasFiltradas = metasConcluidasFiltradas.filter((meta) => new Date(meta.data_prazo) >= dataInicio);
  }
  if (dataFim) {
    metasConcluidasFiltradas = metasConcluidasFiltradas.filter((meta) => new Date(meta.data_prazo) <= dataFim);
  }
  if (filtroCorretor !== "todos") {
    metasConcluidasFiltradas = metasConcluidasFiltradas.filter((meta) => meta.usuario_id === filtroCorretor);
  }
  if (filtroTipo !== "todos") {
    metasConcluidasFiltradas = metasConcluidasFiltradas.filter((meta) => meta.tipo === filtroTipo);
  }
  if (filtroReferencia !== "todos" && filtroReferencia.trim() !== "") {
    metasConcluidasFiltradas = metasConcluidasFiltradas.filter((meta) =>
      meta.id.toLowerCase().includes(filtroReferencia.toLowerCase())
    );
  }
  if (filtroConclusaoPrazo !== "todos") {
    metasConcluidasFiltradas = metasConcluidasFiltradas.filter((meta) => meta.conclusao_prazo === filtroConclusaoPrazo);
  }

  // Usar metasAtivas para os filtros
  metasFiltradas = metasAtivas;

  if (dataInicio) {
    metasFiltradas = metasFiltradas.filter((meta) => new Date(meta.data_prazo) >= dataInicio);
  }

  if (dataFim) {
    metasFiltradas = metasFiltradas.filter((meta) => new Date(meta.data_prazo) <= dataFim);
  }

  if (filtroStatus !== "todos") {
    metasFiltradas = metasFiltradas.filter((meta) => meta.status === filtroStatus);
  }

  if (filtroCorretor !== "todos") {
    metasFiltradas = metasFiltradas.filter((meta) => meta.usuario_id === filtroCorretor);
  }

  if (filtroTipo !== "todos") {
    metasFiltradas = metasFiltradas.filter((meta) => meta.tipo === filtroTipo);
  }

  if (filtroReferencia !== "todos" && filtroReferencia.trim() !== "") {
    metasFiltradas = metasFiltradas.filter((meta) =>
      meta.id.toLowerCase().includes(filtroReferencia.toLowerCase())
    );
  }

  if (filtroConclusaoPrazo !== "todos") {
    metasFiltradas = metasFiltradas.filter((meta) => 
      meta.conclusao_prazo === filtroConclusaoPrazo && meta.conclusao_prazo !== null
    );
  }

  const toggleSection = (tipo: TipoMeta) => {
    setOpenSections((prev) => ({ ...prev, [tipo]: !prev[tipo] }));
  };

  // Função para ordenar metas por categoria e data de criação
  const sortMetas = (metas: Meta[]) => {
    return sortMetasByCategoria(metas);
  };

  // Agrupar metas filtradas por tipo e ordenar
  const metasPorTipo: Record<TipoMeta, Meta[]> = {
    diaria: sortMetas(metasFiltradas.filter((m) => m.tipo === "diaria")),
    semanal: sortMetas(metasFiltradas.filter((m) => m.tipo === "semanal")),
    mensal: sortMetas(metasFiltradas.filter((m) => m.tipo === "mensal")),
    anual: sortMetas(metasFiltradas.filter((m) => m.tipo === "anual")),
  };

  // Agrupar metas concluídas por tipo para histórico e ordenar por data (mais recente primeiro)
  const metasConcluidasPorTipo: Record<TipoMeta, Meta[]> = {
    diaria: metasConcluidasFiltradas
      .filter((meta) => meta.tipo === "diaria")
      .sort((a, b) => new Date(b.data_prazo).getTime() - new Date(a.data_prazo).getTime()),
    semanal: metasConcluidasFiltradas
      .filter((meta) => meta.tipo === "semanal")
      .sort((a, b) => new Date(b.data_prazo).getTime() - new Date(a.data_prazo).getTime()),
    mensal: metasConcluidasFiltradas
      .filter((meta) => meta.tipo === "mensal")
      .sort((a, b) => new Date(b.data_prazo).getTime() - new Date(a.data_prazo).getTime()),
    anual: metasConcluidasFiltradas
      .filter((meta) => meta.tipo === "anual")
      .sort((a, b) => new Date(b.data_prazo).getTime() - new Date(a.data_prazo).getTime()),
  };

  const handleToggleSelecao = (id: string, selected: boolean) => {
    setMetasSelecionadas((prev) => {
      const newSet = new Set(prev);
      if (selected) {
        newSet.add(id);
      } else {
        newSet.delete(id);
      }
      return newSet;
    });
  };

  const handleSelecionarTodas = () => {
    // Determinar quais metas usar baseado na aba ativa
    let metasParaSelecionar: Meta[] = [];

    if (activeTab === "historico") {
      metasParaSelecionar = metasConcluidasFiltradas;
    } else if (activeTab === "todas") {
      // Na aba "todas", selecionar tanto as ativas quanto as concluídas
      metasParaSelecionar = [...metasFiltradas, ...metasConcluidasFiltradas];
    } else {
      // Para abas específicas de tipo
      metasParaSelecionar = metasPorTipo[activeTab as TipoMeta] || [];
    }

    const totalMetasVisiveis = metasParaSelecionar.length;

    if (metasSelecionadas.size === totalMetasVisiveis && totalMetasVisiveis > 0) {
      setMetasSelecionadas(new Set());
    } else {
      setMetasSelecionadas(new Set(metasParaSelecionar.map((m) => m.id)));
    }
  };

  const handleExcluirMeta = async () => {
    if (!metaParaExcluir) return;
    
    console.log("Tentando excluir meta com ID:", metaParaExcluir);
    try {
      await deleteMeta.mutateAsync(metaParaExcluir);
      console.log("Meta excluída com sucesso:", metaParaExcluir);

      toast({
        title: "Sucesso!",
        description: "Meta excluída com sucesso.",
      });
      setMetaParaExcluir(null);
    } catch (error: any) {
      console.error("Erro ao excluir meta:", error);
      toast({
        title: "Erro",
        description: error?.message || "Erro ao excluir meta.",
        variant: "destructive",
      });
    }
  };

  const handleExcluirSelecionadas = async () => {
    if (metasSelecionadas.size === 0) return;

    const quantidade = metasSelecionadas.size;
    const idsArray = Array.from(metasSelecionadas);
    console.log("Tentando excluir metas selecionadas:", idsArray);

    try {
      const promises = idsArray.map((id) => {
        console.log("Excluindo meta ID:", id);
        return deleteMeta.mutateAsync(id);
      });

      await Promise.all(promises);

      console.log("Todas as metas foram excluídas com sucesso");
      setMetasSelecionadas(new Set());
      setModoSelecao(false);
      setConfirmarExclusaoMassa(false);

      toast({
        title: "Sucesso!",
        description: `${quantidade} meta(s) excluída(s) com sucesso.`,
      });
    } catch (error: any) {
      console.error("Erro ao excluir metas:", error);
      toast({
        title: "Erro",
        description: error?.message || "Erro ao excluir metas selecionadas.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header com botões de ação */}
      <div className="flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex-1">
            <h1 className="text-2xl sm:text-3xl font-bold">Metas</h1>
            <p className="text-sm text-muted-foreground">Gerencie e acompanhe suas metas</p>
          </div>
          {/* Container fixo para botões - mantém posição consistente */}
          <div className="flex flex-wrap gap-2">
            {modoSelecao ? (
              <>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setModoSelecao(false);
                    setMetasSelecionadas(new Set());
                  }}
                >
                  Cancelar
                </Button>
                <Button
                  variant="outline"
                  onClick={handleSelecionarTodas}
                  disabled={
                    activeTab === "historico"
                      ? metasConcluidasFiltradas.length === 0
                      : activeTab === "todas"
                        ? (metasFiltradas.length + metasConcluidasFiltradas.length) === 0
                        : (metasPorTipo[activeTab as TipoMeta]?.length || 0) === 0
                  }
                >
                  <CheckSquare className="mr-2 h-4 w-4" />
                  {(() => {
                    const totalVisiveis =
                      activeTab === "historico"
                        ? metasConcluidasFiltradas.length
                        : activeTab === "todas"
                          ? metasFiltradas.length + metasConcluidasFiltradas.length
                          : metasPorTipo[activeTab as TipoMeta]?.length || 0;
                    return metasSelecionadas.size === totalVisiveis && totalVisiveis > 0
                      ? "Desmarcar Todas"
                      : "Selecionar Todas";
                  })()}
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => setConfirmarExclusaoMassa(true)}
                  disabled={metasSelecionadas.size === 0 || deleteMeta.isPending}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Excluir ({metasSelecionadas.size})
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={() => setModoSelecao(true)} disabled={!metas || metas.length === 0}>
                  <CheckSquare className="mr-2 h-4 w-4" />
                  Selecionar
                </Button>
                <NovaMetaModal />
                <ConfiguracoesMetasModal />
              </>
            )}
          </div>
        </div>

        {/* Filtros */}
        <FiltrosMetas modoSelecao={false} setModoSelecao={() => {}} hasMetas={false} />
      </div>

      {/* Metas por Tipo - Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="todas">Todas ({metasFiltradas.length})</TabsTrigger>
          <TabsTrigger value="diaria">Diárias ({metasPorTipo.diaria.length})</TabsTrigger>
          <TabsTrigger value="semanal">Semanais ({metasPorTipo.semanal.length})</TabsTrigger>
          <TabsTrigger value="mensal">Mensais ({metasPorTipo.mensal.length})</TabsTrigger>
          <TabsTrigger value="anual">Anuais ({metasPorTipo.anual.length})</TabsTrigger>
          <TabsTrigger value="historico">Histórico ({metasConcluidasFiltradas.length})</TabsTrigger>
        </TabsList>

        {/* Aba Todas - Mostra todas as seções */}
        <TabsContent value="todas" className="mt-6">
          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <Skeleton className="h-48" />
              <Skeleton className="h-48" />
              <Skeleton className="h-48" />
            </div>
          ) : metasFiltradas.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <div className="text-muted-foreground text-center">
                  <p className="text-lg mb-2">Nenhuma meta encontrada</p>
                  <p className="text-sm">
                    {metas && metas.length > 0
                      ? "Ajuste os filtros para ver mais metas"
                      : "Crie uma nova meta para começar"}
                  </p>
                </div>
                <div className="mt-4">
                  <NovaMetaModal />
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {(["diaria", "semanal", "mensal", "anual"] as TipoMeta[]).map((tipo) => {
                const metasDoTipo = metasPorTipo[tipo];

                if (metasDoTipo.length === 0) return null;

                return (
                  <Collapsible key={tipo} open={openSections[tipo]} onOpenChange={() => toggleSection(tipo)}>
                    <CollapsibleTrigger className="group flex items-center gap-2 w-full hover:bg-muted/50 rounded-md p-2 transition-colors">
                      <ChevronDown
                        className={`h-5 w-5 transition-transform ${openSections[tipo] ? "rotate-0" : "-rotate-90"}`}
                      />
                      <h3 className="text-xl font-semibold text-foreground">
                        {tipoMetaLabels[tipo]} ({metasDoTipo.length})
                      </h3>
                    </CollapsibleTrigger>

                    <CollapsibleContent className="mt-4 ml-7">
                      <MetasDraggableSection
                        metas={metasDoTipo}
                        tipo={tipo}
                        onEdit={(meta) => setSelectedMeta(meta)}
                        onDelete={(id) => setMetaParaExcluir(id)}
                        onReorder={(metasIds) => reordenarMetas(tipo, metasIds)}
                        isSelectable={modoSelecao}
                        selectedIds={metasSelecionadas}
                        onSelect={handleToggleSelecao}
                      />
                    </CollapsibleContent>
                  </Collapsible>
                );
              })}
            </div>
          )}
        </TabsContent>

        {/* Abas individuais por tipo */}
        {(["diaria", "semanal", "mensal", "anual"] as TipoMeta[]).map((tipo) => {
          const metasDoTipo = metasPorTipo[tipo];

          return (
            <TabsContent key={tipo} value={tipo} className="mt-6">
              {isLoading ? (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  <Skeleton className="h-48" />
                  <Skeleton className="h-48" />
                  <Skeleton className="h-48" />
                </div>
              ) : metasDoTipo.length === 0 ? (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-12">
                    <div className="text-muted-foreground text-center">
                      <p className="text-lg mb-2">Nenhuma meta {tipoMetaLabels[tipo].toLowerCase()} encontrada</p>
                      <p className="text-sm">
                        {metas && metas.length > 0
                          ? "Ajuste os filtros ou crie uma nova meta"
                          : "Crie uma nova meta para começar"}
                      </p>
                    </div>
                    <div className="mt-4">
                      <NovaMetaModal />
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <MetasDraggableSection
                  metas={metasDoTipo}
                  tipo={tipo}
                  onEdit={(meta) => setSelectedMeta(meta)}
                  onDelete={(id) => setMetaParaExcluir(id)}
                  onReorder={(metasIds) => reordenarMetas(tipo, metasIds)}
                  isSelectable={modoSelecao}
                  selectedIds={metasSelecionadas}
                  onSelect={handleToggleSelecao}
                />
              )}
            </TabsContent>
          );
        })}

        {/* Aba Histórico */}
        <TabsContent value="historico" className="mt-6">
          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <Skeleton className="h-48" />
            </div>
          ) : metasConcluidas.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <div className="text-muted-foreground text-center">
                  <p className="text-lg mb-2">Nenhuma meta concluída</p>
                  <p className="text-sm">Metas concluídas aparecerão aqui</p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {(["diaria", "semanal", "mensal", "anual"] as TipoMeta[]).map((tipo) => {
                const metasDoTipo = metasConcluidasPorTipo[tipo];
                if (metasDoTipo.length === 0) return null;

                return (
                  <Collapsible 
                    key={tipo} 
                    open={openSections[tipo]} 
                    onOpenChange={() => toggleSection(tipo)}
                  >
                    <CollapsibleTrigger className="group flex items-center gap-2 w-full hover:bg-muted/50 rounded-md p-2 transition-colors">
                      <ChevronDown
                        className={`h-5 w-5 transition-transform ${openSections[tipo] ? "rotate-0" : "-rotate-90"}`}
                      />
                      <h3 className="text-xl font-semibold text-foreground">
                        {tipoMetaLabels[tipo]} ({metasDoTipo.length})
                      </h3>
                    </CollapsibleTrigger>

                    <CollapsibleContent className="mt-4 ml-7">
                        <MetasDraggableSection
                          metas={metasDoTipo}
                          tipo={tipo}
                          onEdit={(meta) => setSelectedMeta(meta)}
                          onDelete={(id) => setMetaParaExcluir(id)}
                          onReorder={(metasIds) => reordenarMetas(tipo, metasIds)}
                          isSelectable={modoSelecao}
                          selectedIds={metasSelecionadas}
                          onSelect={handleToggleSelecao}
                        />
                    </CollapsibleContent>
                  </Collapsible>
                );
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Modal de Detalhes */}
      {selectedMeta && (
        <MetaDetalhesModal
          meta={selectedMeta}
          open={!!selectedMeta}
          onOpenChange={(open) => !open && setSelectedMeta(null)}
        />
      )}

      {/* Confirmação de exclusão individual */}
      <AlertDialog open={!!metaParaExcluir} onOpenChange={() => setMetaParaExcluir(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar exclusão</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir esta meta? Esta ação é irreversível e todos os dados associados serão permanentemente removidos.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleExcluirMeta}
              className="bg-destructive hover:bg-destructive/90"
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Confirmação de exclusão em massa */}
      <AlertDialog open={confirmarExclusaoMassa} onOpenChange={setConfirmarExclusaoMassa}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar exclusão de múltiplas metas</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir {metasSelecionadas.size} meta(s)? Esta ação é irreversível e todos os dados associados serão permanentemente removidos.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleExcluirSelecionadas}
              className="bg-destructive hover:bg-destructive/90"
            >
              Excluir Todas
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
