import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  useLocacoes,
  useCreateLocacao,
  useUpdateLocacao,
  useDeleteLocacao,
  useReajusteLocacao,
  useRenovarLocacao,
} from '@/hooks/useLocacoes';
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
  FileText,
  TrendingUp,
  RefreshCw,
  Trash2,
  AlertTriangle,
  DollarSign,
  Calendar,
  Home,
} from 'lucide-react';
import { EmptyState } from '@/components/ui/empty-state';
import { CardGridSkeleton } from '@/components/ui/page-skeleton';
import { formatCurrency, formatDate } from '@/lib/utils';
import type {
  ContratoLocacao,
  ContratoCreateData,
  StatusLocacao,
  IndiceReajuste,
  ReajusteResult,
} from '@/types/locacoes';

const STATUS_CONFIG: Record<StatusLocacao, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  ativo: { label: 'Ativo', variant: 'default' },
  encerrado: { label: 'Encerrado', variant: 'secondary' },
  renovado: { label: 'Renovado', variant: 'outline' },
  inadimplente: { label: 'Inadimplente', variant: 'destructive' },
};

const EMPTY_FORM: ContratoCreateData = {
  imovel_id: '',
  locatario_id: '',
  proprietario_id: '',
  valor_aluguel: 0,
  dia_vencimento: 10,
  data_inicio: '',
  data_fim: '',
  indice_reajuste: 'IGPM',
  taxa_administracao: 10,
  valor_caucao: 0,
  observacoes: '',
};

export default function Locacoes() {
  const navigate = useNavigate();
  const [filtroStatus, setFiltroStatus] = useState('todos');
  const [busca, setBusca] = useState('');
  const contratosQuery = useLocacoes(filtroStatus !== 'todos' ? filtroStatus : undefined);
  const { data: contratos = [] } = contratosQuery;
  const showLocacoesSkeleton = contratosQuery.isPending && !contratosQuery.data;
  const createMutation = useCreateLocacao();
  const updateMutation = useUpdateLocacao();
  const deleteMutation = useDeleteLocacao();
  const reajusteMutation = useReajusteLocacao();
  const renovarMutation = useRenovarLocacao();

  const [dialogAberto, setDialogAberto] = useState(false);
  const [formData, setFormData] = useState<ContratoCreateData>({ ...EMPTY_FORM });
  const [deleteId, setDeleteId] = useState<string | null>(null);

  // Reajuste modal
  const [reajusteContrato, setReajusteContrato] = useState<ContratoLocacao | null>(null);
  const [reajustePercentual, setReajustePercentual] = useState<string>('');
  const [reajustePreview, setReajustePreview] = useState<ReajusteResult | null>(null);

  // Renovar modal
  const [renovarContrato, setRenovarContrato] = useState<ContratoLocacao | null>(null);
  const [renovarDataFim, setRenovarDataFim] = useState('');
  const [renovarValor, setRenovarValor] = useState('');

  // Summary cards
  const summary = useMemo(() => {
    const ativos = contratos.filter((c) => c.status === 'ativo');
    const inadimplentes = contratos.filter((c) => c.status === 'inadimplente');
    const valorTotal = ativos.reduce((acc, c) => acc + (c.valor_aluguel || 0), 0);
    return {
      totalAtivos: ativos.length,
      valorMensal: valorTotal,
      inadimplentes: inadimplentes.length,
      totalContratos: contratos.length,
    };
  }, [contratos]);

  const filtrados = useMemo(() => {
    if (!busca) return contratos;
    const q = busca.toLowerCase();
    return contratos.filter((c) =>
      c.id.toLowerCase().includes(q) ||
      c.imovel_id.toLowerCase().includes(q) ||
      c.locatario_id.toLowerCase().includes(q) ||
      c.observacoes?.toLowerCase().includes(q)
    );
  }, [contratos, busca]);

  const handleCreate = () => {
    createMutation.mutate(formData, {
      onSuccess: () => {
        setDialogAberto(false);
        setFormData({ ...EMPTY_FORM });
      },
    });
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteMutation.mutate(deleteId);
      setDeleteId(null);
    }
  };

  const handleReajustePreview = () => {
    if (!reajusteContrato) return;
    reajusteMutation.mutate(
      {
        id: reajusteContrato.id,
        percentual: reajustePercentual ? parseFloat(reajustePercentual) : undefined,
        aplicar: false,
      },
      { onSuccess: (data) => setReajustePreview(data) }
    );
  };

  const handleReajusteAplicar = () => {
    if (!reajusteContrato) return;
    reajusteMutation.mutate(
      {
        id: reajusteContrato.id,
        percentual: reajustePercentual ? parseFloat(reajustePercentual) : undefined,
        aplicar: true,
      },
      {
        onSuccess: () => {
          setReajusteContrato(null);
          setReajustePreview(null);
          setReajustePercentual('');
        },
      }
    );
  };

  const handleRenovar = () => {
    if (!renovarContrato || !renovarDataFim) return;
    renovarMutation.mutate(
      {
        id: renovarContrato.id,
        nova_data_fim: renovarDataFim,
        novo_valor: renovarValor ? parseFloat(renovarValor) : undefined,
      },
      {
        onSuccess: () => {
          setRenovarContrato(null);
          setRenovarDataFim('');
          setRenovarValor('');
        },
      }
    );
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Contratos de Locacao</h1>
          <p className="text-muted-foreground">Gerencie contratos de aluguel, reajustes e renovacoes</p>
        </div>
        <Button onClick={() => setDialogAberto(true)}>
          <Plus className="h-4 w-4 mr-2" />Novo Contrato
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Contratos Ativos</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.totalAtivos}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Valor Mensal Total</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(summary.valorMensal)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Inadimplentes</CardTitle>
            <AlertTriangle className="h-4 w-4 text-destructive" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-destructive">{summary.inadimplentes}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total de Contratos</CardTitle>
            <Home className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.totalContratos}</div>
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
                placeholder="Buscar por ID, imovel, locatario..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="pl-10"
              />
            </div>
            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os status</SelectItem>
                <SelectItem value="ativo">Ativo</SelectItem>
                <SelectItem value="encerrado">Encerrado</SelectItem>
                <SelectItem value="renovado">Renovado</SelectItem>
                <SelectItem value="inadimplente">Inadimplente</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Contracts List */}
      {showLocacoesSkeleton ? (
        <CardGridSkeleton count={4} />
      ) : filtrados.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="Nenhum contrato encontrado"
          description="Crie um contrato de locação para começar"
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filtrados.map((contrato) => {
            const cfg = STATUS_CONFIG[contrato.status] || STATUS_CONFIG.ativo;
            return (
              <Card key={contrato.id} className="hover:shadow-md transition-shadow cursor-pointer" onClick={() => navigate(`/locacoes/${contrato.id}`)}>
                <CardContent className="pt-6 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="h-5 w-5 text-primary" />
                      <span className="font-semibold text-sm font-mono">
                        {contrato.id.slice(0, 8)}...
                      </span>
                    </div>
                    <Badge variant={cfg.variant}>{cfg.label}</Badge>
                  </div>

                  <div className="text-2xl font-bold text-primary">
                    {formatCurrency(contrato.valor_aluguel)}/mes
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-sm text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      {formatDate(contrato.data_inicio)} - {formatDate(contrato.data_fim)}
                    </div>
                    <div>Vencimento: dia {contrato.dia_vencimento}</div>
                    <div>Indice: {contrato.indice_reajuste}</div>
                    <div>Adm: {contrato.taxa_administracao}%</div>
                  </div>

                  {contrato.valor_caucao && contrato.valor_caucao > 0 && (
                    <div className="text-sm text-muted-foreground">
                      Caucao: {formatCurrency(contrato.valor_caucao)}
                    </div>
                  )}

                  {contrato.observacoes && (
                    <p className="text-sm text-muted-foreground truncate">{contrato.observacoes}</p>
                  )}

                  <div className="flex gap-2 pt-2" onClick={(e) => e.stopPropagation()}>
                    {contrato.status === 'ativo' && (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setReajusteContrato(contrato);
                            setReajustePreview(null);
                            setReajustePercentual('');
                          }}
                        >
                          <TrendingUp className="h-3 w-3 mr-1" />Reajuste
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setRenovarContrato(contrato);
                            setRenovarDataFim('');
                            setRenovarValor('');
                          }}
                        >
                          <RefreshCw className="h-3 w-3 mr-1" />Renovar
                        </Button>
                      </>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleteId(contrato.id)}
                    >
                      <Trash2 className="h-3 w-3 text-muted-foreground" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create Contract Dialog */}
      <Dialog open={dialogAberto} onOpenChange={setDialogAberto}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Novo Contrato de Locacao</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label>ID do Imovel</Label>
                <Input
                  value={formData.imovel_id}
                  onChange={(e) => setFormData({ ...formData, imovel_id: e.target.value })}
                  placeholder="UUID do imovel"
                />
              </div>
              <div>
                <Label>ID do Locatario</Label>
                <Input
                  value={formData.locatario_id}
                  onChange={(e) => setFormData({ ...formData, locatario_id: e.target.value })}
                  placeholder="UUID do locatario"
                />
              </div>
            </div>
            <div>
              <Label>ID do Proprietario (opcional)</Label>
              <Input
                value={formData.proprietario_id || ''}
                onChange={(e) => setFormData({ ...formData, proprietario_id: e.target.value })}
                placeholder="UUID do proprietario"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label>Valor do Aluguel (R$)</Label>
                <Input
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.valor_aluguel || ''}
                  onChange={(e) => setFormData({ ...formData, valor_aluguel: parseFloat(e.target.value) || 0 })}
                />
              </div>
              <div>
                <Label>Dia de Vencimento</Label>
                <Input
                  type="number"
                  min={1}
                  max={31}
                  value={formData.dia_vencimento || 10}
                  onChange={(e) => setFormData({ ...formData, dia_vencimento: parseInt(e.target.value) || 10 })}
                />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label>Data de Inicio</Label>
                <Input
                  type="date"
                  value={formData.data_inicio}
                  onChange={(e) => setFormData({ ...formData, data_inicio: e.target.value })}
                />
              </div>
              <div>
                <Label>Data de Termino</Label>
                <Input
                  type="date"
                  value={formData.data_fim}
                  onChange={(e) => setFormData({ ...formData, data_fim: e.target.value })}
                />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label>Indice de Reajuste</Label>
                <Select
                  value={formData.indice_reajuste || 'IGPM'}
                  onValueChange={(v) => setFormData({ ...formData, indice_reajuste: v as IndiceReajuste })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="IGPM">IGPM</SelectItem>
                    <SelectItem value="IPCA">IPCA</SelectItem>
                    <SelectItem value="INPC">INPC</SelectItem>
                    <SelectItem value="fixo">Fixo</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Taxa de Administracao (%)</Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step={0.1}
                  value={formData.taxa_administracao || 10}
                  onChange={(e) => setFormData({ ...formData, taxa_administracao: parseFloat(e.target.value) || 10 })}
                />
              </div>
            </div>
            <div>
              <Label>Valor da Caucao (R$)</Label>
              <Input
                type="number"
                min={0}
                step={0.01}
                value={formData.valor_caucao || ''}
                onChange={(e) => setFormData({ ...formData, valor_caucao: parseFloat(e.target.value) || 0 })}
              />
            </div>
            <div>
              <Label>Observacoes</Label>
              <Textarea
                value={formData.observacoes || ''}
                onChange={(e) => setFormData({ ...formData, observacoes: e.target.value })}
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogAberto(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleCreate}
              disabled={createMutation.isPending || !formData.imovel_id || !formData.locatario_id || !formData.valor_aluguel}
            >
              {createMutation.isPending ? 'Criando...' : 'Criar Contrato'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reajuste Dialog */}
      <Dialog open={!!reajusteContrato} onOpenChange={() => setReajusteContrato(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reajuste de Aluguel</DialogTitle>
          </DialogHeader>
          {reajusteContrato && (
            <div className="space-y-4">
              <div className="text-sm text-muted-foreground">
                Valor atual: <strong>{formatCurrency(reajusteContrato.valor_aluguel)}</strong>
                <br />
                Indice: <strong>{reajusteContrato.indice_reajuste}</strong>
              </div>
              <div>
                <Label>Percentual de reajuste (%) — deixe vazio para usar o indice padrao</Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step={0.01}
                  value={reajustePercentual}
                  onChange={(e) => {
                    setReajustePercentual(e.target.value);
                    setReajustePreview(null);
                  }}
                  placeholder="Ex: 5.25"
                />
              </div>
              <Button variant="outline" onClick={handleReajustePreview} disabled={reajusteMutation.isPending}>
                Calcular Preview
              </Button>
              {reajustePreview && (
                <Card>
                  <CardContent className="pt-4 space-y-1 text-sm">
                    <div>Valor anterior: {formatCurrency(reajustePreview.valor_anterior)}</div>
                    <div className="font-bold text-primary">
                      Valor novo: {formatCurrency(reajustePreview.valor_novo)}
                    </div>
                    <div>Diferenca: {formatCurrency(reajustePreview.diferenca)}</div>
                    <div>Percentual aplicado: {reajustePreview.percentual_aplicado}%</div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setReajusteContrato(null)}>
              Cancelar
            </Button>
            <Button onClick={handleReajusteAplicar} disabled={reajusteMutation.isPending}>
              {reajusteMutation.isPending ? 'Aplicando...' : 'Aplicar Reajuste'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Renovar Dialog */}
      <Dialog open={!!renovarContrato} onOpenChange={() => setRenovarContrato(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Renovar Contrato</DialogTitle>
          </DialogHeader>
          {renovarContrato && (
            <div className="space-y-4">
              <div className="text-sm text-muted-foreground">
                Contrato atual: {formatDate(renovarContrato.data_inicio)} a {formatDate(renovarContrato.data_fim)}
                <br />
                Valor: {formatCurrency(renovarContrato.valor_aluguel)}
              </div>
              <div>
                <Label>Nova data de termino</Label>
                <Input
                  type="date"
                  value={renovarDataFim}
                  onChange={(e) => setRenovarDataFim(e.target.value)}
                />
              </div>
              <div>
                <Label>Novo valor (R$) — deixe vazio para manter</Label>
                <Input
                  type="number"
                  min={0}
                  step={0.01}
                  value={renovarValor}
                  onChange={(e) => setRenovarValor(e.target.value)}
                  placeholder={String(renovarContrato.valor_aluguel)}
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenovarContrato(null)}>
              Cancelar
            </Button>
            <Button onClick={handleRenovar} disabled={renovarMutation.isPending || !renovarDataFim}>
              {renovarMutation.isPending ? 'Renovando...' : 'Renovar Contrato'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Contrato</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este contrato de locacao? Esta acao nao pode ser desfeita.
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
