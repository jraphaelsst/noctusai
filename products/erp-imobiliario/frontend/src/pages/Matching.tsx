import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { formatCurrency } from '@/lib/utils';
import {
  useMatches,
  useRecalcularMatches,
  useAtualizarStatusMatch,
  useEmbedBatch,
  Match,
} from '@/hooks/useMatches';
import { ArrowLeftRight, Sparkles, RefreshCw, CheckCircle, XCircle } from 'lucide-react';

function Matching() {
  const [origemFilter, setOrigemFilter] = useState('');
  const [destinoFilter, setDestinoFilter] = useState('');
  const [minScore, setMinScore] = useState([0]);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [gerarAtivoId, setGerarAtivoId] = useState('');

  const { data: matches = [], isLoading } = useMatches({
    ativo_origem_id: origemFilter || undefined,
    ativo_destino_id: destinoFilter || undefined,
    min_score: minScore[0] > 0 ? minScore[0] : undefined,
  });

  const recalcularMutation = useRecalcularMatches();
  const statusMutation = useAtualizarStatusMatch();
  const embedBatchMutation = useEmbedBatch();

  const filteredMatches = statusFilter === 'all'
    ? matches
    : matches.filter(m => m.status === statusFilter);

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

  const handleGerar = () => {
    recalcularMutation.mutate({
      ativo_origem_id: gerarAtivoId || undefined,
    });
  };

  const handleEmbedBatch = () => {
    embedBatchMutation.mutate([]);
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Matching de Ativos</h1>
          <p className="text-muted-foreground">
            {filteredMatches.length} match{filteredMatches.length !== 1 ? 'es' : ''} encontrado{filteredMatches.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleEmbedBatch}
            disabled={embedBatchMutation.isPending}
          >
            <Sparkles className="h-4 w-4 mr-2" />
            {embedBatchMutation.isPending ? 'Embedando...' : 'Embed Batch'}
          </Button>
          <Button onClick={handleGerar} disabled={recalcularMutation.isPending}>
            <RefreshCw className={`h-4 w-4 mr-2 ${recalcularMutation.isPending ? 'animate-spin' : ''}`} />
            {recalcularMutation.isPending ? 'Gerando...' : 'Gerar Matches'}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="text-sm font-medium mb-1 block">Ativo Origem ID</label>
              <Input
                placeholder="Filtrar por origem..."
                value={origemFilter}
                onChange={e => setOrigemFilter(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Gerar para Ativo ID</label>
              <Input
                placeholder="ID do ativo para gerar matches..."
                value={gerarAtivoId}
                onChange={e => setGerarAtivoId(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Status</label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
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
            <div>
              <label className="text-sm font-medium mb-1 block">
                Score mínimo: {minScore[0]}%
              </label>
              <Slider
                value={minScore}
                onValueChange={setMinScore}
                min={0}
                max={100}
                step={5}
                className="mt-3"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {isLoading ? (
        <div className="text-center py-12 text-muted-foreground">Carregando matches...</div>
      ) : filteredMatches.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            Nenhum match encontrado. Use "Gerar Matches" para iniciar.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredMatches.map((match: Match) => (
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
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                  {match.score_breakdown?.embedding_similarity != null && (
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
                      <span>Preço</span>
                      <span>{Math.round(match.detalhes.compatibilidade_preco)}%</span>
                    </div>
                    <Progress value={match.detalhes.compatibilidade_preco} className="h-1.5" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span>Região</span>
                      <span>{Math.round(match.detalhes.compatibilidade_regiao)}%</span>
                    </div>
                    <Progress value={match.detalhes.compatibilidade_regiao} className="h-1.5" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span>Specs</span>
                      <span>{Math.round(match.detalhes.compatibilidade_specs)}%</span>
                    </div>
                    <Progress value={match.detalhes.compatibilidade_specs} className="h-1.5" />
                  </div>
                </div>

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
