import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Progress } from '@noctusai/seed/components/ui/progress';
import { CheckCircle, XCircle } from 'lucide-react';
import { formatCurrency } from '@/lib/utils';
import type { Match } from '@/hooks/useMatches';

function getScoreColor(score: number) {
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  if (score >= 40) return 'text-orange-600';
  return 'text-red-600';
}

function getBorderColor(score: number) {
  if (score >= 60) return '#22c55e';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
}

interface MatchCardProps {
  match: Match;
  onAtualizarStatus?: (id: string, status: 'aceito' | 'rejeitado') => Promise<unknown>;
  isUpdating?: boolean;
}

export function MatchCard({ match, onAtualizarStatus, isUpdating }: MatchCardProps) {
  const scoreColor = getScoreColor(match.score);
  const borderColor = getBorderColor(match.score);
  const origem = match.ativo_origem;
  const destino = match.ativo_destino;

  const statusBadge = match.status === 'aceito'
    ? <Badge className="bg-green-100 text-green-800">Aceito</Badge>
    : match.status === 'rejeitado'
      ? <Badge className="bg-red-100 text-red-800">Rejeitado</Badge>
      : <Badge variant="outline">Pendente</Badge>;

  // Use score_breakdown (percentage-based) or detalhes (point-based)
  const breakdown = match.score_breakdown
    ? [
        { label: 'Região', val: match.score_breakdown.compatibilidade_regiao, pct: true },
        { label: 'Preço', val: match.score_breakdown.compatibilidade_preco, pct: true },
        { label: 'Specs', val: match.score_breakdown.compatibilidade_specs, pct: true },
        { label: 'Qualidade', val: match.score_breakdown.qualidade_anuncio, pct: true },
      ]
    : match.detalhes
      ? [
          { label: 'Região', val: match.detalhes.compatibilidade_regiao || 0, max: 30 },
          { label: 'Preço', val: match.detalhes.compatibilidade_preco || 0, max: 25 },
          { label: 'Specs', val: match.detalhes.compatibilidade_specs || 0, max: 20 },
          { label: 'Qualidade', val: match.detalhes.qualidade_anuncio || 0, max: 10 },
        ]
      : null;

  return (
    <Card className="border-l-4" style={{ borderLeftColor: borderColor }}>
      <CardContent className="pt-4 pb-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-medium capitalize">
                {(origem?.tipo_imovel as string) || (origem?.tipo_veiculo as string) || 'Ativo'}
              </span>
              {origem?.cidade && (
                <span className="text-sm text-muted-foreground">
                  — {origem.cidade as string}{origem.estado ? `, ${origem.estado as string}` : ''}
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

        {breakdown && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            {breakdown.map(({ label, val, ...rest }) => {
              const pctValue = 'pct' in rest ? val : (val / (rest as { max: number }).max) * 100;
              const displayValue = 'pct' in rest ? `${Math.round(val)}%` : `${val}/${(rest as { max: number }).max}`;
              return (
                <div key={label}>
                  <div className="flex justify-between text-xs">
                    <span>{label}</span>
                    <span>{displayValue}</span>
                  </div>
                  <Progress value={pctValue} className="h-1.5" />
                </div>
              );
            })}
          </div>
        )}

        <div className="flex items-center justify-between pt-3 border-t">
          <div className="text-sm space-x-4">
            {origem && <span>Origem: <strong>{formatCurrency((origem.valor as number) || 0)}</strong></span>}
            {destino && <span>Destino: <strong>{formatCurrency((destino.valor as number) || 0)}</strong></span>}
          </div>
          {match.status === 'pendente' && onAtualizarStatus && (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" className="text-red-600" disabled={isUpdating}
                onClick={() => onAtualizarStatus(match.id, 'rejeitado')}>
                <XCircle className="h-4 w-4 mr-1" />Rejeitar
              </Button>
              <Button size="sm" className="bg-green-600 hover:bg-green-700" disabled={isUpdating}
                onClick={() => onAtualizarStatus(match.id, 'aceito')}>
                <CheckCircle className="h-4 w-4 mr-1" />Aceitar
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
