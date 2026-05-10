import { useState, useMemo } from 'react';
import {
  Search, CheckCircle, XCircle, Eye, Users, Star,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Input } from '@noctusai/seed/components/ui/input';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { Avatar, AvatarFallback } from '@noctusai/seed/components/ui/avatar';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { useAdminTherapists, useApproveEntity, useRejectEntity } from '@/hooks/useAdmin';
import { useNavigate } from 'react-router-dom';
import type { Terapeuta } from '@/types';

type StatusFilter = 'todos' | 'pendente' | 'aprovado' | 'rejeitado';

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  aprovado: { label: 'Aprovado', variant: 'default' },
  rejeitado: { label: 'Rejeitado', variant: 'destructive' },
  suspenso: { label: 'Suspenso', variant: 'secondary' },
};

function getInitials(name: string) {
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

export default function AdminTherapists() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('todos');
  const [busca, setBusca] = useState('');
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  const { data, isLoading } = useAdminTherapists(
    statusFilter !== 'todos' ? { status: statusFilter } : undefined
  );
  const approve = useApproveEntity();
  const reject = useRejectEntity();

  const therapists = (data?.data ?? []) as Terapeuta[];

  const filtered = useMemo(() => {
    if (!busca.trim()) return therapists;
    const q = busca.toLowerCase();
    return therapists.filter(t =>
      t.nome.toLowerCase().includes(q) || t.crp.toLowerCase().includes(q)
    );
  }, [therapists, busca]);

  const handleReject = () => {
    if (!rejectTarget || !rejectReason.trim()) return;
    reject.mutate({ type: 'therapist', id: rejectTarget, reason: rejectReason });
    setRejectDialogOpen(false);
    setRejectTarget(null);
    setRejectReason('');
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Terapeutas</h1>
        <p className="text-muted-foreground">Gerenciar cadastros de terapeutas na plataforma</p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={busca}
            onChange={e => setBusca(e.target.value)}
            placeholder="Buscar por nome ou CRP..."
            className="pl-9"
          />
        </div>
        <Tabs value={statusFilter} onValueChange={v => setStatusFilter(v as StatusFilter)}>
          <TabsList>
            <TabsTrigger value="todos">Todos</TabsTrigger>
            <TabsTrigger value="pendente">Pendentes</TabsTrigger>
            <TabsTrigger value="aprovado">Aprovados</TabsTrigger>
            <TabsTrigger value="rejeitado">Rejeitados</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6">
                <div className="flex items-center gap-4">
                  <div className="h-12 w-12 rounded-full bg-muted" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-32 bg-muted rounded" />
                    <div className="h-3 w-20 bg-muted rounded" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <Users className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-lg font-medium text-muted-foreground">
              {statusFilter === 'pendente'
                ? 'Nenhum terapeuta pendente de aprovacao'
                : 'Nenhum terapeuta encontrado'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map(t => {
            const badge = STATUS_BADGE[t.status] ?? STATUS_BADGE.pendente;
            return (
              <Card key={t.id} className="hover:shadow-md transition-shadow">
                <CardContent className="p-5">
                  <div className="flex items-start gap-4">
                    <Avatar className="h-12 w-12">
                      <AvatarFallback>{getInitials(t.nome)}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold truncate">{t.nome}</span>
                        <Badge variant={badge.variant} className="shrink-0">{badge.label}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mt-0.5">CRP: {t.crp}</p>
                      {t.nota_media != null && (
                        <div className="flex items-center gap-1 mt-1">
                          <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />
                          <span className="text-sm">{t.nota_media.toFixed(1)}</span>
                          <span className="text-xs text-muted-foreground">({t.total_avaliacoes ?? 0})</span>
                        </div>
                      )}
                      <p className="text-xs text-muted-foreground mt-1">
                        {t.especialidades?.slice(0, 3).join(', ')}
                      </p>
                    </div>
                  </div>

                  <div className="flex gap-2 mt-4">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => navigate(`/admin/terapeutas/${t.id}`)}
                    >
                      <Eye className="h-3.5 w-3.5 mr-1" />
                      Detalhes
                    </Button>
                    {t.status === 'pendente' && (
                      <>
                        <Button
                          size="sm"
                          className="bg-green-600 hover:bg-green-700"
                          onClick={() => approve.mutate({ type: 'therapist', id: t.id })}
                          disabled={approve.isPending}
                        >
                          <CheckCircle className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => {
                            setRejectTarget(t.id);
                            setRejectReason('');
                            setRejectDialogOpen(true);
                          }}
                        >
                          <XCircle className="h-3.5 w-3.5" />
                        </Button>
                      </>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Reject dialog */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rejeitar terapeuta</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm text-muted-foreground">
              Motivo da rejeicao
            </label>
            <Input
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              placeholder="Descreva o motivo..."
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialogOpen(false)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={handleReject} disabled={!rejectReason.trim()}>
              Confirmar rejeicao
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
