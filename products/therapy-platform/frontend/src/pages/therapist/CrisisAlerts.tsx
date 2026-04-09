import { useState } from 'react';
import { Loader2, AlertTriangle, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useCrisisAlerts, useReviewCrisisAlert } from '@/hooks/useCrisis';

const SEVERIDADE_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  baixa: { label: 'Baixa', variant: 'secondary' },
  media: { label: 'Media', variant: 'outline' },
  alta: { label: 'Alta', variant: 'default' },
  critica: { label: 'Critica', variant: 'destructive' },
};

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pendente: { label: 'Pendente', variant: 'destructive' },
  revisado: { label: 'Revisado', variant: 'default' },
  falso_positivo: { label: 'Falso Positivo', variant: 'secondary' },
  encaminhado: { label: 'Encaminhado', variant: 'outline' },
};

export default function CrisisAlerts() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useCrisisAlerts(page);
  const reviewAlert = useReviewCrisisAlert();

  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewTarget, setReviewTarget] = useState<string | null>(null);
  const [reviewStatus, setReviewStatus] = useState('revisado');

  const alerts = data?.data ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 20);

  function handleReview() {
    if (!reviewTarget) return;
    reviewAlert.mutate({ id: reviewTarget, status: reviewStatus }, {
      onSuccess: () => {
        setReviewOpen(false);
        setReviewTarget(null);
      },
    });
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <AlertTriangle className="h-6 w-6 text-orange-500" /> Alertas de Crise
        </h1>
        <p className="text-muted-foreground">Monitoramento de sinais de crise detectados automaticamente</p>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : alerts.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <CheckCircle className="h-12 w-12 text-green-500/30" />
            <p className="mt-3 text-lg font-medium text-muted-foreground">Nenhum alerta pendente</p>
            <p className="text-sm text-muted-foreground">Todos os alertas foram revisados</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert) => {
            const sevBadge = SEVERIDADE_BADGE[alert.severidade] ?? SEVERIDADE_BADGE.media;
            const statusBadge = STATUS_BADGE[alert.status] ?? STATUS_BADGE.pendente;
            return (
              <Card key={alert.id} className={alert.severidade === 'critica' ? 'border-red-300' : ''}>
                <CardContent className="p-4">
                  <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                    <div className="flex-1 space-y-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant={sevBadge.variant}>{sevBadge.label}</Badge>
                        <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
                        <span className="text-xs text-muted-foreground">
                          Fonte: {alert.source_type}
                        </span>
                      </div>
                      <div className="bg-red-50 p-3 rounded-md">
                        <p className="text-sm">{alert.conteudo_flagged}</p>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {alert.palavras_detectadas.map((palavra, i) => (
                          <Badge key={i} variant="outline" className="text-xs">{palavra}</Badge>
                        ))}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Detectado em {new Date(alert.created_at).toLocaleString('pt-BR')}
                      </p>
                      {alert.revisado_at && (
                        <p className="text-xs text-muted-foreground">
                          Revisado em {new Date(alert.revisado_at).toLocaleString('pt-BR')}
                        </p>
                      )}
                    </div>
                    {alert.status === 'pendente' && (
                      <Button
                        size="sm"
                        className="shrink-0"
                        onClick={() => {
                          setReviewTarget(alert.id);
                          setReviewStatus('revisado');
                          setReviewOpen(true);
                        }}
                      >
                        Revisar
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}

          {totalPages > 1 && (
            <div className="flex justify-center gap-2 mt-4">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</Button>
              <span className="text-sm text-muted-foreground flex items-center px-2">Pagina {page} de {totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Proxima</Button>
            </div>
          )}
        </div>
      )}

      {/* Review Dialog */}
      <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revisar Alerta de Crise</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">Status</label>
              <Select value={reviewStatus} onValueChange={setReviewStatus}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="revisado">Revisado</SelectItem>
                  <SelectItem value="falso_positivo">Falso Positivo</SelectItem>
                  <SelectItem value="encaminhado">Encaminhado</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviewOpen(false)}>Cancelar</Button>
            <Button onClick={handleReview} disabled={reviewAlert.isPending}>
              {reviewAlert.isPending ? 'Salvando...' : 'Confirmar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
