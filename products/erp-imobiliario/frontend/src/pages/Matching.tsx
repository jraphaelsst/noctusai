import { useState } from 'react';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Progress } from '@noctusai/seed/components/ui/progress';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@noctusai/seed/components/ui/select';
import { formatCurrency } from '@/lib/utils';
import {
  useMatches,
  useRecalcularMatches,
  useAtualizarStatusMatch,
  useEmbedBatch,
  Match,
} from '@/hooks/useMatches';
import { ArrowLeftRight, Sparkles, RefreshCw, CheckCircle, XCircle } from 'lucide-react';
import { CardListSkeleton } from '@/components/ui/page-skeleton';

function Matching() {
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const { data: matches = [], isLoading } = useMatches({
    status: statusFilter !== 'all' ? statusFilter : undefined,
  });

  const recalcularMutation = useRecalcularMatches();
  const statusMutation = useAtualizarStatusMatch();
  const embedBatchMutation = useEmbedBatch();

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    if (score >= 40) return 'text-orange-600';
    return 'text-red-600';
  };

  const getStatusVariant = (status: string): 'default' | 'secondary' | 'destructive' | 'outline' => {
    switch (status) {
      case 'aceito': return 'default';
      case 'rejeitado': return 'destructive';
      case 'expirado': return 'secondary';
      default: return 'outline';
    }
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Matching de Ativos</h1>
          <p className="text-muted-foreground">
            {matches.length} match{matches.length !== 1 ? 'es' : ''} encontrado{matches.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => embedBatchMutation.mutate()}
            disabled={embedBatchMutation.isPending}
          >
            <Sparkles className="h-4 w-4 mr-2" />
            {embedBatchMutation.isPending ? 'Embedando...' : 'Embed Batch'}
          </Button>
          <Button
            onClick={() => recalcularMutation.mutate()}
            disabled={recalcularMutation.isPending}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${recalcularMutation.isPending ? 'animate-spin' : ''}`} />
            {recalcularMutation.isPending ? 'Recalculando...' : 'Recalcular Tudo'}
          </Button>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium">Status:</label>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            <SelectItem value="pendente">Pendente</SelectItem>
            <SelectItem value="aceito">Aceito</SelectItem>
            <SelectItem value="rejeitado">Rejeitado</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Results */}
      {isLoading ? (
        <CardListSkeleton count={4} />
      ) : matches.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            Nenhum match encontrado. Os matches são gerados automaticamente ao criar ou atualizar ativos.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {matches.map((match: Match) => (
            <Card key={match.id}>
              <CardContent className="pt-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-medium text-sm">
                        {match.ativo_origem?.titulo_anuncio || match.ativo_origem?.tipo_imovel || match.ativo_origem_id?.slice(0, 8)}
                      </span>
                      <ArrowLeftRight className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium text-sm">
                        {match.ativo_destino?.titulo_anuncio || match.ativo_destino?.tipo_imovel || match.ativo_destino_id?.slice(0, 8)}
                      </span>
                    </div>
                    {match.justificativa && (
                      <p className="text-sm text-muted-foreground">{match.justificativa}</p>
                    )}
                  </div>
                  <div className="text-right flex items-center gap-3">
                    <Badge variant={getStatusVariant(match.status)}>{match.status}</Badge>
                    <div className={`text-2xl font-bold ${getScoreColor(match.score)}`}>
                      {typeof match.score === 'number' ? match.score.toFixed(1) : match.score}%
                    </div>
                  </div>
                </div>

                {/* Score breakdown bars */}
                {match.score_breakdown && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                  {match.score_breakdown.embedding_similarity > 0 && (
                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <span>Similaridade IA</span>
                        <span>{Math.round(match.score_breakdown.embedding_similarity)}%</span>
                      </div>
                      <Progress value={match.score_breakdown.embedding_similarity} className="h-1.5" />
                    </div>
                  )}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span>Região</span>
                      <span>{Math.round(match.score_breakdown.compatibilidade_regiao)}%</span>
                    </div>
                    <Progress value={match.score_breakdown.compatibilidade_regiao} className="h-1.5" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span>Preço</span>
                      <span>{Math.round(match.score_breakdown.compatibilidade_preco)}%</span>
                    </div>
                    <Progress value={match.score_breakdown.compatibilidade_preco} className="h-1.5" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span>Specs</span>
                      <span>{Math.round(match.score_breakdown.compatibilidade_specs)}%</span>
                    </div>
                    <Progress value={match.score_breakdown.compatibilidade_specs} className="h-1.5" />
                  </div>
                </div>
                )}

                {/* Actions */}
                <div className="flex justify-between items-center pt-3 border-t">
                  <div className="text-sm text-muted-foreground">
                    {match.ativo_origem?.valor && (
                      <span>Origem: {formatCurrency(match.ativo_origem.valor)}</span>
                    )}
                    {match.ativo_destino?.valor && (
                      <span className="ml-4">Destino: {formatCurrency(match.ativo_destino.valor)}</span>
                    )}
                  </div>
                  {match.status === 'pendente' && (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-green-600 border-green-200 hover:bg-green-50"
                        onClick={() => statusMutation.mutate({ matchId: match.id, status: 'aceito' })}
                        disabled={statusMutation.isPending}
                      >
                        <CheckCircle className="h-4 w-4 mr-1" />
                        Aceitar
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-red-600 border-red-200 hover:bg-red-50"
                        onClick={() => statusMutation.mutate({ matchId: match.id, status: 'rejeitado' })}
                        disabled={statusMutation.isPending}
                      >
                        <XCircle className="h-4 w-4 mr-1" />
                        Rejeitar
                      </Button>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default Matching;
