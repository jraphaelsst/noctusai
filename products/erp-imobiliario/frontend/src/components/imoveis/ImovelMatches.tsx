import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Progress } from '@noctusai/seed/components/ui/progress';
import { useMatches, useAtualizarStatusMatch, Match } from '@/hooks/useMatches';
import { formatCurrency } from '@/lib/utils';
import { Sparkles, HomeIcon, ArrowLeftRight, Check, X } from 'lucide-react';

function getScoreColor(score: number) {
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  if (score >= 40) return 'text-orange-600';
  return 'text-red-600';
}

function getScoreLabel(score: number) {
  if (score >= 80) return 'Alta';
  if (score >= 60) return 'Boa';
  if (score >= 40) return 'Média';
  return 'Baixa';
}

interface ImovelMatchesProps {
  imovelId: string;
}

export function ImovelMatches({ imovelId }: ImovelMatchesProps) {
  const matchesQuery = useMatches({ ativo_origem_id: imovelId });
  const { data: matches = [] } = matchesQuery;
  const atualizarStatus = useAtualizarStatusMatch();

  if (matchesQuery.isPending && !matchesQuery.data) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Carregando matches...</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {matches.length === 0 ? (
        <Card className="p-8 text-center">
          <Sparkles className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
          <p className="text-muted-foreground">Nenhum match encontrado</p>
          <p className="text-sm text-muted-foreground mt-1">
            Matches são gerados automaticamente ao criar ou atualizar ativos
          </p>
        </Card>
      ) : (
        matches.map((match) => (
          <MatchCard
            key={match.id}
            match={match}
            onAccept={() => atualizarStatus.mutate({ matchId: match.id, status: 'aceito' })}
            onReject={() => atualizarStatus.mutate({ matchId: match.id, status: 'rejeitado' })}
            isUpdating={atualizarStatus.isPending}
          />
        ))
      )}
    </div>
  );
}

function MatchCard({
  match,
  onAccept,
  onReject,
  isUpdating,
}: {
  match: Match;
  onAccept: () => void;
  onReject: () => void;
  isUpdating: boolean;
}) {
  const statusBadge: Record<string, { label: string; className: string }> = {
    pendente: { label: 'Pendente', className: 'bg-yellow-100 text-yellow-800' },
    aceito: { label: 'Aceito', className: 'bg-green-100 text-green-800' },
    rejeitado: { label: 'Rejeitado', className: 'bg-red-100 text-red-800' },
    expirado: { label: 'Expirado', className: 'bg-gray-100 text-gray-800' },
  };

  const config = statusBadge[match.status] || statusBadge.pendente;

  return (
    <Card className="p-4 sm:p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <HomeIcon className="h-4 w-4 text-primary" />
            <span className="font-medium">
              {match.ativo_origem?.tipo_imovel || 'Origem'}
            </span>
            <ArrowLeftRight className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">
              {match.ativo_destino?.tipo_imovel || 'Destino'}
            </span>
            <Badge variant="outline" className={config.className}>
              {config.label}
            </Badge>
          </div>
          {match.justificativa && (
            <p className="text-sm text-muted-foreground">{match.justificativa}</p>
          )}
        </div>
        <div className="text-right ml-4">
          <div className={`text-2xl font-bold ${getScoreColor(match.score)}`}>
            {match.score}%
          </div>
          <Badge variant="outline">{getScoreLabel(match.score)}</Badge>
        </div>
      </div>

      {/* Score breakdown */}
      {match.score_breakdown && (
      <div className="space-y-2 mb-4">
        {match.score_breakdown.embedding_similarity > 0 && (
          <>
            <div className="flex justify-between text-sm">
              <span>Similaridade IA</span>
              <span className="font-medium">{Math.round(match.score_breakdown.embedding_similarity)}%</span>
            </div>
            <Progress value={match.score_breakdown.embedding_similarity} className="h-2" />
          </>
        )}
        <div className="flex justify-between text-sm">
          <span>Região</span>
          <span className="font-medium">{Math.round(match.score_breakdown.compatibilidade_regiao)}%</span>
        </div>
        <Progress value={match.score_breakdown.compatibilidade_regiao} className="h-2" />

        <div className="flex justify-between text-sm">
          <span>Preço</span>
          <span className="font-medium">{Math.round(match.score_breakdown.compatibilidade_preco)}%</span>
        </div>
        <Progress value={match.score_breakdown.compatibilidade_preco} className="h-2" />

        <div className="flex justify-between text-sm">
          <span>Especificações</span>
          <span className="font-medium">{Math.round(match.score_breakdown.compatibilidade_specs)}%</span>
        </div>
        <Progress value={match.score_breakdown.compatibilidade_specs} className="h-2" />

        <div className="flex justify-between text-sm">
          <span>Qualidade</span>
          <span className="font-medium">{Math.round(match.score_breakdown.qualidade_anuncio)}%</span>
        </div>
        <Progress value={match.score_breakdown.qualidade_anuncio} className="h-2" />
      </div>
      )}

      {/* Values + actions */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 pt-4 border-t">
        <div className="text-sm">
          <div>Origem: {formatCurrency(match.ativo_origem?.valor || 0)}</div>
          <div>Destino: {formatCurrency(match.ativo_destino?.valor || 0)}</div>
          {match.detalhes.gap_valor > 0 && (
            <div className="font-medium text-orange-600">
              Gap: {formatCurrency(match.detalhes.gap_valor)}
            </div>
          )}
        </div>

        {match.status === 'pendente' && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onReject}
              disabled={isUpdating}
            >
              <X className="w-4 h-4 mr-1" />
              Rejeitar
            </Button>
            <Button
              size="sm"
              onClick={onAccept}
              disabled={isUpdating}
            >
              <Check className="w-4 h-4 mr-1" />
              Aceitar
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}
