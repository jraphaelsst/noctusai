import { useState, useMemo } from 'react';
import {
  Search, CheckCircle, XCircle, Eye, Building2, Star,
} from 'lucide-react';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Input } from '@noctusai/seed/components/ui/input';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { useAdminClinics, useApproveEntity, useRejectEntity } from '@/hooks/useAdmin';
import { useNavigate } from 'react-router-dom';
import type { Clinica } from '@/types';

type StatusFilter = 'todos' | 'pendente' | 'aprovada' | 'rejeitada';

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  aprovada: { label: 'Aprovada', variant: 'default' },
  rejeitada: { label: 'Rejeitada', variant: 'destructive' },
  suspensa: { label: 'Suspensa', variant: 'secondary' },
};

export default function AdminClinics() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('todos');
  const [busca, setBusca] = useState('');
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  const { data, isLoading } = useAdminClinics(
    statusFilter !== 'todos' ? { status: statusFilter } : undefined
  );
  const approve = useApproveEntity();
  const reject = useRejectEntity();

  const clinics = (data?.data ?? []) as Clinica[];

  const filtered = useMemo(() => {
    if (!busca.trim()) return clinics;
    const q = busca.toLowerCase();
    return clinics.filter(c =>
      c.nome.toLowerCase().includes(q) || c.cnpj.includes(q)
    );
  }, [clinics, busca]);

  const handleReject = () => {
    if (!rejectTarget || !rejectReason.trim()) return;
    reject.mutate({ type: 'clinic', id: rejectTarget, reason: rejectReason });
    setRejectDialogOpen(false);
    setRejectTarget(null);
    setRejectReason('');
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Clinicas</h1>
        <p className="text-muted-foreground">Gerenciar cadastros de clinicas na plataforma</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={busca}
            onChange={e => setBusca(e.target.value)}
            placeholder="Buscar por nome ou CNPJ..."
            className="pl-9"
          />
        </div>
        <Tabs value={statusFilter} onValueChange={v => setStatusFilter(v as StatusFilter)}>
          <TabsList>
            <TabsTrigger value="todos">Todos</TabsTrigger>
            <TabsTrigger value="pendente">Pendentes</TabsTrigger>
            <TabsTrigger value="aprovada">Aprovadas</TabsTrigger>
            <TabsTrigger value="rejeitada">Rejeitadas</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {isLoading ? (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6">
                <div className="h-16 bg-muted rounded" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <Building2 className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-lg font-medium text-muted-foreground">
              {statusFilter === 'pendente'
                ? 'Nenhuma clinica pendente de aprovacao'
                : 'Nenhuma clinica encontrada'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map(c => {
            const badge = STATUS_BADGE[c.status] ?? STATUS_BADGE.pendente;
            return (
              <Card key={c.id} className="hover:shadow-md transition-shadow">
                <CardContent className="p-5">
                  <div className="flex items-start gap-4">
                    <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                      <Building2 className="h-6 w-6 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold truncate">{c.nome}</span>
                        <Badge variant={badge.variant} className="shrink-0">{badge.label}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mt-0.5">CNPJ: {c.cnpj}</p>
                      {c.nota_media != null && (
                        <div className="flex items-center gap-1 mt-1">
                          <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />
                          <span className="text-sm">{c.nota_media.toFixed(1)}</span>
                          <span className="text-xs text-muted-foreground">({c.total_avaliacoes ?? 0})</span>
                        </div>
                      )}
                      <p className="text-xs text-muted-foreground mt-1">
                        {c.cidade}{c.estado ? ` - ${c.estado}` : ''}
                      </p>
                    </div>
                  </div>

                  <div className="flex gap-2 mt-4">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => navigate(`/admin/clinicas/${c.id}`)}
                    >
                      <Eye className="h-3.5 w-3.5 mr-1" /> Detalhes
                    </Button>
                    {c.status === 'pendente' && (
                      <>
                        <Button
                          size="sm"
                          className="bg-green-600 hover:bg-green-700"
                          onClick={() => approve.mutate({ type: 'clinic', id: c.id })}
                          disabled={approve.isPending}
                        >
                          <CheckCircle className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => {
                            setRejectTarget(c.id);
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
