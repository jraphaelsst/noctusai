import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { useMatches, useRecalcularMatches, useAtualizarStatusMatch } from '@/hooks/useMatches';
import { RefreshCcw, CheckCircle, XCircle } from 'lucide-react';
import { formatCurrency } from '@/lib/utils';

interface PermutaMatchesProps {
  perfilId: string;
}

export function PermutaMatches({ perfilId }: PermutaMatchesProps) {
  const { data: matches = [], isLoading } = useMatches({ ativo_destino_id: perfilId });
  const recalcularMutation = useRecalcularMatches();
  const atualizarMutation = useAtualizarStatusMatch();

  if (isLoading) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Carregando matches...</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          Matches ({matches.length})
        </h3>
        <Button
          variant="outline"
          onClick={() => recalcularMutation.mutateAsync({ ativo_destino_id: perfilId })}
          disabled={recalcularMutation.isPending}
        >
          <RefreshCcw className={`w-4 h-4 mr-2 ${recalcularMutation.isPending ? 'animate-spin' : ''}`} />
          Recalcular
        </Button>
      </div>

      {matches.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-muted-foreground">Nenhum match encontrado. Tente recalcular.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {matches.map((match) => {
            const scoreColor = match.score >= 80 ? 'text-green-600' : match.score >= 60 ? 'text-yellow-600' : match.score >= 40 ? 'text-orange-600' : 'text-red-600';
            const borderColor = match.score >= 60 ? '#22c55e' : match.score >= 40 ? '#f59e0b' : '#ef4444';
            const origem = match.ativo_origem;

            const statusBadge = match.status === 'aceito'
              ? <Badge className="bg-green-100 text-green-800">Aceito</Badge>
              : match.status === 'rejeitado'
                ? <Badge className="bg-red-100 text-red-800">Rejeitado</Badge>
                : <Badge variant="outline">Pendente</Badge>;

            return (
              <Card key={match.id} className="border-l-4" style={{ borderLeftColor: borderColor }}>
                <CardContent className="pt-4 pb-4">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium capitalize">
                          {origem?.tipo_imovel || origem?.tipo_veiculo || 'Ativo'}
                        </span>
                        {origem?.cidade && (
                          <span className="text-sm text-muted-foreground">
                            — {origem.cidade}{origem.estado ? `, ${origem.estado}` : ''}
                          </span>
                        )}
                        {statusBadge}
                      </div>
                      {match.justificativa && (
                        <p className="text-sm text-muted-foreground">{match.justificativa}</p>
                      )}
                    </div>
                    <div className="text-right ml-4">
                      <div className={`text-2xl font-bold ${scoreColor}`}>{match.score}%</div>
                    </div>
                  </div>

                  {match.detalhes && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                      {[
                        { label: 'Região', val: match.detalhes.compatibilidade_regiao || 0, max: 30 },
                        { label: 'Preço', val: match.detalhes.compatibilidade_preco || 0, max: 25 },
                        { label: 'Specs', val: match.detalhes.compatibilidade_specs || 0, max: 20 },
                        { label: 'Qualidade', val: match.detalhes.qualidade_anuncio || 0, max: 10 },
                      ].map(({ label, val, max }) => (
                        <div key={label}>
                          <div className="flex justify-between text-xs">
                            <span>{label}</span>
                            <span>{val}/{max}</span>
                          </div>
                          <Progress value={val / max * 100} className="h-1.5" />
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-3 border-t">
                    <div className="text-sm">
                      {origem && <span>Valor: <strong>{formatCurrency(origem.valor || 0)}</strong></span>}
                    </div>
                    {match.status === 'pendente' && (
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-red-600"
                          disabled={atualizarMutation.isPending}
                          onClick={() => atualizarMutation.mutateAsync({ matchId: match.id, status: 'rejeitado' })}
                        >
                          <XCircle className="h-4 w-4 mr-1" />
                          Rejeitar
                        </Button>
                        <Button
                          size="sm"
                          className="bg-green-600 hover:bg-green-700"
                          disabled={atualizarMutation.isPending}
                          onClick={() => atualizarMutation.mutateAsync({ matchId: match.id, status: 'aceito' })}
                        >
                          <CheckCircle className="h-4 w-4 mr-1" />
                          Aceitar
                        </Button>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
