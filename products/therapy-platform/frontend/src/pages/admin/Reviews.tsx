import { Star, Flag, Eye, EyeOff } from 'lucide-react';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { useAdminReviews, useDismissReviewFlag, useHideReview } from '@/hooks/useAdmin';

interface FlaggedReview {
  id: string;
  nota: number;
  comentario: string;
  patient_name: string;
  entity_name: string;
  entity_type: 'therapist' | 'clinic';
  flag_reason: string;
  created_at: string;
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          className={`h-4 w-4 ${i < rating ? 'text-yellow-500 fill-yellow-500' : 'text-muted-foreground/30'}`}
        />
      ))}
    </div>
  );
}

export default function AdminReviews() {
  const { data, isLoading } = useAdminReviews();
  const dismissFlag = useDismissReviewFlag();
  const hideReview = useHideReview();

  const reviews = (data?.data ?? []) as FlaggedReview[];

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Flag className="h-6 w-6" /> Moderacao de Avaliacoes
        </h1>
        <p className="text-muted-foreground">Avaliacoes sinalizadas para revisao</p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-4 h-32" />
            </Card>
          ))}
        </div>
      ) : reviews.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <Star className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-lg font-medium text-muted-foreground">
              Nenhuma avaliacao sinalizada
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {reviews.map(r => (
            <Card key={r.id}>
              <CardContent className="p-5">
                <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                  <div className="flex-1 space-y-3">
                    <div className="flex items-center gap-3 flex-wrap">
                      <StarRating rating={r.nota} />
                      <Badge variant={r.entity_type === 'therapist' ? 'default' : 'secondary'}>
                        {r.entity_type === 'therapist' ? 'Terapeuta' : 'Clinica'}
                      </Badge>
                    </div>

                    <p className="text-sm">{r.comentario}</p>

                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>Paciente: {r.patient_name}</span>
                      <span>
                        {r.entity_type === 'therapist' ? 'Terapeuta' : 'Clinica'}: {r.entity_name}
                      </span>
                      <span>{new Date(r.created_at).toLocaleDateString('pt-BR')}</span>
                    </div>

                    <div className="flex items-center gap-2 bg-destructive/10 p-2 rounded-md">
                      <Flag className="h-3.5 w-3.5 text-destructive shrink-0" />
                      <p className="text-sm text-destructive">
                        <span className="font-medium">Motivo da flag:</span> {r.flag_reason}
                      </p>
                    </div>
                  </div>

                  <div className="flex sm:flex-col gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => dismissFlag.mutate(r.id)}
                      disabled={dismissFlag.isPending}
                    >
                      <Eye className="h-3.5 w-3.5 mr-1" /> Manter
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => hideReview.mutate(r.id)}
                      disabled={hideReview.isPending}
                    >
                      <EyeOff className="h-3.5 w-3.5 mr-1" /> Ocultar
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
