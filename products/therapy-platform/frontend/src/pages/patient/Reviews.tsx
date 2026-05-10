import { useState } from 'react';
import { Star, Pencil, Trash2, Plus } from 'lucide-react';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { Input } from '@noctusai/seed/components/ui/input';
import {
  usePatientReviews,
  useDeleteReview,
  useUpdateReview,
  type PatientReview,
} from '@/hooks/usePatientReviews';

function StarRating({ rating, size = 'md' }: { rating: number; size?: 'sm' | 'md' }) {
  const cls = size === 'sm' ? 'h-3.5 w-3.5' : 'h-5 w-5';
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          className={`${cls} ${i < rating ? 'text-yellow-500 fill-yellow-500' : 'text-muted-foreground/30'}`}
        />
      ))}
    </div>
  );
}

function InteractiveStars({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: 5 }).map((_, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onChange(i + 1)}
          className="focus:outline-none"
        >
          <Star
            className={`h-7 w-7 transition-colors ${i < value ? 'text-yellow-500 fill-yellow-500' : 'text-muted-foreground/30 hover:text-yellow-300'}`}
          />
        </button>
      ))}
    </div>
  );
}

export default function PatientReviews() {
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<PatientReview | null>(null);
  const [editNota, setEditNota] = useState(5);
  const [editComentario, setEditComentario] = useState('');

  const { data, isLoading } = usePatientReviews();
  const deleteReview = useDeleteReview();
  const updateReview = useUpdateReview(() => setEditDialogOpen(false));

  const reviews = data?.data ?? [];
  const pending = data?.pending ?? [];

  const openEdit = (review: PatientReview) => {
    setEditTarget(review);
    setEditNota(review.nota);
    setEditComentario(review.comentario ?? '');
    setEditDialogOpen(true);
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Minhas Avaliacoes</h1>
        <p className="text-muted-foreground">Avaliacoes que voce deixou para terapeutas e clinicas</p>
      </div>

      {/* Pending reviews CTA */}
      {pending.length > 0 && (
        <Card className="border-primary/50 bg-primary/5">
          <CardContent className="p-5">
            <div className="flex items-center gap-3">
              <Plus className="h-5 w-5 text-primary" />
              <div className="flex-1">
                <p className="font-medium text-sm">
                  Voce tem {pending.length} {pending.length === 1 ? 'sessao' : 'sessoes'} sem avaliacao
                </p>
                <p className="text-xs text-muted-foreground">
                  Avalie suas sessoes recentes para ajudar outros pacientes.
                </p>
              </div>
              <Button size="sm">Avaliar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-5 h-28" />
            </Card>
          ))}
        </div>
      ) : reviews.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <Star className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-lg font-medium text-muted-foreground">
              Nenhuma avaliacao deixada
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Apos completar sessoes, voce podera avaliar seus terapeutas.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {reviews.map(r => (
            <Card key={r.id}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-3">
                      <StarRating rating={r.nota} size="sm" />
                      <Badge variant={r.entity_type === 'therapist' ? 'default' : 'secondary'}>
                        {r.entity_type === 'therapist' ? 'Terapeuta' : 'Clinica'}
                      </Badge>
                    </div>
                    <p className="font-medium text-sm">{r.entity_name}</p>
                    {r.comentario && (
                      <p className="text-sm text-muted-foreground">{r.comentario}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {new Date(r.created_at).toLocaleDateString('pt-BR')}
                    </p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openEdit(r)}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteReview.mutate(r.id)}
                      disabled={deleteReview.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Edit dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar Avaliacao</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Nota</label>
              <InteractiveStars value={editNota} onChange={setEditNota} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Comentario</label>
              <Input
                value={editComentario}
                onChange={e => setEditComentario(e.target.value)}
                placeholder="Seu comentario..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>Cancelar</Button>
            <Button
              onClick={() => editTarget && updateReview.mutate({
                id: editTarget.id,
                nota: editNota,
                comentario: editComentario,
              })}
              disabled={updateReview.isPending}
            >
              Salvar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
