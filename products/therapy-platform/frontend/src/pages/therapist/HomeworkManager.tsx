import { useState } from 'react';
import { Loader2, CheckSquare, Plus } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { formatDate } from '@/lib/utils';
import { useHomeworkList, useCreateHomework, useReviewHomework } from '@/hooks/useHomework';

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  enviada: { label: 'Enviada', variant: 'default' },
  revisada: { label: 'Revisada', variant: 'secondary' },
  atrasada: { label: 'Atrasada', variant: 'destructive' },
};

export default function HomeworkManager() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useHomeworkList(page);
  const createHomework = useCreateHomework();
  const reviewHomework = useReviewHomework();

  const [createOpen, setCreateOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewTarget, setReviewTarget] = useState<string | null>(null);
  const [reviewFeedback, setReviewFeedback] = useState('');
  const [form, setForm] = useState({ patient_id: '', titulo: '', descricao: '', data_limite: '' });

  const items = data?.data ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 10);

  function handleCreate() {
    createHomework.mutate(form, {
      onSuccess: () => {
        setCreateOpen(false);
        setForm({ patient_id: '', titulo: '', descricao: '', data_limite: '' });
      },
    });
  }

  function handleReview() {
    if (!reviewTarget || !reviewFeedback.trim()) return;
    reviewHomework.mutate({ id: reviewTarget, feedback_terapeuta: reviewFeedback }, {
      onSuccess: () => {
        setReviewOpen(false);
        setReviewTarget(null);
        setReviewFeedback('');
      },
    });
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CheckSquare className="h-6 w-6" /> Tarefas Terapeuticas
          </h1>
          <p className="text-muted-foreground">Gerencie tarefas e atividades para seus pacientes</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-1" /> Nova Tarefa
        </Button>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <CheckSquare className="h-10 w-10 text-muted-foreground/30" />
            <p className="mt-3 text-sm text-muted-foreground">Nenhuma tarefa criada</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((hw) => {
            const badge = STATUS_BADGE[hw.status] ?? STATUS_BADGE.pendente;
            return (
              <Card key={hw.id}>
                <CardContent className="p-4">
                  <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                    <div className="flex-1 space-y-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium">{hw.titulo}</span>
                        <Badge variant={badge.variant}>{badge.label}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">{hw.descricao}</p>
                      <div className="flex gap-4 text-xs text-muted-foreground">
                        <span>Criada: {formatDate(hw.created_at)}</span>
                        {hw.data_limite && <span>Prazo: {formatDate(hw.data_limite)}</span>}
                      </div>
                      {hw.resposta_paciente && (
                        <div className="mt-2 bg-muted/50 p-3 rounded-md">
                          <p className="text-xs font-medium text-muted-foreground mb-1">Resposta do Paciente</p>
                          <p className="text-sm">{hw.resposta_paciente}</p>
                        </div>
                      )}
                      {hw.feedback_terapeuta && (
                        <div className="mt-2 bg-blue-50 p-3 rounded-md">
                          <p className="text-xs font-medium text-blue-600 mb-1">Seu Feedback</p>
                          <p className="text-sm">{hw.feedback_terapeuta}</p>
                        </div>
                      )}
                    </div>
                    {hw.resposta_paciente && !hw.feedback_terapeuta && (
                      <Button
                        size="sm"
                        className="shrink-0"
                        onClick={() => {
                          setReviewTarget(hw.id);
                          setReviewFeedback('');
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

      {/* Create Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nova Tarefa Terapeutica</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>ID do Paciente *</Label>
              <Input value={form.patient_id} onChange={(e) => setForm({ ...form, patient_id: e.target.value })} />
            </div>
            <div>
              <Label>Titulo *</Label>
              <Input value={form.titulo} onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
            </div>
            <div>
              <Label>Descricao *</Label>
              <Textarea value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
            </div>
            <div>
              <Label>Data Limite</Label>
              <Input type="date" value={form.data_limite} onChange={(e) => setForm({ ...form, data_limite: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancelar</Button>
            <Button
              onClick={handleCreate}
              disabled={!form.patient_id || !form.titulo.trim() || !form.descricao.trim() || createHomework.isPending}
            >
              {createHomework.isPending ? 'Criando...' : 'Criar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Review Dialog */}
      <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revisar Tarefa</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Feedback</Label>
            <Textarea
              value={reviewFeedback}
              onChange={(e) => setReviewFeedback(e.target.value)}
              placeholder="Escreva seu feedback sobre a resposta do paciente..."
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviewOpen(false)}>Cancelar</Button>
            <Button onClick={handleReview} disabled={!reviewFeedback.trim() || reviewHomework.isPending}>
              {reviewHomework.isPending ? 'Enviando...' : 'Enviar Feedback'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
