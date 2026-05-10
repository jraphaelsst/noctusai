import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, CheckCircle, XCircle, Ban, Mail,
  Star, Calendar, DollarSign, Percent, User,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Avatar, AvatarFallback } from '@noctusai/seed/components/ui/avatar';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { Input } from '@noctusai/seed/components/ui/input';
import { Separator } from '@noctusai/seed/components/ui/separator';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { useAdminTherapist, useApproveEntity, useRejectEntity, useSuspendEntity } from '@/hooks/useAdmin';
import { formatCurrency } from '@/lib/utils';

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  aprovado: { label: 'Aprovado', variant: 'default' },
  rejeitado: { label: 'Rejeitado', variant: 'destructive' },
  suspenso: { label: 'Suspenso', variant: 'secondary' },
};

function getInitials(name: string) {
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

export default function AdminTherapistDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: therapist, isLoading } = useAdminTherapist(id);
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

  if (!therapist) {
    return (
      <div className="container mx-auto p-6">
        <p className="text-muted-foreground">Terapeuta nao encontrado</p>
        <Button variant="outline" className="mt-4" onClick={() => navigate('/admin/terapeutas')}>
          <ArrowLeft className="h-4 w-4 mr-2" /> Voltar
        </Button>
      </div>
    );
  }

  const t = therapist as Record<string, unknown>;
  const nome = (t.nome as string) ?? 'Terapeuta';
  const crp = (t.crp as string) ?? '';
  const status = (t.status as string) ?? 'pendente';
  const badge = STATUS_BADGE[status] ?? STATUS_BADGE.pendente;
  const bio = (t.bio as string) ?? '';
  const especialidades = (t.especialidades as string[]) ?? [];
  const abordagens = (t.abordagens as string[]) ?? [];
  const valorSessao = t.valor_sessao as number | undefined;
  const notaMedia = t.nota_media as number | undefined;
  const totalAvaliacoes = (t.total_avaliacoes as number) ?? 0;
  const email = (t.email as string) ?? '';
  const approvedAt = t.approved_at as string | undefined;
  const commissionRate = (t.commission_override_pct as number) ?? null;

  const handleReject = () => {
    if (!id || !rejectReason.trim()) return;
    reject.mutate({ type: 'therapist', id, reason: rejectReason });
    setRejectDialogOpen(false);
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Back + Header */}
      <Button variant="ghost" size="sm" onClick={() => navigate('/admin/terapeutas')}>
        <ArrowLeft className="h-4 w-4 mr-2" /> Terapeutas
      </Button>

      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <Avatar className="h-16 w-16">
          <AvatarFallback className="text-lg">{getInitials(nome)}</AvatarFallback>
        </Avatar>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{nome}</h1>
            <Badge variant={badge.variant}>{badge.label}</Badge>
          </div>
          <p className="text-muted-foreground">CRP: {crp} | {email}</p>
          {approvedAt && (
            <p className="text-xs text-muted-foreground mt-1">
              Aprovado em {new Date(approvedAt).toLocaleDateString('pt-BR')}
            </p>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          {status === 'pendente' && (
            <>
              <Button
                className="bg-green-600 hover:bg-green-700"
                onClick={() => id && approve.mutate({ type: 'therapist', id })}
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
          {status === 'aprovado' && (
            <Button
              variant="outline"
              onClick={() => id && suspend.mutate({ type: 'therapist', id })}
              disabled={suspend.isPending}
            >
              <Ban className="h-4 w-4 mr-2" /> Suspender
            </Button>
          )}
          <Button variant="outline">
            <Mail className="h-4 w-4 mr-2" /> Enviar Mensagem
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="perfil">
        <TabsList>
          <TabsTrigger value="perfil">Perfil</TabsTrigger>
          <TabsTrigger value="sessoes">Sessoes</TabsTrigger>
          <TabsTrigger value="financeiro">Financeiro</TabsTrigger>
          <TabsTrigger value="avaliacoes">Avaliacoes</TabsTrigger>
          <TabsTrigger value="comissao">Comissao</TabsTrigger>
        </TabsList>

        <TabsContent value="perfil" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <User className="h-5 w-5" /> Informacoes Profissionais
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {bio && (
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Bio</label>
                  <p className="mt-1">{bio}</p>
                </div>
              )}
              <Separator />
              <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Especialidades</label>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {especialidades.length > 0 ? especialidades.map(e => (
                      <Badge key={e} variant="secondary">{e}</Badge>
                    )) : <span className="text-sm text-muted-foreground">Nenhuma</span>}
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Abordagens</label>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {abordagens.length > 0 ? abordagens.map(a => (
                      <Badge key={a} variant="outline">{a}</Badge>
                    )) : <span className="text-sm text-muted-foreground">Nenhuma</span>}
                  </div>
                </div>
              </div>
              {valorSessao != null && (
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Valor da sessao</label>
                  <p className="text-lg font-semibold mt-1">{formatCurrency(valorSessao)}</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sessoes" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Calendar className="h-5 w-5" /> Historico de Sessoes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Nenhuma sessao registrada.</p>
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
              <div className="text-sm text-muted-foreground">
                <p className="font-medium mb-1">Cadeia de aplicacao:</p>
                <ol className="list-decimal list-inside space-y-1">
                  <li>Override individual do terapeuta {commissionRate != null && <Badge variant="default" className="ml-1">Ativo</Badge>}</li>
                  <li>Override da clinica (se vinculado)</li>
                  <li>Taxa global da plataforma</li>
                </ol>
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
                  <Button size="sm" onClick={() => setCommissionEdit(false)}>
                    Salvar
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setCommissionEdit(false)}>
                    Cancelar
                  </Button>
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

      {/* Reject dialog */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rejeitar terapeuta</DialogTitle>
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
