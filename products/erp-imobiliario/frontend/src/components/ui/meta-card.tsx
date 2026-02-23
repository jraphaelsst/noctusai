import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { cn, formatDate } from "@/lib/utils";
import { Meta, CategoriaMeta } from "@/types";
import { Calendar, Target, TrendingUp, Edit, Check, X, User, Clock, Activity, Percent } from "lucide-react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { useState, memo, useMemo } from "react";
import { useUpdateMeta } from "@/hooks/useMetas";
import { useUserRole } from "@/hooks/useUserRole";
import { useConcluirMetaAgrupada } from "@/hooks/useConcluirMetaAgrupada";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Info, ArrowRight, ArrowLeft } from "lucide-react";
import { categoriaLabels as categoriaMetaLabels, getDisplayCategoria } from "@/lib/categorias";

interface MetaCardProps {
  meta: Meta;
  onEdit?: (meta: Meta) => void;
  onDelete?: (id: string) => void;
  isSelectable?: boolean;
  isSelected?: boolean;
  onSelect?: (id: string, selected: boolean) => void;
}


const statusStyles = {
  aberta: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  concluida: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  atrasada: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
};

const statusLabels = {
  aberta: "Aberta",
  concluida: "Concluída",
  atrasada: "Atrasada",
};

export const MetaCard = memo(function MetaCard({ meta, onEdit, onDelete, isSelectable, isSelected, onSelect }: MetaCardProps) {
  const [metaRealizada, setMetaRealizada] = useState(meta.meta_realizada || 0);
  const [isEditing, setIsEditing] = useState(false);
  const [isEditingNome, setIsEditingNome] = useState(false);
  const [nomeEdit, setNomeEdit] = useState(meta.nome || '');
  const updateMeta = useUpdateMeta();
  const concluirAgrupada = useConcluirMetaAgrupada();
  const { data: userRole } = useUserRole();
  
  const isAgregada = ['semanal', 'mensal', 'anual'].includes(meta.tipo);
  const progress = useMemo(() => 
    meta.meta_realizada ? (meta.meta_realizada / meta.meta_pretendida) * 100 : 0,
    [meta.meta_realizada, meta.meta_pretendida]
  );

  const isOverdue = (meta.dias_restantes ?? 0) < 0 && meta.status !== 'concluida';
  const canViewAllCorretores = userRole === 'admin';
  const podeConclui = isAgregada ? (meta.meta_realizada || 0) >= meta.meta_pretendida : true;
  
  // Usar o status do banco de dados com validação
  const validStatus = ['aberta', 'concluida', 'atrasada'].includes(meta.status) 
    ? meta.status 
    : 'aberta'; // fallback para status inválido
  const displayStatus = validStatus;

  // Sistema de cores baseado no progresso
  const getProgressColor = (progress: number) => {
    if (progress >= 95) return 'bg-success';
    if (progress >= 85) return 'bg-info';
    if (progress >= 60) return 'bg-warning';
    if (progress > 30) return 'bg-secondary';
    return 'bg-danger';
  };
  
  // Cálculos de estatísticas - usar dias_restantes do banco
  const diasRestantes = meta.dias_restantes ?? 0;
  const diasAtraso = diasRestantes < 0 ? Math.abs(diasRestantes) : 0;
  const faltaRealizar = Math.max(0, meta.meta_pretendida - (meta.meta_realizada || 0));
  const taxaPerformance = progress;
  
  // Usar o nível de performance armazenado no banco
  const performanceStatus = meta.nivel_performance || 'baixo';
  
  // Labels de performance
  const performanceLabels = {
    excelente: "Excelente",
    bom: "Bom",
    regular: "Regular",
    baixo: "Baixo"
  };

  const handleSaveRealizada = async () => {
    await updateMeta.mutateAsync({
      id: meta.id,
      meta_realizada: metaRealizada,
    });
    setIsEditing(false);
  };

  const handleSaveNome = async () => {
    await updateMeta.mutateAsync({
      id: meta.id,
      nome: nomeEdit || null,
    });
    setIsEditingNome(false);
  };

  const handleConcluir = async () => {
    if (isAgregada) {
      await concluirAgrupada.mutateAsync(meta.id);
    } else {
      await updateMeta.mutateAsync({
        id: meta.id,
        status: 'concluida',
        meta_realizada: meta.meta_pretendida,
        finalizada_em: new Date().toISOString(),
        finalizada_no_prazo: !isOverdue,
      });
    }
  };

  return (
    <HoverCard openDelay={200} closeDelay={100}>
      <HoverCardTrigger asChild>
        <Card className={cn(
          "transition-all hover:shadow-lg hover:scale-[1.02] cursor-pointer group relative",
          isOverdue && "border-danger/30 bg-danger-light/10",
          isSelected && "border-primary border-2 bg-primary/5"
        )}
        onClick={(e) => {
          if (isSelectable) {
            e.stopPropagation();
            onSelect?.(meta.id, !isSelected);
          } else {
            onEdit?.(meta);
          }
        }}
        >
          {isSelectable && (
            <div className="absolute top-3 left-3 z-10" onClick={(e) => e.stopPropagation()}>
              <Checkbox
                checked={isSelected}
                onCheckedChange={(checked) => onSelect?.(meta.id, checked as boolean)}
                className="h-5 w-5"
              />
            </div>
          )}
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className={cn("flex-1", isSelectable && "ml-8")}>
                <div className="flex items-center gap-2">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Target className="h-5 w-5 text-primary" />
                    {categoriaMetaLabels[meta.categoria]}
                  </CardTitle>
                </div>
                {meta.nome && (
                  <p className="text-sm font-medium text-foreground mt-1">{meta.nome}</p>
                )}
                <p className="text-xs text-muted-foreground mt-1">Ref: {meta.id}</p>
                {canViewAllCorretores && meta.usuario && (
                  <div className="flex items-center gap-1 mt-1">
                    <User className="h-3 w-3 text-muted-foreground" />
                    <p className="text-xs font-medium text-muted-foreground">
                      {meta.usuario.nome}
                    </p>
                  </div>
                )}
              </div>
              <Badge className={statusStyles[displayStatus]}>
                {statusLabels[displayStatus]}
              </Badge>
            </div>
          </CardHeader>
          
          <CardContent className="space-y-4">
            <div className="space-y-3">
              {/* Estatísticas Principais */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="bg-muted/50 rounded-lg p-3 space-y-1">
                  <div className="flex items-center gap-1.5">
                    <Activity className="h-3.5 w-3.5 text-primary" />
                    <span className="text-xs font-medium text-muted-foreground">Performance</span>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <span className="text-lg font-bold text-foreground">{taxaPerformance.toFixed(0)}%</span>
                    <Badge 
                      className={cn(
                        "text-[10px] h-4 px-1",
                        performanceStatus === "excelente" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" :
                        performanceStatus === "bom" ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" :
                        performanceStatus === "regular" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300" :
                        "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300"
                      )}
                    >
                      {performanceLabels[performanceStatus]}
                    </Badge>
                  </div>
                </div>
                
                <div className="bg-muted/50 rounded-lg p-3 space-y-1">
                  <div className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5 text-primary" />
                    <span className="text-xs font-medium text-muted-foreground">Prazo</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-lg font-bold text-foreground">
                      {isOverdue ? diasAtraso : diasRestantes}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {isOverdue ? `dias atrasado${diasAtraso > 1 ? 's' : ''}` : 
                       diasRestantes === 0 ? 'vence hoje' :
                       diasRestantes === 1 ? 'vence amanhã' :
                       `dias restantes`}
                    </span>
                  </div>
                </div>
              </div>

              {/* Data do Prazo */}
              <div className="flex items-center justify-between border-t pt-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Calendar className="h-4 w-4" />
                  {formatDate(meta.data_prazo)}
                </div>
                {meta.status === 'concluida' && meta.finalizada_no_prazo && (
                  <Badge variant="default" className="text-xs bg-success">
                    ✓ No prazo
                  </Badge>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex flex-wrap justify-between text-sm gap-2">
                <span className="text-muted-foreground">Progresso</span>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">
                    {meta.meta_realizada || 0} / {meta.meta_pretendida}
                  </span>
                  {faltaRealizar > 0 && meta.status !== 'concluida' && (
                    <Badge variant="outline" className="text-[10px] h-4 px-1 whitespace-nowrap">
                      faltam {faltaRealizar}
                    </Badge>
                  )}
                </div>
              </div>
              <Progress 
                value={progress} 
                className="h-2"
                indicatorClassName={getProgressColor(progress)}
              />
              <div className="flex flex-wrap justify-between text-xs text-muted-foreground gap-2">
                <span className="whitespace-nowrap">{progress.toFixed(1)}% concluído</span>
                <div className="flex items-center gap-1">
                  <TrendingUp className="h-3 w-3 flex-shrink-0" />
                  <span className="whitespace-nowrap">
                    {progress >= 100 ? "Meta atingida!" : 
                     progress >= 80 ? "Quase lá!" : 
                     faltaRealizar > 0 ? `Faltam ${faltaRealizar}` : "Continue focado!"}
                  </span>
                </div>
              </div>
              
              {isAgregada && (meta.carry_in! > 0 || meta.carry_out! > 0) && (
                <div className="flex flex-wrap gap-2 pt-2 border-t">
                  {meta.carry_in! > 0 && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Badge variant="secondary" className="text-xs flex items-center gap-1">
                            <ArrowLeft className="h-3 w-3" />
                            Carry-in: +{meta.carry_in}
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p className="text-xs">Excedente recebido do período anterior</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                  {meta.carry_out! > 0 && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Badge variant="secondary" className="text-xs flex items-center gap-1">
                            <ArrowRight className="h-3 w-3" />
                            Carry-out: +{meta.carry_out}
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p className="text-xs">Excedente para o próximo período</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </HoverCardTrigger>
      
      <HoverCardContent 
        side="right" 
        align="start" 
        className="w-80 z-50 animate-in fade-in-0 slide-in-from-left-2 duration-400"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-4">
          <div className="flex items-center gap-2 border-b pb-2">
            <Edit className="h-4 w-4 text-primary" />
            <h4 className="font-semibold">{isAgregada ? 'Visualização Rápida' : 'Edição Rápida'}</h4>
          </div>
          
          {isAgregada ? (
            <div className="space-y-3">
              <div className="rounded-lg bg-muted p-3 space-y-2">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Info className="h-3 w-3" />
                  Esta meta é calculada automaticamente
                </p>
                <p className="text-xs text-muted-foreground">
                  Os valores são derivados das metas diárias do período, com limite (cap) e carry-over.
                </p>
              </div>
              
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Meta Pretendida:</span>
                  <span className="font-medium">{meta.meta_pretendida}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Meta Realizada (Cap):</span>
                  <span className="font-medium">{meta.meta_realizada || 0}</span>
                </div>
                {meta.carry_in! > 0 && (
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Carry-in recebido:</span>
                    <span className="font-medium text-success">+{meta.carry_in}</span>
                  </div>
                )}
                {meta.carry_out! > 0 && (
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Carry-out gerado:</span>
                    <span className="font-medium text-warning">+{meta.carry_out}</span>
                  </div>
                )}
              </div>
              
              {meta.status !== 'concluida' && podeConclui && (
                <Button 
                  onClick={handleConcluir}
                  className="w-full h-8 text-xs"
                  disabled={concluirAgrupada.isPending}
                >
                  <Check className="h-3 w-3 mr-1" />
                  Marcar como Concluída
                </Button>
              )}
              
              {!podeConclui && meta.status !== 'concluida' && (
                <p className="text-xs text-muted-foreground text-center p-2 bg-muted rounded">
                  Complete {meta.meta_pretendida} para poder concluir
                </p>
              )}
              
              <div className="flex gap-2">
                <Button 
                  onClick={() => onEdit?.(meta)}
                  variant="outline"
                  className="flex-1 h-8 text-xs"
                >
                  Ver Detalhes
                </Button>
                {onDelete && (
                  <Button 
                    onClick={(e) => {
                      e.stopPropagation();
                      console.log("MetaCard: Clique em excluir para meta:", meta.id);
                      onDelete(meta.id);
                    }}
                    variant="destructive"
                    size="icon"
                    className="h-8 w-8"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Nome da Meta - Editável */}
              <div className="space-y-2">
                <Label htmlFor={`meta-nome-${meta.id}`} className="text-xs">
                  Nome da Meta
                </Label>
                <div className="flex gap-2">
                  {isEditingNome ? (
                    <>
                      <Input
                        id={`meta-nome-${meta.id}`}
                        value={nomeEdit}
                        onChange={(e) => setNomeEdit(e.target.value)}
                        placeholder="Ex: Captação Q1 2025"
                        maxLength={100}
                        className="h-8 flex-1"
                      />
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={handleSaveNome}
                        disabled={updateMeta.isPending}
                      >
                        <Check className="h-4 w-4 text-success" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => {
                          setNomeEdit(meta.nome || '');
                          setIsEditingNome(false);
                        }}
                      >
                        <X className="h-4 w-4 text-muted-foreground" />
                      </Button>
                    </>
                  ) : (
                    <>
                      <div className="flex-1 h-8 flex items-center px-3 border border-border rounded-md bg-muted/30">
                        <span className="text-sm text-muted-foreground">
                          {meta.nome || 'Sem nome'}
                        </span>
                      </div>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => setIsEditingNome(true)}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor={`meta-realizada-${meta.id}`} className="text-xs">
                  Meta Realizada
                </Label>
                <div className="flex gap-2">
                  <Input
                    id={`meta-realizada-${meta.id}`}
                    type="number"
                    min="0"
                    max={meta.meta_pretendida}
                    value={metaRealizada}
                    onChange={(e) => {
                      setMetaRealizada(Number(e.target.value));
                      setIsEditing(true);
                    }}
                    className="h-8"
                  />
                  {isEditing && (
                    <div className="flex gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={handleSaveRealizada}
                        disabled={updateMeta.isPending}
                      >
                        <Check className="h-4 w-4 text-success" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => {
                          setMetaRealizada(meta.meta_realizada || 0);
                          setIsEditing(false);
                        }}
                      >
                        <X className="h-4 w-4 text-muted-foreground" />
                      </Button>
                    </div>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Meta pretendida: {meta.meta_pretendida}
                </p>
              </div>
              
              {meta.status !== 'concluida' && (
                <Button 
                  onClick={handleConcluir}
                  className="w-full h-8 text-xs"
                  disabled={updateMeta.isPending}
                >
                  <Check className="h-3 w-3 mr-1" />
                  Marcar como Concluída
                </Button>
              )}
              
              <div className="flex gap-2">
                <Button 
                  onClick={() => onEdit?.(meta)}
                  variant="outline"
                  className="flex-1 h-8 text-xs"
                >
                  Abrir Detalhes
                </Button>
                {onDelete && (
                  <Button 
                    onClick={(e) => {
                      e.stopPropagation();
                      console.log("MetaCard: Clique em excluir para meta:", meta.id);
                      onDelete(meta.id);
                    }}
                    variant="destructive"
                    size="icon"
                    className="h-8 w-8"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
});