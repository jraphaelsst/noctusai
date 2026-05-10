import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@noctusai/seed/components/ui/dialog";
import { Meta } from "@/types";
import { Card, CardContent } from "@noctusai/seed/components/ui/card";
import { Badge } from "@noctusai/seed/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@noctusai/seed/components/ui/select";
import { Button } from "@noctusai/seed/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@noctusai/seed/components/ui/popover";
import { CalendarIcon, AlertTriangle, Target } from "lucide-react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { cn, formatDate } from "@/lib/utils";
import { categoriaLabels } from "@/lib/categorias";
import { useFiltrosStore } from "@/store/filtrosStore";
import { MetaDetalhesModal } from "./MetaDetalhesModal";

interface ImpedimentosModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  metas: Meta[];
}

const tipoMetaLabels = {
  diaria: "Diária",
  semanal: "Semanal",
  mensal: "Mensal",
  anual: "Anual",
};

const statusStyles = {
  aberta: "bg-primary/10 text-primary border-primary/20",
  concluida: "bg-success/10 text-success border-success/20",
  atrasada: "bg-danger/10 text-danger border-danger/20",
};

const statusLabels = {
  aberta: "Aberta",
  concluida: "Concluída",
  atrasada: "Atrasada",
};

// Função auxiliar para validar status
const getValidStatus = (status: string): keyof typeof statusStyles => {
  return ['aberta', 'concluida', 'atrasada'].includes(status) 
    ? (status as keyof typeof statusStyles)
    : 'aberta';
};

export function ImpedimentosModal({ open, onOpenChange, metas }: ImpedimentosModalProps) {
  const [selectedMeta, setSelectedMeta] = useState<Meta | null>(null);
  const [showMetaModal, setShowMetaModal] = useState(false);
  
  // Filtros locais do modal
  const [dataInicio, setDataInicio] = useState<Date>();
  const [dataFim, setDataFim] = useState<Date>();
  const [filtroTipo, setFiltroTipo] = useState<string>("todos");
  const [filtroCategoria, setFiltroCategoria] = useState<string>("todos");

  // Filtrar apenas metas com impedimento
  let metasComImpedimento = metas.filter(m => m.tem_impedimento);

  // Aplicar filtros
  if (dataInicio) {
    metasComImpedimento = metasComImpedimento.filter(meta => 
      new Date(meta.data_prazo) >= dataInicio
    );
  }

  if (dataFim) {
    metasComImpedimento = metasComImpedimento.filter(meta => 
      new Date(meta.data_prazo) <= dataFim
    );
  }

  if (filtroTipo !== "todos") {
    metasComImpedimento = metasComImpedimento.filter(meta => 
      meta.tipo === filtroTipo
    );
  }

  if (filtroCategoria !== "todos") {
    metasComImpedimento = metasComImpedimento.filter(meta => 
      meta.categoria === filtroCategoria
    );
  }

  const handleMetaClick = (meta: Meta) => {
    setSelectedMeta(meta);
    setShowMetaModal(true);
  };

  const limparFiltros = () => {
    setDataInicio(undefined);
    setDataFim(undefined);
    setFiltroTipo("todos");
    setFiltroCategoria("todos");
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-[95vw] sm:max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-6 w-6 text-warning" />
              <DialogTitle className="text-2xl font-semibold">Impedimentos Ativos</DialogTitle>
            </div>
            <DialogDescription>
              Metas que possuem impedimentos identificados - {metasComImpedimento.length} {metasComImpedimento.length === 1 ? 'impedimento' : 'impedimentos'}
            </DialogDescription>
          </DialogHeader>

          {/* Filtros */}
          <div className="space-y-4 border-t border-b py-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Data Início */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Data Início</label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className={cn(
                        "w-full justify-start text-left font-normal",
                        !dataInicio && "text-muted-foreground"
                      )}
                    >
                      <CalendarIcon className="mr-2 h-4 w-4" />
                      {dataInicio ? format(dataInicio, "dd/MM/yyyy") : "Selecione"}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      mode="single"
                      selected={dataInicio}
                      onSelect={setDataInicio}
                      locale={ptBR}
                    />
                  </PopoverContent>
                </Popover>
              </div>

              {/* Data Fim */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Data Fim</label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className={cn(
                        "w-full justify-start text-left font-normal",
                        !dataFim && "text-muted-foreground"
                      )}
                    >
                      <CalendarIcon className="mr-2 h-4 w-4" />
                      {dataFim ? format(dataFim, "dd/MM/yyyy") : "Selecione"}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      mode="single"
                      selected={dataFim}
                      onSelect={setDataFim}
                      locale={ptBR}
                    />
                  </PopoverContent>
                </Popover>
              </div>

              {/* Tipo */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Periodicidade</label>
                  <Select value={filtroTipo} onValueChange={setFiltroTipo}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione a periodicidade" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="todos">Todas</SelectItem>
                    <SelectItem value="diaria">Diárias</SelectItem>
                    <SelectItem value="semanal">Semanais</SelectItem>
                    <SelectItem value="mensal">Mensais</SelectItem>
                    <SelectItem value="anual">Anuais</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Categoria */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Categoria</label>
                  <Select value={filtroCategoria} onValueChange={setFiltroCategoria}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione a categoria" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="todos">Todas</SelectItem>
                    <SelectItem value="captacao">Captação</SelectItem>
                    <SelectItem value="visitas">Visitas</SelectItem>
                    <SelectItem value="contatos">Contatos</SelectItem>
                    <SelectItem value="propostas">Propostas</SelectItem>
                    <SelectItem value="fechamento">Fechamento</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={limparFiltros}>
                Limpar Filtros
              </Button>
            </div>
          </div>

          {/* Lista de Impedimentos */}
          <div className="space-y-3">
            {metasComImpedimento.length === 0 ? (
              <div className="text-center py-12">
                <Target className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
                <p className="text-muted-foreground">
                  Nenhum impedimento encontrado com os filtros selecionados
                </p>
              </div>
            ) : (
              metasComImpedimento.map((meta) => (
                <Card 
                  key={meta.id} 
                  className="cursor-pointer hover:shadow-md transition-all hover:scale-[1.01] bg-warning/5 border-warning/20"
                  onClick={() => handleMetaClick(meta)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start gap-4">
                      <div className="flex-shrink-0 mt-1">
                        <div className="w-10 h-10 rounded-full bg-warning/20 flex items-center justify-center">
                          <AlertTriangle className="h-5 w-5 text-warning" />
                        </div>
                      </div>
                      
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-4 mb-2">
                          <div className="flex-1">
                            <h4 className="font-semibold text-base mb-1">
                              {categoriaLabels[meta.categoria]} - {tipoMetaLabels[meta.tipo]}
                            </h4>
                            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                              <span className="flex items-center gap-1">
                                <CalendarIcon className="h-3 w-3" />
                                {formatDate(meta.data_prazo)}
                              </span>
                              <span>•</span>
                              <span>
                                {meta.meta_realizada || 0}/{meta.meta_pretendida}
                              </span>
                              <Badge variant="outline" className={cn("ml-2", statusStyles[getValidStatus(meta.status)])}>
                                {statusLabels[getValidStatus(meta.status)]}
                              </Badge>
                            </div>
                          </div>
                        </div>
                        
                        <div className="bg-warning/10 rounded-md p-3 mt-2 border border-warning/20">
                          <p className="text-sm text-foreground leading-relaxed">
                            <strong className="text-warning-foreground">Motivo:</strong> {meta.motivo_impedimento}
                          </p>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Modal de detalhes da meta */}
      {selectedMeta && (
        <MetaDetalhesModal
          meta={selectedMeta}
          open={showMetaModal}
          onOpenChange={(open) => {
            setShowMetaModal(open);
            if (!open) setSelectedMeta(null);
          }}
        />
      )}
    </>
  );
}
