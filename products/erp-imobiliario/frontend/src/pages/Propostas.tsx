import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
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
  Send,
  Search,
  HandshakeIcon,
  CheckCircle2,
  XCircle,
  Clock,
  Plus,
  Trash2,
  ArrowRightLeft,
  History,
  FileText,
} from 'lucide-react';
import { EmptyState } from '@/components/ui/empty-state';
import { CardListSkeleton } from '@/components/ui/page-skeleton';
import { formatCurrency, formatDate } from '@/lib/utils';
import {
  usePropostas,
  usePropostaStats,
  useCreateProposta,
  useUpdateProposta,
  useContraproposta,
  useDeleteProposta,
} from '@/hooks/usePropostas';
import {
  StatusProposta,
  Proposta,
  HistoricoProposta,
} from '@/types/propostas';

const STATUS_CONFIG: Record<StatusProposta, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: typeof Send }> = {
  enviada: { label: 'Enviada', variant: 'outline', icon: Send },
  em_analise: { label: 'Em Análise', variant: 'secondary', icon: Search },
  contraproposta: { label: 'Contraproposta', variant: 'default', icon: ArrowRightLeft },
  aceita: { label: 'Aceita', variant: 'default', icon: CheckCircle2 },
  recusada: { label: 'Recusada', variant: 'destructive', icon: XCircle },
  expirada: { label: 'Expirada', variant: 'secondary', icon: Clock },
};

const propostaSchema = z.object({
  imovel_id: z.string().min(1, 'ID do imóvel é obrigatório'),
  cliente_id: z.string().min(1, 'ID do cliente é obrigatório'),
  valor_proposta: z.coerce.number().positive('Valor deve ser maior que zero'),
  prazo_validade: z.string().optional(),
  condicoes_pagamento: z.string().optional(),
  observacoes: z.string().optional(),
});

type PropostaFormData = z.infer<typeof propostaSchema>;

export default function Propostas() {
  const navigate = useNavigate();
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [contrapropostaModal, setContrapropostaModal] = useState<Proposta | null>(null);
  const [historyModal, setHistoryModal] = useState<Proposta | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [contraValor, setContraValor] = useState<number>(0);

  const {
    register: registerProposta,
    handleSubmit: rhfHandleCreate,
    formState: { errors: propostaErrors },
    reset: resetProposta,
  } = useForm<PropostaFormData>({
    resolver: zodResolver(propostaSchema),
    defaultValues: {
      imovel_id: '',
      cliente_id: '',
      valor_proposta: 0,
      prazo_validade: '',
      condicoes_pagamento: '',
      observacoes: '',
    },
  });
  const [contraCondicoes, setContraCondicoes] = useState<string>('');
  const [contraObs, setContraObs] = useState<string>('');

  const { data: propostasData, isLoading } = usePropostas({
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
  });
  const propostas = propostasData?.data || [];

  const { data: stats } = usePropostaStats();

  const { mutate: createProposta, isPending: isCreating } = useCreateProposta();
  const { mutate: updateProposta } = useUpdateProposta();
  const { mutate: sendContraproposta, isPending: isSendingContra } = useContraproposta();
  const { mutate: deleteProposta } = useDeleteProposta();

  const handleCreate = (data: PropostaFormData) => {
    createProposta(
      {
        ...data,
        prazo_validade: data.prazo_validade || undefined,
        condicoes_pagamento: data.condicoes_pagamento || undefined,
        observacoes: data.observacoes || undefined,
      },
      {
        onSuccess: () => {
          setCreateModalOpen(false);
          resetProposta();
        },
      }
    );
  };

  const handleStatusChange = (proposta: Proposta, newStatus: StatusProposta) => {
    updateProposta({ id: proposta.id, status: newStatus });
  };

  const handleContraproposta = () => {
    if (!contrapropostaModal || !contraValor) return;
    sendContraproposta(
      {
        proposta_id: contrapropostaModal.id,
        valor_contraproposta: contraValor,
        condicoes_pagamento: contraCondicoes || undefined,
        observacoes: contraObs || undefined,
      },
      {
        onSuccess: () => {
          setContrapropostaModal(null);
          setContraValor(0);
          setContraCondicoes('');
          setContraObs('');
        },
      }
    );
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteProposta(deleteId);
      setDeleteId(null);
    }
  };

  const canContraproposta = (status: StatusProposta) => {
    return status === 'enviada' || status === 'em_analise';
  };

  const canChangeStatus = (status: StatusProposta) => {
    return !['aceita', 'recusada', 'expirada'].includes(status);
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Propostas</h1>
          <p className="text-muted-foreground">Gerenciamento de propostas e negociacoes</p>
        </div>
        <Button onClick={() => setCreateModalOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Nova Proposta
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Enviadas</CardTitle>
            <Send className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.enviada || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Analise</CardTitle>
            <Search className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.em_analise || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Contrapropostas</CardTitle>
            <ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.contraproposta || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Aceitas</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{stats?.aceita || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Recusadas</CardTitle>
            <XCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">{stats?.recusada || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <HandshakeIcon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total || 0}</div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Status</SelectItem>
                <SelectItem value="enviada">Enviada</SelectItem>
                <SelectItem value="em_analise">Em Analise</SelectItem>
                <SelectItem value="contraproposta">Contraproposta</SelectItem>
                <SelectItem value="aceita">Aceita</SelectItem>
                <SelectItem value="recusada">Recusada</SelectItem>
                <SelectItem value="expirada">Expirada</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Proposals List */}
      <div className="space-y-4">
        {isLoading ? (
          <CardListSkeleton count={3} />
        ) : propostas.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="Nenhuma proposta encontrada"
            description="Crie uma proposta para iniciar uma negociação"
            action={{ label: 'Nova Proposta', onClick: () => setCreateModalOpen(true) }}
          />
        ) : (
          propostas.map((proposta) => {
            const statusConfig = STATUS_CONFIG[proposta.status];
            const StatusIcon = statusConfig.icon;

            return (
              <Card key={proposta.id} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => navigate(`/propostas/${proposta.id}`)}>
                <CardContent className="pt-6">
                  <div className="flex flex-col lg:flex-row items-start justify-between gap-4">
                    <div className="flex-1 min-w-0 space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusIcon className="h-5 w-5 text-primary" />
                        <span className="font-semibold text-sm truncate">
                          {proposta.id.slice(0, 8)}...
                        </span>
                        <Badge variant={statusConfig.variant}>
                          {statusConfig.label}
                        </Badge>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                          <p className="text-muted-foreground">Valor Proposta</p>
                          <p className="font-medium">{formatCurrency(proposta.valor_proposta)}</p>
                        </div>
                        {proposta.valor_contraproposta && (
                          <div>
                            <p className="text-muted-foreground">Contraproposta</p>
                            <p className="font-medium text-orange-600">
                              {formatCurrency(proposta.valor_contraproposta)}
                            </p>
                          </div>
                        )}
                        <div>
                          <p className="text-muted-foreground">Imovel</p>
                          <p className="font-medium truncate">{proposta.imovel_id.slice(0, 8)}...</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Criado em</p>
                          <p className="font-medium">{formatDate(proposta.created_at)}</p>
                        </div>
                      </div>

                      {proposta.prazo_validade && (
                        <p className="text-sm text-muted-foreground">
                          Validade: {formatDate(proposta.prazo_validade)}
                        </p>
                      )}

                      {proposta.condicoes_pagamento && (
                        <div className="text-sm">
                          <p className="text-muted-foreground">Condicoes:</p>
                          <p className="mt-1">{proposta.condicoes_pagamento}</p>
                        </div>
                      )}

                      {proposta.observacoes && (
                        <div className="text-sm">
                          <p className="text-muted-foreground">Observacoes:</p>
                          <p className="mt-1">{proposta.observacoes}</p>
                        </div>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setHistoryModal(proposta)}
                      >
                        <History className="w-4 h-4 mr-1" />
                        Historico
                      </Button>

                      {canContraproposta(proposta.status) && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setContrapropostaModal(proposta);
                            setContraValor(proposta.valor_proposta);
                          }}
                        >
                          <ArrowRightLeft className="w-4 h-4 mr-1" />
                          Contraproposta
                        </Button>
                      )}

                      {canChangeStatus(proposta.status) && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-green-600 hover:text-green-700"
                            onClick={() => handleStatusChange(proposta, 'aceita')}
                          >
                            <CheckCircle2 className="w-4 h-4 mr-1" />
                            Aceitar
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-red-600 hover:text-red-700"
                            onClick={() => handleStatusChange(proposta, 'recusada')}
                          >
                            <XCircle className="w-4 h-4 mr-1" />
                            Recusar
                          </Button>
                        </>
                      )}

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeleteId(proposta.id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {/* Create Proposal Modal */}
      <Dialog open={createModalOpen} onOpenChange={setCreateModalOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Nova Proposta</DialogTitle>
          </DialogHeader>

          <form onSubmit={rhfHandleCreate(handleCreate)}>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label>ID do Imóvel</Label>
                <Input {...registerProposta('imovel_id')} placeholder="UUID do imóvel" />
                {propostaErrors.imovel_id && <p className="text-sm text-destructive">{propostaErrors.imovel_id.message}</p>}
              </div>

              <div className="space-y-2">
                <Label>ID do Cliente</Label>
                <Input {...registerProposta('cliente_id')} placeholder="UUID do cliente" />
                {propostaErrors.cliente_id && <p className="text-sm text-destructive">{propostaErrors.cliente_id.message}</p>}
              </div>

              <div className="space-y-2">
                <Label>Valor da Proposta (R$)</Label>
                <Input type="number" min="0" step="0.01" {...registerProposta('valor_proposta')} placeholder="0,00" />
                {propostaErrors.valor_proposta && <p className="text-sm text-destructive">{propostaErrors.valor_proposta.message}</p>}
              </div>

              <div className="space-y-2">
                <Label>Prazo de Validade</Label>
                <Input type="date" {...registerProposta('prazo_validade')} />
              </div>

              <div className="space-y-2">
                <Label>Condições de Pagamento</Label>
                <Textarea {...registerProposta('condicoes_pagamento')} placeholder="Descreva as condições de pagamento..." rows={3} />
              </div>

              <div className="space-y-2">
                <Label>Observações</Label>
                <Textarea {...registerProposta('observacoes')} placeholder="Observações adicionais..." rows={3} />
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateModalOpen(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={isCreating}>
                Criar Proposta
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Counter-Proposal Modal */}
      <Dialog open={!!contrapropostaModal} onOpenChange={() => setContrapropostaModal(null)}>
        <DialogContent className="sm:max-w-[450px]">
          <DialogHeader>
            <DialogTitle>Enviar Contraproposta</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {contrapropostaModal && (
              <div className="text-sm text-muted-foreground">
                Valor original: {formatCurrency(contrapropostaModal.valor_proposta)}
              </div>
            )}

            <div className="space-y-2">
              <Label>Valor da Contraproposta (R$)</Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={contraValor || ''}
                onChange={(e) => setContraValor(parseFloat(e.target.value) || 0)}
                placeholder="0,00"
              />
            </div>

            <div className="space-y-2">
              <Label>Condicoes de Pagamento</Label>
              <Textarea
                value={contraCondicoes}
                onChange={(e) => setContraCondicoes(e.target.value)}
                placeholder="Novas condicoes..."
                rows={2}
              />
            </div>

            <div className="space-y-2">
              <Label>Observacoes</Label>
              <Textarea
                value={contraObs}
                onChange={(e) => setContraObs(e.target.value)}
                placeholder="Observacoes..."
                rows={2}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setContrapropostaModal(null)}>
              Cancelar
            </Button>
            <Button
              onClick={handleContraproposta}
              disabled={isSendingContra || !contraValor}
            >
              Enviar Contraproposta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* History Modal */}
      <Dialog open={!!historyModal} onOpenChange={() => setHistoryModal(null)}>
        <DialogContent className="sm:max-w-[500px] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Historico da Proposta</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {historyModal?.historico && historyModal.historico.length > 0 ? (
              historyModal.historico.map((entry: HistoricoProposta, index: number) => (
                <div key={index} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <div className="w-2 h-2 bg-primary rounded-full mt-2" />
                    {index < historyModal.historico.length - 1 && (
                      <div className="w-px flex-1 bg-border mt-1" />
                    )}
                  </div>
                  <div className="flex-1 pb-4">
                    <p className="font-medium text-sm">{entry.action}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(entry.timestamp, true)}
                    </p>
                    {entry.details && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        {Object.entries(entry.details).map(([key, value]) => (
                          <span key={key} className="block">
                            {key}: {typeof value === 'number' ? formatCurrency(value) : String(value)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-center text-muted-foreground">Nenhum historico disponivel</p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Proposta</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir esta proposta? Esta acao e irreversivel.
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
