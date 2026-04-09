import { useState } from 'react';
import { Loader2, CheckSquare } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { formatDate } from '@/lib/utils';
import { useHomeworkList, useSubmitHomework } from '@/hooks/useHomework';

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  enviada: { label: 'Enviada', variant: 'default' },
  revisada: { label: 'Revisada', variant: 'secondary' },
  atrasada: { label: 'Atrasada', variant: 'destructive' },
};

export default function PatientHomework() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useHomeworkList(page);
  const submitHomework = useSubmitHomework();

  const [submitOpen, setSubmitOpen] = useState(false);
  const [submitTarget, setSubmitTarget] = useState<string | null>(null);
  const [resposta, setResposta] = useState('');

  const items = data?.data ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 10);

  function handleSubmit() {
    if (!submitTarget || !resposta.trim()) return;
    submitHomework.mutate({ id: submitTarget, resposta_paciente: resposta }, {
      onSuccess: () => {
        setSubmitOpen(false);
        setSubmitTarget(null);
        setResposta('');
      },
    });
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <CheckSquare className="h-6 w-6" /> Minhas Tarefas
        </h1>
        <p className="text-muted-foreground">Tarefas e atividades atribuidas pelo seu terapeuta</p>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <CheckSquare className="h-10 w-10 text-muted-foreground/30" />
            <p className="mt-3 text-sm text-muted-foreground">Nenhuma tarefa atribuida no momento</p>
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
                        <span>Recebida: {formatDate(hw.created_at)}</span>
                        {hw.data_limite && <span>Prazo: {formatDate(hw.data_limite)}</span>}
                      </div>
                      {hw.resposta_paciente && (
                        <div className="mt-2 bg-muted/50 p-3 rounded-md">
                          <p className="text-xs font-medium text-muted-foreground mb-1">Sua Resposta</p>
                          <p className="text-sm">{hw.resposta_paciente}</p>
                        </div>
                      )}
                      {hw.feedback_terapeuta && (
                        <div className="mt-2 bg-blue-50 p-3 rounded-md">
                          <p className="text-xs font-medium text-blue-600 mb-1">Feedback do Terapeuta</p>
                          <p className="text-sm">{hw.feedback_terapeuta}</p>
                        </div>
                      )}
                    </div>
                    {hw.status === 'pendente' && (
                      <Button
                        size="sm"
                        className="shrink-0"
                        onClick={() => {
                          setSubmitTarget(hw.id);
                          setResposta('');
                          setSubmitOpen(true);
                        }}
                      >
                        Responder
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

      {/* Submit Dialog */}
      <Dialog open={submitOpen} onOpenChange={setSubmitOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enviar Resposta</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm text-muted-foreground">Sua resposta</label>
            <Textarea
              value={resposta}
              onChange={(e) => setResposta(e.target.value)}
              placeholder="Escreva sua resposta para a tarefa..."
              rows={5}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSubmitOpen(false)}>Cancelar</Button>
            <Button onClick={handleSubmit} disabled={!resposta.trim() || submitHomework.isPending}>
              {submitHomework.isPending ? 'Enviando...' : 'Enviar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
