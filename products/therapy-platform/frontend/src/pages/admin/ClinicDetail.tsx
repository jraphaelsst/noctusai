import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, CheckCircle, XCircle, Ban,
  Building2, Users, DollarSign, Star, Percent,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { Input } from '@noctusai/seed/components/ui/input';
import { Separator } from '@noctusai/seed/components/ui/separator';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { useAdminClinic, useApproveEntity, useRejectEntity, useSuspendEntity } from '@/hooks/useAdmin';

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  aprovada: { label: 'Aprovada', variant: 'default' },
  rejeitada: { label: 'Rejeitada', variant: 'destructive' },
  suspensa: { label: 'Suspensa', variant: 'secondary' },
};

export default function AdminClinicDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: clinic, isLoading } = useAdminClinic(id);
  const approve = useApproveEntity();
  const reject = useRejectEntity();
  const suspend = useSuspendEntity();

  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [commissionEdit, setCommissionEdit] = useState(false);
  const [commissionValue, setCommissionValue] = useState('');

  if (isLoading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-64 bg-muted animate-pulse rounded" />
      </div>
    );
  }

  if (!clinic) {
    return (
      <div className="container mx-auto p-6">
        <p className="text-muted-foreground">Clinica nao encontrada</p>
        <Button variant="outline" className="mt-4" onClick={() => navigate('/admin/clinicas')}>
          <ArrowLeft className="h-4 w-4 mr-2" /> Voltar
        </Button>
      </div>
    );
  }

  const c = clinic as Record<string, unknown>;
  const nome = (c.nome as string) ?? 'Clinica';
  const cnpj = (c.cnpj as string) ?? '';
  const status = (c.status as string) ?? 'pendente';
  const badge = STATUS_BADGE[status] ?? STATUS_BADGE.pendente;
  const responsavel = (c.responsavel as string) ?? '';
  const email = (c.email as string) ?? '';
  const telefone = (c.telefone as string) ?? '';
  const endereco = (c.endereco as string) ?? '';
  const cidade = (c.cidade as string) ?? '';
  const estado = (c.estado as string) ?? '';
  const notaMedia = c.nota_media as number | undefined;
  const totalAvaliacoes = (c.total_avaliacoes as number) ?? 0;
  const commissionRate = (c.commission_override_pct as number) ?? null;

  const handleReject = () => {
    if (!id || !rejectReason.trim()) return;
    reject.mutate({ type: 'clinic', id, reason: rejectReason });
    setRejectDialogOpen(false);
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate('/admin/clinicas')}>
        <ArrowLeft className="h-4 w-4 mr-2" /> Clinicas
      </Button>

      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="h-16 w-16 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
          <Building2 className="h-8 w-8 text-primary" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{nome}</h1>
            <Badge variant={badge.variant}>{badge.label}</Badge>
          </div>
          <p className="text-muted-foreground">CNPJ: {cnpj} | {email}</p>
        </div>
        <div className="flex gap-2 shrink-0">
          {status === 'pendente' && (
            <>
              <Button
                className="bg-green-600 hover:bg-green-700"
                onClick={() => id && approve.mutate({ type: 'clinic', id })}
                disabled={approve.isPending}
              >
                <CheckCircle className="h-4 w-4 mr-2" /> Aprovar
              </Button>
              <Button
                variant="destructive"
                onClick={() => { setRejectReason(''); setRejectDialogOpen(true); }}
              >
                <XCircle className="h-4 w-4 mr-2" /> Rejeitar
              </Button>
            </>
          )}
          {status === 'aprovada' && (
            <Button
              variant="outline"
              onClick={() => id && suspend.mutate({ type: 'clinic', id })}
              disabled={suspend.isPending}
            >
              <Ban className="h-4 w-4 mr-2" /> Suspender
            </Button>
          )}
        </div>
      </div>

      <Tabs defaultValue="perfil">
        <TabsList>
          <TabsTrigger value="perfil">Perfil</TabsTrigger>
          <TabsTrigger value="terapeutas">Terapeutas</TabsTrigger>
          <TabsTrigger value="financeiro">Financeiro</TabsTrigger>
          <TabsTrigger value="avaliacoes">Avaliacoes</TabsTrigger>
          <TabsTrigger value="comissao">Comissao</TabsTrigger>
        </TabsList>

        <TabsContent value="perfil" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Informacoes da Clinica</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Responsavel</label>
                  <p className="mt-1">{responsavel || '-'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Telefone</label>
                  <p className="mt-1">{telefone || '-'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Endereco</label>
                  <p className="mt-1">{endereco || '-'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Cidade/Estado</label>
                  <p className="mt-1">{cidade}{estado ? ` - ${estado}` : ''}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="terapeutas" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Users className="h-5 w-5" /> Terapeutas Vinculados
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Nenhum terapeuta vinculado a esta clinica.</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="financeiro" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <DollarSign className="h-5 w-5" /> Resumo Financeiro
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Dados financeiros aparecerão aqui.</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="avaliacoes" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Star className="h-5 w-5" /> Avaliacoes
              </CardTitle>
            </CardHeader>
            <CardContent>
              {notaMedia != null ? (
                <div className="flex items-center gap-2 mb-4">
                  <Star className="h-5 w-5 text-yellow-500 fill-yellow-500" />
                  <span className="text-xl font-bold">{notaMedia.toFixed(1)}</span>
                  <span className="text-muted-foreground">({totalAvaliacoes} avaliacoes)</span>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Nenhuma avaliacao recebida.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="comissao" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Percent className="h-5 w-5" /> Taxa da Plataforma
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium text-muted-foreground">Taxa atual aplicada</label>
                <p className="text-lg font-semibold mt-1">
                  {commissionRate != null
                    ? `${commissionRate}% (override individual)`
                    : 'Taxa global da plataforma'}
                </p>
              </div>
              <Separator />
              {commissionEdit ? (
                <div className="flex items-center gap-3">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    step={0.5}
                    value={commissionValue}
                    onChange={e => setCommissionValue(e.target.value)}
                    placeholder="Ex: 15"
                    className="w-32"
                  />
                  <span className="text-muted-foreground">%</span>
                  <Button size="sm" onClick={() => setCommissionEdit(false)}>Salvar</Button>
                  <Button size="sm" variant="outline" onClick={() => setCommissionEdit(false)}>Cancelar</Button>
                </div>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setCommissionValue(commissionRate?.toString() ?? '');
                    setCommissionEdit(true);
                  }}
                >
                  Editar override
                </Button>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rejeitar clinica</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm text-muted-foreground">Motivo da rejeicao</label>
            <Input
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              placeholder="Descreva o motivo..."
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialogOpen(false)}>Cancelar</Button>
            <Button variant="destructive" onClick={handleReject} disabled={!rejectReason.trim()}>
              Confirmar rejeicao
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
