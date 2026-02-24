import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Wrench,
  Clock,
  AlertTriangle,
  DollarSign,
  Plus,
  Pencil,
  Trash2,
} from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import {
  useManutencao,
  useResumoManutencao,
  useCreateOrdemServico,
  useUpdateOrdemServico,
  useDeleteOrdemServico,
} from '@/hooks/useManutencao';
import {
  TipoOrdem,
  PrioridadeOrdem,
  StatusOrdem,
  OrdemServicoCreateData,
  OrdemServicoUpdateData,
  OrdemServico,
} from '@/types/manutencao';

const STATUS_CONFIG: Record<StatusOrdem, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  aberto: { label: 'Aberto', variant: 'destructive' },
  em_andamento: { label: 'Em Andamento', variant: 'outline' },
  aguardando: { label: 'Aguardando', variant: 'secondary' },
  concluido: { label: 'Concluido', variant: 'default' },
  cancelado: { label: 'Cancelado', variant: 'secondary' },
};

const PRIORIDADE_CONFIG: Record<PrioridadeOrdem, { label: string; className: string }> = {
  baixa: { label: 'Baixa', className: 'bg-blue-100 text-blue-800' },
  media: { label: 'Media', className: 'bg-yellow-100 text-yellow-800' },
  alta: { label: 'Alta', className: 'bg-orange-100 text-orange-800' },
  urgente: { label: 'Urgente', className: 'bg-red-100 text-red-800' },
};

const TIPO_CONFIG: Record<TipoOrdem, string> = {
  preventiva: 'Preventiva',
  corretiva: 'Corretiva',
  emergencial: 'Emergencial',
  reforma: 'Reforma',
};

const emptyForm: OrdemServicoCreateData = {
  titulo: '',
  descricao: '',
  tipo: 'corretiva',
  prioridade: 'media',
  imovel_id: undefined,
  cliente_id: undefined,
  responsavel: undefined,
  fornecedor: undefined,
  custo_estimado: undefined,
  data_abertura: '',
  data_previsao: undefined,
  fotos: [],
  observacoes: undefined,
};

export default function Manutencao() {
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [filtroPrioridade, setFiltroPrioridade] = useState<string>('todos');
  const [filtroTipo, setFiltroTipo] = useState<string>('todos');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingOrdem, setEditingOrdem] = useState<OrdemServico | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [formData, setFormData] = useState<OrdemServicoCreateData>(emptyForm);

  const { data: manutencaoData, isLoading } = useManutencao({
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
    prioridade: filtroPrioridade !== 'todos' ? filtroPrioridade : undefined,
    tipo: filtroTipo !== 'todos' ? filtroTipo : undefined,
  });
  const ordens = manutencaoData?.data || [];

  const { data: resumo } = useResumoManutencao();

  const { mutate: createOrdem, isPending: isCreating } = useCreateOrdemServico();
  const { mutate: updateOrdem, isPending: isUpdating } = useUpdateOrdemServico();
  const { mutate: deleteOrdem } = useDeleteOrdemServico();

  const handleOpenCreate = () => {
    setEditingOrdem(null);
    setFormData(emptyForm);
    setModalOpen(true);
  };

  const handleOpenEdit = (ordem: OrdemServico) => {
    setEditingOrdem(ordem);
    setFormData({
      titulo: ordem.titulo,
      descricao: ordem.descricao,
      tipo: ordem.tipo,
      prioridade: ordem.prioridade,
      imovel_id: ordem.imovel_id || undefined,
      cliente_id: ordem.cliente_id || undefined,
      responsavel: ordem.responsavel || undefined,
      fornecedor: ordem.fornecedor || undefined,
      custo_estimado: ordem.custo_estimado || undefined,
      data_abertura: ordem.data_abertura,
      data_previsao: ordem.data_previsao || undefined,
      fotos: ordem.fotos || [],
      observacoes: ordem.observacoes || undefined,
    });
    setModalOpen(true);
  };

  const handleSubmit = () => {
    if (!formData.titulo || !formData.descricao || !formData.data_abertura) {
      return;
    }

    if (editingOrdem) {
      const updateData: OrdemServicoUpdateData = {
        id: editingOrdem.id,
        ...formData,
      };
      updateOrdem(updateData, {
        onSuccess: () => setModalOpen(false),
      });
    } else {
      createOrdem(formData, {
        onSuccess: () => setModalOpen(false),
      });
    }
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteOrdem(deleteId);
      setDeleteId(null);
    }
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Manutencao</h1>
          <p className="text-muted-foreground">Gestao de ordens de servico e manutencao</p>
        </div>
        <Button onClick={handleOpenCreate}>
          <Plus className="w-4 h-4 mr-2" />
          Nova Ordem de Servico
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Abertas</CardTitle>
            <Wrench className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">
              {resumo?.por_status?.aberto || 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Andamento</CardTitle>
            <Clock className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-600">
              {resumo?.por_status?.em_andamento || 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tempo Medio</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">
              {resumo?.tempo_medio_resolucao || 0} dias
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Custo Total</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(resumo?.custo_total || 0)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap gap-4">
            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Status</SelectItem>
                <SelectItem value="aberto">Aberto</SelectItem>
                <SelectItem value="em_andamento">Em Andamento</SelectItem>
                <SelectItem value="aguardando">Aguardando</SelectItem>
                <SelectItem value="concluido">Concluido</SelectItem>
                <SelectItem value="cancelado">Cancelado</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filtroPrioridade} onValueChange={setFiltroPrioridade}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Prioridade" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todas as Prioridades</SelectItem>
                <SelectItem value="baixa">Baixa</SelectItem>
                <SelectItem value="media">Media</SelectItem>
                <SelectItem value="alta">Alta</SelectItem>
                <SelectItem value="urgente">Urgente</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filtroTipo} onValueChange={setFiltroTipo}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Tipos</SelectItem>
                <SelectItem value="preventiva">Preventiva</SelectItem>
                <SelectItem value="corretiva">Corretiva</SelectItem>
                <SelectItem value="emergencial">Emergencial</SelectItem>
                <SelectItem value="reforma">Reforma</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Orders Table */}
      <Card>
        <CardContent className="pt-6">
          {isLoading ? (
            <div className="py-8 text-center text-muted-foreground">
              Carregando ordens de servico...
            </div>
          ) : ordens.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              Nenhuma ordem de servico encontrada
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Titulo</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Prioridade</TableHead>
                    <TableHead>Responsavel</TableHead>
                    <TableHead>Previsao</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ordens.map((ordem) => (
                    <TableRow key={ordem.id}>
                      <TableCell className="max-w-[200px] truncate font-medium">
                        {ordem.titulo}
                      </TableCell>
                      <TableCell>{TIPO_CONFIG[ordem.tipo]}</TableCell>
                      <TableCell>
                        <Badge className={PRIORIDADE_CONFIG[ordem.prioridade].className}>
                          {PRIORIDADE_CONFIG[ordem.prioridade].label}
                        </Badge>
                      </TableCell>
                      <TableCell>{ordem.responsavel || '-'}</TableCell>
                      <TableCell>
                        {ordem.data_previsao ? formatDate(ordem.data_previsao) : '-'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATUS_CONFIG[ordem.status].variant}>
                          {STATUS_CONFIG[ordem.status].label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenEdit(ordem)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteId(ordem.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create/Edit Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingOrdem ? 'Editar Ordem de Servico' : 'Nova Ordem de Servico'}
            </DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Titulo</Label>
              <Input
                value={formData.titulo}
                onChange={(e) => setFormData({ ...formData, titulo: e.target.value })}
                placeholder="Titulo da ordem de servico"
              />
            </div>

            <div className="space-y-2">
              <Label>Descricao</Label>
              <Textarea
                value={formData.descricao}
                onChange={(e) => setFormData({ ...formData, descricao: e.target.value })}
                placeholder="Descricao detalhada do servico"
                rows={3}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tipo</Label>
                <Select
                  value={formData.tipo}
                  onValueChange={(v) => setFormData({ ...formData, tipo: v as TipoOrdem })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="preventiva">Preventiva</SelectItem>
                    <SelectItem value="corretiva">Corretiva</SelectItem>
                    <SelectItem value="emergencial">Emergencial</SelectItem>
                    <SelectItem value="reforma">Reforma</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Prioridade</Label>
                <Select
                  value={formData.prioridade || 'media'}
                  onValueChange={(v) => setFormData({ ...formData, prioridade: v as PrioridadeOrdem })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="baixa">Baixa</SelectItem>
                    <SelectItem value="media">Media</SelectItem>
                    <SelectItem value="alta">Alta</SelectItem>
                    <SelectItem value="urgente">Urgente</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Imovel ID</Label>
                <Input
                  value={formData.imovel_id || ''}
                  onChange={(e) => setFormData({ ...formData, imovel_id: e.target.value || undefined })}
                  placeholder="ID do imovel"
                />
              </div>

              <div className="space-y-2">
                <Label>Cliente ID</Label>
                <Input
                  value={formData.cliente_id || ''}
                  onChange={(e) => setFormData({ ...formData, cliente_id: e.target.value || undefined })}
                  placeholder="ID do cliente"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Responsavel</Label>
                <Input
                  value={formData.responsavel || ''}
                  onChange={(e) => setFormData({ ...formData, responsavel: e.target.value || undefined })}
                  placeholder="Nome do responsavel"
                />
              </div>

              <div className="space-y-2">
                <Label>Fornecedor</Label>
                <Input
                  value={formData.fornecedor || ''}
                  onChange={(e) => setFormData({ ...formData, fornecedor: e.target.value || undefined })}
                  placeholder="Nome do fornecedor"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Custo Estimado (R$)</Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={formData.custo_estimado || ''}
                onChange={(e) => setFormData({ ...formData, custo_estimado: parseFloat(e.target.value) || undefined })}
                placeholder="0,00"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Data de Abertura</Label>
                <Input
                  type="date"
                  value={formData.data_abertura}
                  onChange={(e) => setFormData({ ...formData, data_abertura: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label>Data de Previsao</Label>
                <Input
                  type="date"
                  value={formData.data_previsao || ''}
                  onChange={(e) => setFormData({ ...formData, data_previsao: e.target.value || undefined })}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Observacoes</Label>
              <Textarea
                value={formData.observacoes || ''}
                onChange={(e) => setFormData({ ...formData, observacoes: e.target.value || undefined })}
                placeholder="Observacoes adicionais..."
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={isCreating || isUpdating || !formData.titulo || !formData.descricao || !formData.data_abertura}
            >
              {editingOrdem ? 'Salvar' : 'Criar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Ordem de Servico</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir esta ordem de servico? Esta acao e irreversivel.
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
