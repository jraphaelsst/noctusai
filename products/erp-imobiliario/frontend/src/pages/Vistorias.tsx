import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useVistorias,
  useCreateVistoria,
  useUpdateVistoria,
  useDeleteVistoria,
} from '@/hooks/useVistorias';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@noctusai/seed/components/ui/alert-dialog';
import {
  Search,
  Plus,
  ClipboardCheck,
  Camera,
  Trash2,
  Eye,
  Calendar,
  CheckCircle,
  Clock,
  XCircle,
} from 'lucide-react';
import { CardGridSkeleton } from '@/components/ui/page-skeleton';
import { formatDate } from '@/lib/utils';
import { VISTORIA_STATUS_CONFIG, VISTORIA_TIPO_CONFIG } from '@/lib/constants';
import { useAuthStore } from '@noctusai/seed/infra';
import type {
  Vistoria,
  TipoVistoria,
  StatusVistoria,
  ChecklistItem,
  EstadoChecklist,
} from '@/types/locacoes';

const TIPO_VARIANT: Record<TipoVistoria, 'default' | 'secondary' | 'outline'> = {
  entrada: 'default',
  saida: 'secondary',
  periodica: 'outline',
};

const STATUS_ICON: Record<StatusVistoria, { icon: typeof Clock; color: string }> = {
  agendada: { icon: Calendar, color: 'text-blue-500' },
  em_andamento: { icon: Clock, color: 'text-yellow-500' },
  concluida: { icon: CheckCircle, color: 'text-green-500' },
  cancelada: { icon: XCircle, color: 'text-red-500' },
};

const ESTADO_OPTIONS: { value: EstadoChecklist; label: string; color: string }[] = [
  { value: 'bom', label: 'Bom', color: 'bg-green-100 text-green-800' },
  { value: 'regular', label: 'Regular', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'ruim', label: 'Ruim', color: 'bg-red-100 text-red-800' },
  { value: 'NA', label: 'N/A', color: 'bg-gray-100 text-gray-800' },
];

const DEFAULT_CHECKLIST: ChecklistItem[] = [
  { item: 'Paredes', estado: 'bom', observacao: '' },
  { item: 'Teto / Forro', estado: 'bom', observacao: '' },
  { item: 'Piso', estado: 'bom', observacao: '' },
  { item: 'Portas', estado: 'bom', observacao: '' },
  { item: 'Janelas', estado: 'bom', observacao: '' },
  { item: 'Instalacao Eletrica', estado: 'bom', observacao: '' },
  { item: 'Instalacao Hidraulica', estado: 'bom', observacao: '' },
  { item: 'Torneiras / Registros', estado: 'bom', observacao: '' },
  { item: 'Vasos Sanitarios', estado: 'bom', observacao: '' },
  { item: 'Pintura', estado: 'bom', observacao: '' },
  { item: 'Vidros', estado: 'bom', observacao: '' },
  { item: 'Limpeza Geral', estado: 'bom', observacao: '' },
];

const vistoriaSchema = z.object({
  imovel_id: z.string().min(1, 'ID do imóvel é obrigatório'),
  tipo: z.enum(['entrada', 'saida', 'periodica']),
  data_vistoria: z.string().min(1, 'Data da vistoria é obrigatória'),
  responsavel_id: z.string().optional(),
  responsavel_nome: z.string().optional(),
  observacoes_gerais: z.string().optional(),
});

type VistoriaFormData = z.infer<typeof vistoriaSchema>;

export default function Vistorias() {
  const [filtroTipo, setFiltroTipo] = useState('todos');
  const [filtroStatus, setFiltroStatus] = useState('todos');
  const [busca, setBusca] = useState('');
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const { data: vistorias = [], isLoading } = useVistorias({
    tipo: filtroTipo !== 'todos' ? filtroTipo : undefined,
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
  });
  const createMutation = useCreateVistoria();
  const updateMutation = useUpdateVistoria();
  const deleteMutation = useDeleteVistoria();

  const [dialogAberto, setDialogAberto] = useState(false);
  const [formChecklist, setFormChecklist] = useState<ChecklistItem[]>([...DEFAULT_CHECKLIST]);

  const {
    register: registerVistoria,
    handleSubmit: rhfHandleCreate,
    formState: { errors: vistoriaErrors },
    reset: resetVistoria,
    setValue: setVistoriaValue,
    watch: watchVistoria,
  } = useForm<VistoriaFormData>({
    resolver: zodResolver(vistoriaSchema),
    defaultValues: {
      imovel_id: '',
      tipo: 'entrada',
      data_vistoria: '',
      responsavel_id: '',
      responsavel_nome: '',
      observacoes_gerais: '',
    },
  });

  const tipoVistoriaValue = watchVistoria('tipo');
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [detailVistoria, setDetailVistoria] = useState<Vistoria | null>(null);

  const filtrados = useMemo(() => {
    if (!busca) return vistorias;
    const q = busca.toLowerCase();
    return vistorias.filter((v) =>
      v.id.toLowerCase().includes(q) ||
      v.imovel_id.toLowerCase().includes(q) ||
      v.responsavel_nome?.toLowerCase().includes(q) ||
      v.observacoes_gerais?.toLowerCase().includes(q)
    );
  }, [vistorias, busca]);

  const summary = useMemo(() => {
    const agendadas = vistorias.filter((v) => v.status === 'agendada').length;
    const emAndamento = vistorias.filter((v) => v.status === 'em_andamento').length;
    const concluidas = vistorias.filter((v) => v.status === 'concluida').length;
    return { agendadas, emAndamento, concluidas, total: vistorias.length };
  }, [vistorias]);

  const handleCreate = (data: VistoriaFormData) => {
    createMutation.mutate(
      {
        ...data,
        responsavel_id: data.responsavel_id || user?.id || '',
        checklist: formChecklist,
      },
      {
        onSuccess: () => {
          setDialogAberto(false);
          resetVistoria();
          setFormChecklist([...DEFAULT_CHECKLIST]);
        },
      }
    );
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteMutation.mutate(deleteId);
      setDeleteId(null);
    }
  };

  const handleStatusChange = (vistoria: Vistoria, newStatus: StatusVistoria) => {
    updateMutation.mutate({ id: vistoria.id, status: newStatus });
  };

  const updateChecklistItem = (index: number, field: keyof ChecklistItem, value: string) => {
    const updated = [...formChecklist];
    updated[index] = { ...updated[index], [field]: value };
    setFormChecklist(updated);
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Vistorias</h1>
          <p className="text-muted-foreground">Agende e gerencie vistorias de imoveis</p>
        </div>
        <Button onClick={() => {
          resetVistoria({ imovel_id: '', tipo: 'entrada', data_vistoria: '', responsavel_id: user?.id || '', responsavel_nome: '', observacoes_gerais: '' });
          setFormChecklist([...DEFAULT_CHECKLIST]);
          setDialogAberto(true);
        }}>
          <Plus className="h-4 w-4 mr-2" />Nova Vistoria
        </Button>
      </div>

      {/* Summary */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Agendadas</CardTitle>
            <Calendar className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.agendadas}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Andamento</CardTitle>
            <Clock className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.emAndamento}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Concluidas</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.concluidas}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <ClipboardCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.total}</div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por ID, imovel, responsavel..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="pl-10"
              />
            </div>
            <Select value={filtroTipo} onValueChange={setFiltroTipo}>
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os tipos</SelectItem>
                <SelectItem value="entrada">Entrada</SelectItem>
                <SelectItem value="saida">Saida</SelectItem>
                <SelectItem value="periodica">Periodica</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os status</SelectItem>
                <SelectItem value="agendada">Agendada</SelectItem>
                <SelectItem value="em_andamento">Em Andamento</SelectItem>
                <SelectItem value="concluida">Concluida</SelectItem>
                <SelectItem value="cancelada">Cancelada</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Vistorias List */}
      {isLoading ? (
        <CardGridSkeleton count={6} />
      ) : filtrados.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <ClipboardCheck className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg">Nenhuma vistoria encontrada</p>
            <p className="text-sm mt-1">Agende uma vistoria para comecar</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtrados.map((vistoria) => {
            const tipoLabel = VISTORIA_TIPO_CONFIG[vistoria.tipo]?.label || vistoria.tipo;
            const tipoVariant = TIPO_VARIANT[vistoria.tipo] || 'default';
            const statusLabel = VISTORIA_STATUS_CONFIG[vistoria.status]?.label || vistoria.status;
            const statusIcon = STATUS_ICON[vistoria.status] || STATUS_ICON.agendada;
            const StatusIcon = statusIcon.icon;
            return (
              <Card key={vistoria.id} className="hover:shadow-md transition-shadow">
                <CardContent className="pt-6 space-y-3">
                  <div className="flex items-center justify-between">
                    <Badge variant={tipoVariant}>{tipoLabel}</Badge>
                    <div className={`flex items-center gap-1 text-sm ${statusIcon.color}`}>
                      <StatusIcon className="h-4 w-4" />
                      {statusLabel}
                    </div>
                  </div>

                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <Calendar className="h-3 w-3" />
                    {formatDate(vistoria.data_vistoria)}
                  </div>

                  {vistoria.responsavel_nome && (
                    <div className="text-sm text-muted-foreground">
                      Responsavel: {vistoria.responsavel_nome}
                    </div>
                  )}

                  {vistoria.fotos && vistoria.fotos.length > 0 && (
                    <div className="flex items-center gap-1 text-sm text-muted-foreground">
                      <Camera className="h-3 w-3" />
                      {vistoria.fotos.length} foto(s)
                    </div>
                  )}

                  {vistoria.checklist && vistoria.checklist.length > 0 && (
                    <div className="flex gap-2 text-xs">
                      {(() => {
                        const counts = { bom: 0, regular: 0, ruim: 0, NA: 0 };
                        vistoria.checklist.forEach((item) => {
                          if (item.estado in counts) counts[item.estado as keyof typeof counts]++;
                        });
                        return (
                          <>
                            {counts.bom > 0 && <span className="bg-green-100 text-green-800 px-1.5 py-0.5 rounded">{counts.bom} bom</span>}
                            {counts.regular > 0 && <span className="bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded">{counts.regular} regular</span>}
                            {counts.ruim > 0 && <span className="bg-red-100 text-red-800 px-1.5 py-0.5 rounded">{counts.ruim} ruim</span>}
                          </>
                        );
                      })()}
                    </div>
                  )}

                  {vistoria.observacoes_gerais && (
                    <p className="text-sm text-muted-foreground truncate">{vistoria.observacoes_gerais}</p>
                  )}

                  <div className="flex gap-2 pt-2">
                    <Button size="sm" variant="outline" onClick={() => navigate(`/vistorias/${vistoria.id}`)}>
                      <Eye className="h-3 w-3 mr-1" />Detalhes
                    </Button>
                    {vistoria.status === 'agendada' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleStatusChange(vistoria, 'em_andamento')}
                      >
                        Iniciar
                      </Button>
                    )}
                    {vistoria.status === 'em_andamento' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleStatusChange(vistoria, 'concluida')}
                      >
                        Concluir
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => setDeleteId(vistoria.id)}>
                      <Trash2 className="h-3 w-3 text-muted-foreground" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create Vistoria Dialog */}
      <Dialog open={dialogAberto} onOpenChange={setDialogAberto}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Nova Vistoria</DialogTitle>
          </DialogHeader>
          <form onSubmit={rhfHandleCreate(handleCreate)} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label>ID do Imóvel</Label>
                <Input {...registerVistoria('imovel_id')} placeholder="UUID do imóvel" />
                {vistoriaErrors.imovel_id && <p className="text-sm text-destructive">{vistoriaErrors.imovel_id.message}</p>}
              </div>
              <div>
                <Label>Tipo</Label>
                <Select value={tipoVistoriaValue} onValueChange={(v) => setVistoriaValue('tipo', v as TipoVistoria)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="entrada">Entrada</SelectItem>
                    <SelectItem value="saida">Saída</SelectItem>
                    <SelectItem value="periodica">Periódica</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label>Data da Vistoria</Label>
                <Input type="date" {...registerVistoria('data_vistoria')} />
                {vistoriaErrors.data_vistoria && <p className="text-sm text-destructive">{vistoriaErrors.data_vistoria.message}</p>}
              </div>
              <div>
                <Label>Nome do Responsável</Label>
                <Input {...registerVistoria('responsavel_nome')} placeholder="Nome do responsável" />
              </div>
            </div>
            <div>
              <Label>Observações Gerais</Label>
              <Textarea {...registerVistoria('observacoes_gerais')} rows={2} />
            </div>

            {/* Checklist Editor */}
            <div>
              <Label className="text-base font-semibold">Checklist</Label>
              <div className="mt-2 space-y-2 max-h-60 overflow-y-auto">
                {formChecklist.map((item, index) => (
                  <div key={index} className="flex items-center gap-2 p-2 border rounded">
                    <span className="text-sm font-medium flex-1 min-w-0 truncate">{item.item}</span>
                    <Select
                      value={item.estado}
                      onValueChange={(v) => updateChecklistItem(index, 'estado', v)}
                    >
                      <SelectTrigger className="w-[110px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ESTADO_OPTIONS.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      className="w-40"
                      placeholder="Obs."
                      value={item.observacao}
                      onChange={(e) => updateChecklistItem(index, 'observacao', e.target.value)}
                    />
                  </div>
                ))}
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialogAberto(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Criando...' : 'Criar Vistoria'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={!!detailVistoria} onOpenChange={() => setDetailVistoria(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detalhes da Vistoria</DialogTitle>
          </DialogHeader>
          {detailVistoria && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                <div>
                  <strong>Tipo:</strong> {VISTORIA_TIPO_CONFIG[detailVistoria.tipo]?.label || detailVistoria.tipo}
                </div>
                <div>
                  <strong>Status:</strong> {VISTORIA_STATUS_CONFIG[detailVistoria.status]?.label || detailVistoria.status}
                </div>
                <div>
                  <strong>Data:</strong> {formatDate(detailVistoria.data_vistoria)}
                </div>
                <div>
                  <strong>Responsavel:</strong> {detailVistoria.responsavel_nome || '-'}
                </div>
              </div>

              {detailVistoria.observacoes_gerais && (
                <div>
                  <strong className="text-sm">Observacoes:</strong>
                  <p className="text-sm text-muted-foreground mt-1">{detailVistoria.observacoes_gerais}</p>
                </div>
              )}

              {detailVistoria.checklist && detailVistoria.checklist.length > 0 && (
                <div>
                  <strong className="text-sm">Checklist ({detailVistoria.checklist.length} itens)</strong>
                  <div className="mt-2 space-y-1 max-h-60 overflow-y-auto">
                    {detailVistoria.checklist.map((item, i) => {
                      const estadoOpt = ESTADO_OPTIONS.find((o) => o.value === item.estado);
                      return (
                        <div key={i} className="flex items-center gap-2 text-sm p-1.5 border rounded">
                          <span className="flex-1">{item.item}</span>
                          <span className={`px-2 py-0.5 rounded text-xs ${estadoOpt?.color || ''}`}>
                            {estadoOpt?.label || item.estado}
                          </span>
                          {item.observacao && (
                            <span className="text-muted-foreground text-xs max-w-[150px] truncate">
                              {item.observacao}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {detailVistoria.fotos && detailVistoria.fotos.length > 0 && (
                <div>
                  <strong className="text-sm">Fotos ({detailVistoria.fotos.length})</strong>
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    {detailVistoria.fotos.map((url, i) => (
                      <a key={i} href={url} target="_blank" rel="noopener noreferrer">
                        <img
                          src={url}
                          alt={`Foto ${i + 1}`}
                          className="w-full h-24 object-cover rounded border hover:opacity-80 transition-opacity"
                        />
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetailVistoria(null)}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Vistoria</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir esta vistoria? Esta acao nao pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive hover:bg-destructive/90">
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
