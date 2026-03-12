import { useState } from 'react';
import {
  useChaves,
  useCreateChave,
  useRetirarChave,
  useDevolverChave,
  useChaveHistorico,
  type Chave,
} from '@/hooks/useChaves';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Search,
  Plus,
  Key,
  ArrowUpFromLine,
  ArrowDownToLine,
  History,
  Filter,
} from 'lucide-react';
import { formatDate } from '@/lib/utils';
import { MetricsTableSkeleton } from '@/components/ui/page-skeleton';

const STATUS_CONFIG = {
  disponivel: { label: 'Disponível', variant: 'default' as const, className: 'bg-green-100 text-green-800 hover:bg-green-100' },
  emprestada: { label: 'Emprestada', variant: 'default' as const, className: 'bg-yellow-100 text-yellow-800 hover:bg-yellow-100' },
  perdida: { label: 'Perdida', variant: 'default' as const, className: 'bg-red-100 text-red-800 hover:bg-red-100' },
};

export default function Chaves() {
  const [filtroStatus, setFiltroStatus] = useState<string>('');
  const [busca, setBusca] = useState('');
  const [dialogNovaChave, setDialogNovaChave] = useState(false);
  const [dialogRetirada, setDialogRetirada] = useState<string | null>(null);
  const [dialogDevolucao, setDialogDevolucao] = useState<string | null>(null);
  const [dialogHistorico, setDialogHistorico] = useState<string | null>(null);

  // Form states
  const [novaChave, setNovaChave] = useState({ imovel_id: '', codigo: '', descricao: '', observacoes: '' });
  const [retiradaForm, setRetiradaForm] = useState({ corretor_nome: '', motivo: '' });
  const [devolucaoForm, setDevolucaoForm] = useState({ corretor_nome: '', motivo: '' });

  const { data: chaves = [], isLoading } = useChaves(
    filtroStatus ? { status: filtroStatus } : undefined
  );
  const createMutation = useCreateChave();
  const retiradaMutation = useRetirarChave();
  const devolucaoMutation = useDevolverChave();
  const { data: historico = [] } = useChaveHistorico(dialogHistorico || undefined);

  const filtradas = chaves.filter((c) => {
    if (!busca) return true;
    const q = busca.toLowerCase();
    return (
      c.codigo.toLowerCase().includes(q) ||
      c.descricao?.toLowerCase().includes(q) ||
      c.ultima_retirada_nome?.toLowerCase().includes(q)
    );
  });

  const handleCriar = () => {
    if (!novaChave.imovel_id || !novaChave.codigo) return;
    createMutation.mutate(novaChave, {
      onSuccess: () => {
        setDialogNovaChave(false);
        setNovaChave({ imovel_id: '', codigo: '', descricao: '', observacoes: '' });
      },
    });
  };

  const handleRetirada = () => {
    if (!dialogRetirada || !retiradaForm.corretor_nome) return;
    retiradaMutation.mutate(
      { id: dialogRetirada, ...retiradaForm },
      {
        onSuccess: () => {
          setDialogRetirada(null);
          setRetiradaForm({ corretor_nome: '', motivo: '' });
        },
      }
    );
  };

  const handleDevolucao = () => {
    if (!dialogDevolucao || !devolucaoForm.corretor_nome) return;
    devolucaoMutation.mutate(
      { id: dialogDevolucao, ...devolucaoForm },
      {
        onSuccess: () => {
          setDialogDevolucao(null);
          setDevolucaoForm({ corretor_nome: '', motivo: '' });
        },
      }
    );
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Controle de Chaves</h1>
          <p className="text-muted-foreground">Gerencie as chaves dos imóveis</p>
        </div>
        <Button onClick={() => setDialogNovaChave(true)}>
          <Plus className="h-4 w-4 mr-2" />Nova Chave
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4 items-end">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por código, descrição ou nome..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="w-48">
              <Select value={filtroStatus} onValueChange={setFiltroStatus}>
                <SelectTrigger>
                  <Filter className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Todos os status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="disponivel">Disponível</SelectItem>
                  <SelectItem value="emprestada">Emprestada</SelectItem>
                  <SelectItem value="perdida">Perdida</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-2xl font-bold text-green-600">
              {chaves.filter((c) => c.status === 'disponivel').length}
            </div>
            <p className="text-sm text-muted-foreground">Disponíveis</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-2xl font-bold text-yellow-600">
              {chaves.filter((c) => c.status === 'emprestada').length}
            </div>
            <p className="text-sm text-muted-foreground">Emprestadas</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-2xl font-bold text-red-600">
              {chaves.filter((c) => c.status === 'perdida').length}
            </div>
            <p className="text-sm text-muted-foreground">Perdidas</p>
          </CardContent>
        </Card>
      </div>

      {/* Key list */}
      {isLoading ? (
        <MetricsTableSkeleton cards={0} />
      ) : filtradas.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Key className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg">Nenhuma chave encontrada</p>
            <p className="text-sm mt-1">Registre uma chave para começar o controle</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Código</TableHead>
                <TableHead>Descrição</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Última Retirada</TableHead>
                <TableHead>Última Devolução</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtradas.map((chave) => {
                const statusConfig = STATUS_CONFIG[chave.status];
                return (
                  <TableRow key={chave.id}>
                    <TableCell className="font-mono font-semibold">{chave.codigo}</TableCell>
                    <TableCell>{chave.descricao || '-'}</TableCell>
                    <TableCell>
                      <Badge className={statusConfig.className}>{statusConfig.label}</Badge>
                    </TableCell>
                    <TableCell>
                      {chave.ultima_retirada_em ? (
                        <div className="text-sm">
                          <div>{chave.ultima_retirada_nome}</div>
                          <div className="text-muted-foreground">{formatDate(chave.ultima_retirada_em, true)}</div>
                        </div>
                      ) : '-'}
                    </TableCell>
                    <TableCell>
                      {chave.ultima_devolucao_em
                        ? formatDate(chave.ultima_devolucao_em, true)
                        : '-'}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        {chave.status === 'disponivel' && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setDialogRetirada(chave.id)}
                          >
                            <ArrowUpFromLine className="h-3 w-3 mr-1" />Retirar
                          </Button>
                        )}
                        {chave.status === 'emprestada' && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setDialogDevolucao(chave.id)}
                          >
                            <ArrowDownToLine className="h-3 w-3 mr-1" />Devolver
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDialogHistorico(chave.id)}
                        >
                          <History className="h-3 w-3" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Dialog: Nova Chave */}
      <Dialog open={dialogNovaChave} onOpenChange={setDialogNovaChave}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar Nova Chave</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>ID do Imóvel *</Label>
              <Input
                value={novaChave.imovel_id}
                onChange={(e) => setNovaChave({ ...novaChave, imovel_id: e.target.value })}
                placeholder="ID do imóvel vinculado"
              />
            </div>
            <div>
              <Label>Código da Chave *</Label>
              <Input
                value={novaChave.codigo}
                onChange={(e) => setNovaChave({ ...novaChave, codigo: e.target.value })}
                placeholder="Ex: CH-001"
              />
            </div>
            <div>
              <Label>Descrição</Label>
              <Input
                value={novaChave.descricao}
                onChange={(e) => setNovaChave({ ...novaChave, descricao: e.target.value })}
                placeholder="Ex: Chave do portão principal"
              />
            </div>
            <div>
              <Label>Observações</Label>
              <Textarea
                value={novaChave.observacoes}
                onChange={(e) => setNovaChave({ ...novaChave, observacoes: e.target.value })}
                placeholder="Observações adicionais..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogNovaChave(false)}>Cancelar</Button>
            <Button onClick={handleCriar} disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Registrando...' : 'Registrar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog: Retirada */}
      <Dialog open={!!dialogRetirada} onOpenChange={() => setDialogRetirada(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar Retirada de Chave</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Nome do Corretor *</Label>
              <Input
                value={retiradaForm.corretor_nome}
                onChange={(e) => setRetiradaForm({ ...retiradaForm, corretor_nome: e.target.value })}
                placeholder="Nome de quem está retirando"
              />
            </div>
            <div>
              <Label>Motivo</Label>
              <Textarea
                value={retiradaForm.motivo}
                onChange={(e) => setRetiradaForm({ ...retiradaForm, motivo: e.target.value })}
                placeholder="Motivo da retirada..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogRetirada(null)}>Cancelar</Button>
            <Button onClick={handleRetirada} disabled={retiradaMutation.isPending}>
              {retiradaMutation.isPending ? 'Registrando...' : 'Confirmar Retirada'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog: Devolução */}
      <Dialog open={!!dialogDevolucao} onOpenChange={() => setDialogDevolucao(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar Devolução de Chave</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Nome do Corretor *</Label>
              <Input
                value={devolucaoForm.corretor_nome}
                onChange={(e) => setDevolucaoForm({ ...devolucaoForm, corretor_nome: e.target.value })}
                placeholder="Nome de quem está devolvendo"
              />
            </div>
            <div>
              <Label>Motivo</Label>
              <Textarea
                value={devolucaoForm.motivo}
                onChange={(e) => setDevolucaoForm({ ...devolucaoForm, motivo: e.target.value })}
                placeholder="Observações da devolução..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogDevolucao(null)}>Cancelar</Button>
            <Button onClick={handleDevolucao} disabled={devolucaoMutation.isPending}>
              {devolucaoMutation.isPending ? 'Registrando...' : 'Confirmar Devolução'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog: Histórico */}
      <Dialog open={!!dialogHistorico} onOpenChange={() => setDialogHistorico(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Histórico da Chave</DialogTitle>
          </DialogHeader>
          {historico.length === 0 ? (
            <p className="text-center text-muted-foreground py-4">Nenhum registro no histórico</p>
          ) : (
            <div className="max-h-96 overflow-y-auto space-y-3">
              {historico.map((h) => (
                <div key={h.id} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                  {h.acao === 'retirada' ? (
                    <ArrowUpFromLine className="h-4 w-4 text-yellow-600 mt-0.5 shrink-0" />
                  ) : (
                    <ArrowDownToLine className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{h.corretor_nome}</span>
                      <Badge variant="outline" className="text-xs">
                        {h.acao === 'retirada' ? 'Retirada' : 'Devolução'}
                      </Badge>
                    </div>
                    {h.motivo && <p className="text-sm text-muted-foreground mt-1">{h.motivo}</p>}
                    <p className="text-xs text-muted-foreground mt-1">{formatDate(h.created_at, true)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
