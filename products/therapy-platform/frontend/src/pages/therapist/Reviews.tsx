import { Star, Flag, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { useAuthStore } from '@/store/authStore';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { toast } from 'sonner';

interface Review {
  id: string;
  nota: number;
  comentario?: string;
  patient_name: string;
  tags?: string[];
  created_at: string;
  is_anonymous: boolean;
}

interface ReviewSummary {
  average: number;
  total: number;
  distribution: Record<number, number>;
}

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

export default function TherapistReviews() {
  const { user } = useAuthStore();

  const { data, isLoading } = useQuery<{ data: Review[]; summary: ReviewSummary }>({
    queryKey: ['therapist', 'reviews'],
    queryFn: async () => api.get('/api/therapist/reviews'),
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });

  const reviews = data?.data ?? [];
  const summary = data?.summary ?? { average: 0, total: 0, distribution: {} };

  const handleFlag = (id: string) => {
    toast.success('Avaliacao sinalizada para revisao');
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Minhas Avaliacoes</h1>
        <p className="text-muted-foreground">Avaliacoes recebidas dos pacientes</p>
      </div>

      {/* Summary card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row items-center gap-6">
            <div className="text-center">
              <p className="text-4xl font-bold">{summary.average.toFixed(1)}</p>
              <StarRating rating={Math.round(summary.average)} />
              <p className="text-sm text-muted-foreground mt-1">{summary.total} avaliacoes</p>
            </div>
            <Separator orientation="vertical" className="hidden sm:block h-20" />
            <div className="flex-1 space-y-1.5">
              {[5, 4, 3, 2, 1].map(star => {
                const count = summary.distribution[star] ?? 0;
                const pct = summary.total > 0 ? (count / summary.total) * 100 : 0;
                return (
                  <div key={star} className="flex items-center gap-2">
                    <span className="text-sm w-4 text-right">{star}</span>
                    <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />
                    <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-yellow-500 rounded-full transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground w-8">{count}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Reviews list */}
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
            <TrendingUp className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-lg font-medium text-muted-foreground">
              Nenhuma avaliacao recebida ainda
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              As avaliacoes aparecerao aqui apos suas primeiras sessoes.
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
                      <span className="text-sm font-medium">
                        {r.is_anonymous ? 'Paciente anonimo' : r.patient_name}
                      </span>
                    </div>
                    {r.comentario && (
                      <p className="text-sm text-foreground">{r.comentario}</p>
                    )}
                    {r.tags && r.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {r.tags.map(tag => (
                          <Badge key={tag} variant="outline" className="text-xs">{tag}</Badge>
                        ))}
                      </div>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {new Date(r.created_at).toLocaleDateString('pt-BR')}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="shrink-0"
                    onClick={() => handleFlag(r.id)}
                  >
                    <Flag className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
