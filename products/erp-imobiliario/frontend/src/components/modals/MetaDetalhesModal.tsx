import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Calendar, Target, TrendingUp, Edit2, X, Save, Trash2, RotateCcw, AlertTriangle, Activity, Clock, ArrowLeft, ArrowRight, Check } from "lucide-react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { Meta, TipoMeta, StatusMeta, CategoriaMeta } from "@/types";
import { useUpdateMeta, useDeleteMeta } from "@/hooks/useMetas";
import { useIsAdmin, useUserRole } from "@/hooks/useUserRole";
import { cn, formatDate } from "@/lib/utils";
import { User } from "lucide-react";
import { categoriaLabels as categoriaMetaLabels, getDisplayCategoria } from "@/lib/categorias";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface MetaDetalhesModalProps {
  meta: Meta;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const tipoMetaLabels: Record<TipoMeta, string> = {
  diaria: "Diária",
  semanal: "Semanal",
  mensal: "Mensal",
  anual: "Anual",
};


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

export function MetaDetalhesModal({
  meta,
  open,
  onOpenChange,
}: MetaDetalhesModalProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isEditingNome, setIsEditingNome] = useState(false);
  const [showConcluirDialog, setShowConcluirDialog] = useState(false);
  const [showReabrirDialog, setShowReabrirDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [formData, setFormData] = useState({
    meta_realizada: meta.meta_realizada || 0,
    tem_impedimento: meta.tem_impedimento || false,
    motivo_impedimento: meta.motivo_impedimento || '',
    nome: meta.nome || '',
  });

  const updateMeta = useUpdateMeta();
  const deleteMeta = useDeleteMeta();
  const { isAdmin } = useIsAdmin();
  const { data: userRole } = useUserRole();
  const canViewAllCorretores = userRole === 'admin';

  const progress = formData.meta_realizada 
    ? (formData.meta_realizada / meta.meta_pretendida) * 100 
    : 0;

  const isOverdue = (meta.dias_restantes ?? 0) < 0 && meta.status !== 'concluida';
  const isAgregada = ['semanal', 'mensal', 'anual'].includes(meta.tipo);
  
  // Cálculos de estatísticas - usar dias_restantes do banco
  const diasRestantes = meta.dias_restantes ?? 0;
  const diasAtraso = diasRestantes < 0 ? Math.abs(diasRestantes) : 0;
  const faltaRealizar = Math.max(0, meta.meta_pretendida - (formData.meta_realizada || 0));
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
  
  // Sistema de cores baseado no progresso
  const getProgressColor = (progress: number) => {
    if (progress >= 95) return 'bg-success'; // 95-100%: verde
    if (progress >= 85) return 'bg-info'; // 85-94.99%: azul
    if (progress >= 60) return 'bg-warning'; // 60-84.99%: amarelo
    if (progress > 30) return 'bg-secondary'; // 30.01-59.99%: laranja
    return 'bg-danger'; // 0-30%: vermelho
  };
  
  // Usar o status do banco de dados com validação
  const validStatus = ['aberta', 'concluida', 'atrasada'].includes(meta.status) 
    ? meta.status 
    : 'aberta'; // fallback para status inválido
  const currentStatus = validStatus;
  
  // Determinar se a meta pode ser editada baseado nas regras de negócio
  const canEditMeta = () => {
    // Metas agregadas (semanal, anual) NUNCA podem ser editadas manualmente
    if (meta.tipo === 'semanal' || meta.tipo === 'anual') {
      return false;
    }
    
    // Metas mensais só podem ser editadas por admins
    if (meta.tipo === 'mensal') {
      return isAdmin;
    }
    
    // Metas diárias podem ser editadas pelo dono (se não concluída) ou por admins
    if (meta.tipo === 'diaria') {
      if (isAdmin) return true;
      return meta.status !== 'concluida';
    }
    
    return false;
  };
  
  const canEdit = canEditMeta();
  
  // Mensagem de aviso quando não pode editar
  const getEditWarningMessage = () => {
    if (meta.tipo === 'semanal' || meta.tipo === 'anual') {
      return 'Metas agregadas são calculadas automaticamente e não podem ser editadas manualmente.';
    }
    if (meta.tipo === 'mensal' && !isAdmin) {
      return 'Apenas administradores podem editar metas mensais.';
    }
    if (meta.tipo === 'diaria' && meta.status === 'concluida' && !isAdmin) {
      return 'Metas concluídas não podem ser editadas. Contate um administrador.';
    }
    return '';
  };

  const handleEdit = () => {
    setIsEditing(true);
  };

  const handleCancel = () => {
    setIsEditing(false);
    setIsEditingNome(false);
    setFormData({
      meta_realizada: meta.meta_realizada || 0,
      tem_impedimento: meta.tem_impedimento || false,
      motivo_impedimento: meta.motivo_impedimento || '',
      nome: meta.nome || '',
    });
  };

  const handleSave = async () => {
    // Validar impedimento
    if (formData.tem_impedimento && (!formData.motivo_impedimento || formData.motivo_impedimento.trim().length < 10)) {
      return;
    }
    
    await updateMeta.mutateAsync({
      id: meta.id,
      meta_realizada: formData.meta_realizada,
      tem_impedimento: formData.tem_impedimento,
      motivo_impedimento: formData.tem_impedimento ? formData.motivo_impedimento : null,
      nome: formData.nome || null,
    });
    setIsEditing(false);
    setIsEditingNome(false);
    onOpenChange(false);
  };
  
  const handleSaveNome = async () => {
    await updateMeta.mutateAsync({
      id: meta.id,
      nome: formData.nome || null,
    });
    setIsEditingNome(false);
  };
  
  const handleConcluir = async () => {
    await updateMeta.mutateAsync({
      id: meta.id,
      status: 'concluida',
      finalizada_em: new Date().toISOString(),
      finalizada_no_prazo: !isOverdue,
    });
    setShowConcluirDialog(false);
    onOpenChange(false);
  };
  
  const handleReabrir = async () => {
    await updateMeta.mutateAsync({
      id: meta.id,
      status: 'aberta',
      finalizada_em: null,
      finalizada_no_prazo: null,
    });
    setShowReabrirDialog(false);
  };
  
  const handleDelete = async () => {
    await deleteMeta.mutateAsync(meta.id);
    setShowDeleteDialog(false);
    onOpenChange(false);
  };

  const handleInputChange = (field: string) => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const value = field === 'meta_pretendida' || field === 'meta_realizada'
      ? parseInt(e.target.value) || 0
      : e.target.value;
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            Detalhes da Meta
          </DialogTitle>
          <DialogDescription>
            Visualize e edite as informações da meta
          </DialogDescription>
        </DialogHeader>

        {isEditing ? (
          <form onSubmit={(e) => { e.preventDefault(); handleSave(); }} className="space-y-6">
            {/* Categoria e Tipo */}
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <div>
                  <h3 className="text-2xl font-bold">{categoriaMetaLabels[meta.categoria]}</h3>
                  {meta.nome && (
                    <p className="text-base font-medium text-foreground mt-2">
                      {meta.nome}
                    </p>
                  )}
                  <p className="text-sm text-muted-foreground mt-1">
                    Meta {tipoMetaLabels[meta.tipo]} • Ref: {meta.id}
                  </p>
                  {canViewAllCorretores && meta.usuario && (
                    <div className="flex items-center gap-1 mt-1">
                      <User className="h-4 w-4 text-muted-foreground" />
                      <p className="text-sm font-medium text-foreground">
                        {meta.usuario.nome}
                      </p>
                    </div>
                  )}
                </div>
              </div>
              <Badge className={statusStyles[currentStatus]}>
                {statusLabels[currentStatus]}
              </Badge>
            </div>

            {/* Nome da Meta - Editável */}
            <div className="space-y-2">
              <Label htmlFor="nome">Nome da Meta</Label>
              <div className="flex gap-2">
                <Input
                  id="nome"
                  value={formData.nome}
                  onChange={handleInputChange('nome')}
                  placeholder="Ex: Captação Q1 2025"
                  maxLength={100}
                  className="flex-1"
                />
              </div>
            </div>

            {/* Data Prazo - Não editável */}
            <div>
              <Label htmlFor="data_prazo">Data Prazo</Label>
              <div className="flex items-center gap-2 mt-1">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {meta.data_prazo.split('-').reverse().join('/')}
                </span>
              </div>
            </div>

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

            {/* Metas Pretendida e Realizada */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="meta_pretendida">Meta Pretendida</Label>
                <div className="text-2xl font-bold text-primary mt-1">
                  {meta.meta_pretendida}
                </div>
              </div>
              <div>
                <Label htmlFor="meta_realizada">Meta Realizada</Label>
                <Input
                  id="meta_realizada"
                  type="number"
                  value={formData.meta_realizada}
                  onChange={handleInputChange("meta_realizada")}
                  className="mt-1"
                  min="0"
                />
              </div>
            </div>

            {/* Impedimento */}
            <div className="space-y-4 border-t pt-4">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="tem_impedimento"
                  checked={formData.tem_impedimento}
                  onChange={(e) => setFormData({ 
                    ...formData, 
                    tem_impedimento: e.target.checked,
                    motivo_impedimento: e.target.checked ? formData.motivo_impedimento : ''
                  })}
                  className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                />
                <Label htmlFor="tem_impedimento" className="cursor-pointer font-medium flex items-center gap-2">
                  <Badge variant="outline" className="text-xs bg-warning/10 text-warning-foreground">
                    ⚠️ Impedimento
                  </Badge>
                  <span className="text-sm text-muted-foreground">Esta meta possui algum impedimento</span>
                </Label>
              </div>
              
              {formData.tem_impedimento && (
                <div className="ml-6 space-y-2 animate-in slide-in-from-top-2">
                  <Label htmlFor="motivo_impedimento" className="text-sm">
                    Motivo do Impedimento <span className="text-danger">*</span>
                  </Label>
                  <textarea
                    id="motivo_impedimento"
                    value={formData.motivo_impedimento}
                    onChange={(e) => setFormData({ 
                      ...formData, 
                      motivo_impedimento: e.target.value 
                    })}
                    className="w-full min-h-[100px] px-3 py-2 border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary resize-y"
                    placeholder="Descreva detalhadamente o impedimento que está bloqueando esta meta..."
                    maxLength={500}
                    required
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Mínimo 10 caracteres</span>
                    <span>{formData.motivo_impedimento.length}/500</span>
                  </div>
                  {formData.motivo_impedimento && formData.motivo_impedimento.trim().length < 10 && (
                    <p className="text-xs text-danger">
                      O motivo deve ter no mínimo 10 caracteres
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Progresso */}
            <div className={cn(
              "bg-muted/50 rounded-lg p-4",
              isOverdue && "bg-danger-light/10"
            )}>
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="h-5 w-5 text-primary" />
                <h4 className="font-semibold">Progresso da Meta</h4>
              </div>
              <div className="space-y-2">
                <div className="flex flex-wrap justify-between text-sm gap-2">
                  <span className="text-muted-foreground">Progresso</span>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">
                      {formData.meta_realizada} / {meta.meta_pretendida}
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
            </div>

            {/* Botões de Ação */}
            <div className="flex justify-between pt-4 border-t">
              <div>
                {/* Botão Excluir */}
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => setShowDeleteDialog(true)}
                  disabled={updateMeta.isPending || deleteMeta.isPending}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Excluir
                </Button>
              </div>
              
              <div className="flex gap-2">
                {/* Mensagem de aviso se não pode editar */}
                {!canEdit && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/50 px-3 py-1.5 rounded-md">
                    <Badge variant="outline" className="text-xs">
                      Bloqueado
                    </Badge>
                    <span>{getEditWarningMessage()}</span>
                  </div>
                )}
                
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleCancel}
                  disabled={updateMeta.isPending}
                >
                  <X className="h-4 w-4 mr-2" />
                  Cancelar
                </Button>
                <Button
                  type="submit"
                  disabled={updateMeta.isPending}
                >
                  <Save className="h-4 w-4 mr-2" />
                  {updateMeta.isPending ? "Salvando..." : "Salvar Alterações"}
                </Button>
              </div>
            </div>
          </form>
        ) : (
          <div className="space-y-6">
            {/* Categoria e Tipo */}
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <div>
                  <h3 className="text-2xl font-bold">{categoriaMetaLabels[meta.categoria]}</h3>
                  {(formData.nome || isEditingNome) && (
                    <div className="flex items-center gap-2 mt-2">
                      {isEditingNome ? (
                        <>
                          <Input
                            value={formData.nome}
                            onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                            placeholder="Ex: Captação Q1 2025"
                            maxLength={100}
                            className="flex-1 h-8 text-sm"
                          />
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={handleSaveNome}
                          >
                            <Check className="h-3 w-3" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={() => {
                              setIsEditingNome(false);
                              setFormData({ ...formData, nome: meta.nome || '' });
                            }}
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </>
                      ) : (
                        <>
                          <p className="text-base font-medium text-foreground">
                            {formData.nome}
                          </p>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7"
                            onClick={() => setIsEditingNome(true)}
                          >
                            <Edit2 className="h-3 w-3" />
                          </Button>
                        </>
                      )}
                    </div>
                  )}
                  {!formData.nome && !isEditingNome && (
                    <Button
                      variant="link"
                      size="sm"
                      className="h-auto p-0 text-xs text-muted-foreground hover:text-primary mt-1"
                      onClick={() => setIsEditingNome(true)}
                    >
                      + Adicionar nome
                    </Button>
                  )}
                  <p className="text-sm text-muted-foreground mt-1">
                    Meta {tipoMetaLabels[meta.tipo]} • Ref: {meta.id}
                  </p>
                  {canViewAllCorretores && meta.usuario && (
                    <div className="flex items-center gap-1 mt-1">
                      <User className="h-4 w-4 text-muted-foreground" />
                      <p className="text-sm font-medium text-foreground">
                        {meta.usuario.nome}
                      </p>
                    </div>
                  )}
                </div>
              </div>
              <Badge className={statusStyles[currentStatus]}>
                {statusLabels[currentStatus]}
              </Badge>
            </div>

            {/* Data Prazo - Não editável */}
            <div>
              <Label htmlFor="data_prazo">Data Prazo</Label>
              <div className="flex items-center gap-2 mt-1">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {meta.data_prazo.split('-').reverse().join('/')}
                </span>
              </div>
            </div>

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

            {/* Metas Pretendida e Realizada */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="meta_pretendida">Meta Pretendida</Label>
                <div className="text-2xl font-bold text-primary mt-1">
                  {meta.meta_pretendida}
                </div>
              </div>
              <div>
                <Label htmlFor="meta_realizada">Meta Realizada</Label>
                <div className="text-2xl font-bold text-success mt-1">
                  {formData.meta_realizada}
                </div>
              </div>
            </div>

            {/* Progresso */}
            <div className={cn(
              "bg-muted/50 rounded-lg p-4",
              isOverdue && "bg-danger-light/10"
            )}>
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="h-5 w-5 text-primary" />
                <h4 className="font-semibold">Progresso da Meta</h4>
              </div>
              <div className="space-y-2">
                <div className="flex flex-wrap justify-between text-sm gap-2">
                  <span className="text-muted-foreground">Progresso</span>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">
                      {formData.meta_realizada} / {meta.meta_pretendida}
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
            </div>

            {/* Impedimento */}
            {meta.tem_impedimento && (
              <div className="bg-warning/10 border border-warning/30 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-warning mt-0.5 flex-shrink-0" />
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      <h4 className="font-semibold text-warning-foreground">Impedimento Identificado</h4>
                      <Badge variant="outline" className="bg-warning/20 text-warning-foreground border-warning/40">
                        ⚠️ Atenção
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {meta.motivo_impedimento}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Informações Adicionais */}
            <div className="text-xs text-muted-foreground space-y-1">
              <p>Criada em: {formatDate(meta.created_at, true)}</p>
              <p>Última atualização: {formatDate(meta.updated_at, true)}</p>
              {meta.finalizada_em && (
                <p>Finalizada em: {formatDate(meta.finalizada_em, true)}</p>
              )}
            </div>

            {/* Botões de Ação */}
            <div className="flex flex-col gap-4 pt-4 border-t">
              {/* Mensagem de aviso se não pode editar */}
              {!canEdit && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/50 px-4 py-3 rounded-md border border-border">
                  <Badge variant="outline" className="text-xs">
                    🔒 Bloqueado
                  </Badge>
                  <span>{getEditWarningMessage()}</span>
                </div>
              )}
              
              <div className="flex justify-between">
                <div>
                  {/* Botão Excluir */}
                  <Button
                    variant="destructive"
                    onClick={() => setShowDeleteDialog(true)}
                    disabled={updateMeta.isPending || deleteMeta.isPending}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Excluir
                  </Button>
                </div>
                
                <div className="flex gap-2">
                  {/* Botão Reabrir (só para admins e metas concluídas) */}
                  {isAdmin && meta.status === 'concluida' && (
                    <Button
                      variant="outline"
                      onClick={() => setShowReabrirDialog(true)}
                      disabled={updateMeta.isPending}
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Reabrir Meta
                    </Button>
                  )}
                  
                  {/* Botão Concluir (só para metas não concluídas) */}
                  {meta.status !== 'concluida' && (
                    <Button
                      variant="default"
                      onClick={() => setShowConcluirDialog(true)}
                      disabled={updateMeta.isPending}
                      className="bg-success hover:bg-success/90"
                    >
                      <Target className="h-4 w-4 mr-2" />
                      Concluir Meta
                    </Button>
                  )}
                  
                  {/* Botão Editar (se pode editar) */}
                  {canEdit && (
                    <Button onClick={handleEdit} variant="outline">
                      <Edit2 className="h-4 w-4 mr-2" />
                      Editar Meta
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
        
        {/* Dialog de Confirmação para Concluir */}
        <AlertDialog open={showConcluirDialog} onOpenChange={setShowConcluirDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Concluir Meta?</AlertDialogTitle>
              <AlertDialogDescription>
                Tem certeza que deseja marcar esta meta como concluída? 
                {!isAdmin && " Esta ação não poderá ser desfeita."}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction 
                onClick={handleConcluir}
                className="bg-success hover:bg-success/90"
              >
                Sim, Concluir
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        
        {/* Dialog de Confirmação para Reabrir */}
        <AlertDialog open={showReabrirDialog} onOpenChange={setShowReabrirDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Reabrir Meta?</AlertDialogTitle>
              <AlertDialogDescription>
                Tem certeza que deseja reabrir esta meta? O status voltará para "Em Andamento".
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction onClick={handleReabrir}>
                Sim, Reabrir
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        
        {/* Dialog de Confirmação para Excluir */}
        <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Excluir Meta?</AlertDialogTitle>
              <AlertDialogDescription>
                Tem certeza que deseja excluir esta meta? Esta ação é irreversível e todos os dados associados serão permanentemente removidos.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction 
                onClick={handleDelete}
                className="bg-destructive hover:bg-destructive/90"
              >
                Sim, Excluir
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  );
}
