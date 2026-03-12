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
  Users,
  Link,
  Plus,
  Trash2,
  Eye,
  MessageSquare,
  Clock,
  CheckCircle2,
} from 'lucide-react';
import { formatDate } from '@/lib/utils';
import { TableSkeleton } from '@/components/ui/page-skeleton';
import {
  usePortalAcessos,
  useGerarAcesso,
  useRevogarAcesso,
  useChamadosPortal,
  useUpdateChamado,
  PortalAcesso,
  ChamadoPortal,
} from '@/hooks/usePortalCliente';
import { toast } from 'sonner';

const STATUS_CHAMADO: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  aberto: { label: 'Aberto', variant: 'destructive' },
  em_andamento: { label: 'Em Andamento', variant: 'outline' },
  resolvido: { label: 'Resolvido', variant: 'default' },
  fechado: { label: 'Fechado', variant: 'secondary' },
};

const PRIORIDADE_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  baixa: { label: 'Baixa', variant: 'secondary' },
  media: { label: 'Media', variant: 'outline' },
  alta: { label: 'Alta', variant: 'destructive' },
  urgente: { label: 'Urgente', variant: 'destructive' },
};

export default function PortalCliente() {
  const [activeTab, setActiveTab] = useState<'acessos' | 'chamados'>('acessos');
  const [filtroStatusChamado, setFiltroStatusChamado] = useState<string>('todos');
  const [gerarAcessoOpen, setGerarAcessoOpen] = useState(false);
  const [respondChamadoOpen, setRespondChamadoOpen] = useState(false);
  const [selectedChamado, setSelectedChamado] = useState<ChamadoPortal | null>(null);
  const [revokeId, setRevokeId] = useState<string | null>(null);

  const [gerarForm, setGerarForm] = useState({ cliente_id: '', data_expiracao: '' });
  const [respondForm, setRespondForm] = useState({ status: '', resposta: '' });

  const { data: acessosData, isLoading: isLoadingAcessos } = usePortalAcessos();
  const acessos = acessosData?.data || [];

  const { data: chamadosData, isLoading: isLoadingChamados } = useChamadosPortal({
    status: filtroStatusChamado !== 'todos' ? filtroStatusChamado : undefined,
  });
  const chamados = chamadosData?.data || [];

  const { mutate: gerarAcesso, isPending: isGerando } = useGerarAcesso();
  const { mutate: revogarAcesso } = useRevogarAcesso();
  const { mutate: updateChamado, isPending: isUpdatingChamado } = useUpdateChamado();

  const acessosAtivos = acessos.filter((a) => a.ativo).length;
  const chamadosAbertos = chamados.filter((c) => c.status === 'aberto').length;
  const chamadosResolvidos = chamados.filter((c) => c.status === 'resolvido').length;

  const handleGerarAcesso = () => {
    if (!gerarForm.cliente_id) return;

    gerarAcesso(
      {
        cliente_id: gerarForm.cliente_id,
        data_expiracao: gerarForm.data_expiracao || undefined,
      },
      {
        onSuccess: () => {
          setGerarAcessoOpen(false);
          setGerarForm({ cliente_id: '', data_expiracao: '' });
        },
      },
    );
  };

  const handleRevogar = () => {
    if (revokeId) {
      revogarAcesso(revokeId);
      setRevokeId(null);
    }
  };

  const handleOpenRespondChamado = (chamado: ChamadoPortal) => {
    setSelectedChamado(chamado);
    setRespondForm({
      status: chamado.status,
      resposta: chamado.resposta || '',
    });
    setRespondChamadoOpen(true);
  };

  const handleRespondChamado = () => {
    if (!selectedChamado) return;

    updateChamado(
      {
        id: selectedChamado.id,
        status: respondForm.status,
        resposta: respondForm.resposta || undefined,
      },
      {
        onSuccess: () => {
          setRespondChamadoOpen(false);
          setSelectedChamado(null);
          setRespondForm({ status: '', resposta: '' });
        },
      },
    );
  };

  const handleCopyLink = (acesso: PortalAcesso) => {
    const link = acesso.link || acesso.token;
    navigator.clipboard.writeText(link);
    toast.success('Link copiado para a area de transferencia!');
  };

  const truncateToken = (token: string) => {
    if (token.length <= 16) return token;
    return `${token.slice(0, 8)}...${token.slice(-8)}`;
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Portal do Cliente</h1>
          <p className="text-muted-foreground">Gerencie acessos e chamados do portal</p>
        </div>
        <Button onClick={() => setGerarAcessoOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Gerar Acesso
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Acessos Ativos</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{acessosAtivos}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Chamados Abertos</CardTitle>
            <Clock className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">{chamadosAbertos}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Chamados Resolvidos</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{chamadosResolvidos}</div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        <Button
          variant={activeTab === 'acessos' ? 'default' : 'outline'}
          onClick={() => setActiveTab('acessos')}
        >
          <Link className="w-4 h-4 mr-2" />
          Acessos
        </Button>
        <Button
          variant={activeTab === 'chamados' ? 'default' : 'outline'}
          onClick={() => setActiveTab('chamados')}
        >
          <MessageSquare className="w-4 h-4 mr-2" />
          Chamados
        </Button>
      </div>

      {/* Acessos Section */}
      {activeTab === 'acessos' && (
        <Card>
          <CardContent className="pt-6">
            {isLoadingAcessos ? (
              <TableSkeleton rows={3} />
            ) : acessos.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">
                Nenhum acesso encontrado
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Cliente ID</TableHead>
                      <TableHead>Token</TableHead>
                      <TableHead>Ultimo Acesso</TableHead>
                      <TableHead>Expiracao</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Acoes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {acessos.map((acesso) => (
                      <TableRow key={acesso.id}>
                        <TableCell className="font-medium max-w-[150px] truncate">
                          {acesso.cliente_id}
                        </TableCell>
                        <TableCell className="font-mono text-sm">
                          {truncateToken(acesso.token)}
                        </TableCell>
                        <TableCell>
                          {acesso.ultimo_acesso ? formatDate(acesso.ultimo_acesso, true) : '-'}
                        </TableCell>
                        <TableCell>
                          {acesso.data_expiracao ? formatDate(acesso.data_expiracao) : '-'}
                        </TableCell>
                        <TableCell>
                          <Badge variant={acesso.ativo ? 'default' : 'secondary'}>
                            {acesso.ativo ? 'Ativo' : 'Inativo'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCopyLink(acesso)}
                              title="Copiar link"
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setRevokeId(acesso.id)}
                              title="Revogar acesso"
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
      )}

      {/* Chamados Section */}
      {activeTab === 'chamados' && (
        <>
          {/* Chamados Filter */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex flex-wrap gap-4">
                <Select value={filtroStatusChamado} onValueChange={setFiltroStatusChamado}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="todos">Todos os Status</SelectItem>
                    <SelectItem value="aberto">Aberto</SelectItem>
                    <SelectItem value="em_andamento">Em Andamento</SelectItem>
                    <SelectItem value="resolvido">Resolvido</SelectItem>
                    <SelectItem value="fechado">Fechado</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Chamados Table */}
          <Card>
            <CardContent className="pt-6">
              {isLoadingChamados ? (
                <TableSkeleton rows={3} />
              ) : chamados.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground">
                  Nenhum chamado encontrado
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Assunto</TableHead>
                        <TableHead>Cliente</TableHead>
                        <TableHead>Prioridade</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Data</TableHead>
                        <TableHead className="text-right">Acoes</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {chamados.map((chamado) => (
                        <TableRow key={chamado.id}>
                          <TableCell className="max-w-[200px] truncate font-medium">
                            {chamado.assunto}
                          </TableCell>
                          <TableCell className="max-w-[150px] truncate">
                            {chamado.cliente_id}
                          </TableCell>
                          <TableCell>
                            <Badge variant={PRIORIDADE_CONFIG[chamado.prioridade]?.variant || 'outline'}>
                              {PRIORIDADE_CONFIG[chamado.prioridade]?.label || chamado.prioridade}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={STATUS_CHAMADO[chamado.status]?.variant || 'outline'}>
                              {STATUS_CHAMADO[chamado.status]?.label || chamado.status}
                            </Badge>
                          </TableCell>
                          <TableCell>{formatDate(chamado.created_at)}</TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenRespondChamado(chamado)}
                              title="Responder chamado"
                            >
                              <MessageSquare className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Generate Access Dialog */}
      <Dialog open={gerarAcessoOpen} onOpenChange={setGerarAcessoOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Gerar Acesso ao Portal</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Cliente ID</Label>
              <Input
                value={gerarForm.cliente_id}
                onChange={(e) => setGerarForm({ ...gerarForm, cliente_id: e.target.value })}
                placeholder="ID do cliente"
              />
            </div>

            <div className="space-y-2">
              <Label>Data de Expiracao (opcional)</Label>
              <Input
                type="date"
                value={gerarForm.data_expiracao}
                onChange={(e) => setGerarForm({ ...gerarForm, data_expiracao: e.target.value })}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setGerarAcessoOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleGerarAcesso}
              disabled={isGerando || !gerarForm.cliente_id}
            >
              {isGerando ? 'Gerando...' : 'Gerar Acesso'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Respond to Ticket Dialog */}
      <Dialog open={respondChamadoOpen} onOpenChange={setRespondChamadoOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Responder Chamado</DialogTitle>
          </DialogHeader>

          {selectedChamado && (
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label className="text-muted-foreground">Assunto</Label>
                <p className="font-medium">{selectedChamado.assunto}</p>
              </div>

              <div className="space-y-2">
                <Label className="text-muted-foreground">Descricao</Label>
                <p className="text-sm bg-muted p-3 rounded-md whitespace-pre-wrap">
                  {selectedChamado.descricao}
                </p>
              </div>

              <div className="space-y-2">
                <Label>Status</Label>
                <Select
                  value={respondForm.status}
                  onValueChange={(v) => setRespondForm({ ...respondForm, status: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="aberto">Aberto</SelectItem>
                    <SelectItem value="em_andamento">Em Andamento</SelectItem>
                    <SelectItem value="resolvido">Resolvido</SelectItem>
                    <SelectItem value="fechado">Fechado</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Resposta</Label>
                <Textarea
                  value={respondForm.resposta}
                  onChange={(e) => setRespondForm({ ...respondForm, resposta: e.target.value })}
                  placeholder="Digite sua resposta ao chamado..."
                  rows={5}
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setRespondChamadoOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleRespondChamado}
              disabled={isUpdatingChamado || !respondForm.status}
            >
              {isUpdatingChamado ? 'Salvando...' : 'Salvar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke Confirmation */}
      <AlertDialog open={!!revokeId} onOpenChange={() => setRevokeId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revogar Acesso</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja revogar este acesso? O cliente perdera acesso ao portal imediatamente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleRevogar} className="bg-destructive hover:bg-destructive/90">
              Revogar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
