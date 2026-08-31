import { useState } from 'react';
import { Loader2, Smile, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import { Separator } from '@noctusai/seed/components/ui/separator';
import { formatDate } from '@/lib/utils';
import { useMoodEntries, useCreateMoodEntry, useMoodAnalytics } from '@/hooks/useMood';

const EMOCOES = [
  'Feliz', 'Triste', 'Ansioso', 'Calmo', 'Irritado', 'Motivado',
  'Cansado', 'Esperancoso', 'Frustrado', 'Grato', 'Solitario', 'Confiante',
];

export default function MoodTracker() {
  const [page, setPage] = useState(1);
  const { data: entriesData, isPending } = useMoodEntries({ page, page_size: 10 });
  const showSkeleton = isPending && !entriesData;
  const { data: analytics } = useMoodAnalytics();
  const createMood = useCreateMoodEntry();

  const [rating, setRating] = useState(5);
  const [selectedEmocoes, setSelectedEmocoes] = useState<string[]>([]);
  const [nota, setNota] = useState('');

  const entries = entriesData?.data ?? [];
  const total = entriesData?.total ?? 0;
  const totalPages = Math.ceil(total / 10);

  function toggleEmocao(emocao: string) {
    setSelectedEmocoes((prev) =>
      prev.includes(emocao) ? prev.filter((e) => e !== emocao) : [...prev, emocao]
    );
  }

  function handleSubmit() {
    createMood.mutate(
      {
        rating,
        emocoes: selectedEmocoes.length > 0 ? selectedEmocoes : undefined,
        nota: nota.trim() || undefined,
        data: new Date().toISOString().split('T')[0],
      },
      {
        onSuccess: () => {
          setRating(5);
          setSelectedEmocoes([]);
          setNota('');
        },
      }
    );
  }

  const tendenciaIcon = analytics?.tendencia === 'subindo'
    ? <TrendingUp className="h-4 w-4 text-green-500" />
    : analytics?.tendencia === 'descendo'
    ? <TrendingDown className="h-4 w-4 text-red-500" />
    : <Minus className="h-4 w-4 text-muted-foreground" />;

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Smile className="h-6 w-6" /> Registro de Humor
        </h1>
        <p className="text-muted-foreground">Acompanhe como voce esta se sentindo ao longo do tempo</p>
      </div>

      {/* Analytics Summary */}
      {analytics && (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Media</p>
              <p className="text-2xl font-bold">{analytics.media_rating.toFixed(1)} / 10</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Total de Registros</p>
              <p className="text-2xl font-bold">{analytics.total_registros}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Tendencia</p>
              <div className="flex items-center gap-2">
                {tendenciaIcon}
                <p className="text-2xl font-bold capitalize">{analytics.tendencia}</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* New Entry Form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Como voce esta hoje?</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Nivel de Humor: {rating}</Label>
            <input
              type="range"
              min="1"
              max="10"
              value={rating}
              onChange={(e) => setRating(Number(e.target.value))}
              className="w-full mt-2"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>1 - Muito mal</span>
              <span>5 - Neutro</span>
              <span>10 - Muito bem</span>
            </div>
          </div>

          <div>
            <Label>Emocoes</Label>
            <div className="flex flex-wrap gap-2 mt-2">
              {EMOCOES.map((emocao) => (
                <Badge
                  key={emocao}
                  variant={selectedEmocoes.includes(emocao) ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => toggleEmocao(emocao)}
                >
                  {emocao}
                </Badge>
              ))}
            </div>
          </div>

          <div>
            <Label>Nota (opcional)</Label>
            <Textarea
              value={nota}
              onChange={(e) => setNota(e.target.value)}
              placeholder="Como foi seu dia? O que esta sentindo?"
              rows={3}
            />
          </div>

          <Button onClick={handleSubmit} disabled={createMood.isPending}>
            {createMood.isPending ? 'Registrando...' : 'Registrar Humor'}
          </Button>
        </CardContent>
      </Card>

      <Separator />

      {/* History */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Historico</CardTitle>
        </CardHeader>
        <CardContent>
          {showSkeleton ? (
            <div className="flex h-32 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : entries.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum registro encontrado. Comece registrando como voce esta hoje!</p>
          ) : (
            <>
              <div className="space-y-3">
                {entries.map((entry) => (
                  <div key={entry.id} className="flex items-start gap-4 border-b last:border-0 pb-3 last:pb-0">
                    <div className="flex-shrink-0 w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                      <span className="text-lg font-bold">{entry.rating}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium">{formatDate(entry.data)}</span>
                        {entry.emocoes && entry.emocoes.map((e, i) => (
                          <Badge key={i} variant="secondary" className="text-xs">{e}</Badge>
                        ))}
                      </div>
                      {entry.nota && <p className="text-sm text-muted-foreground mt-1">{entry.nota}</p>}
                    </div>
                  </div>
                ))}
              </div>

              {totalPages > 1 && (
                <div className="flex justify-center gap-2 mt-4">
                  <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</Button>
                  <span className="text-sm text-muted-foreground flex items-center px-2">Pagina {page} de {totalPages}</span>
                  <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Proxima</Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
