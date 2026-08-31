import { Card } from '@noctusai/seed/components/ui/card';
import { useMatches, useAtualizarStatusMatch } from '@/hooks/useMatches';
import { MatchCard } from '@/components/shared/MatchCard';

interface PermutaMatchesProps {
  perfilId: string;
}

export function PermutaMatches({ perfilId }: PermutaMatchesProps) {
  const matchesQuery = useMatches({ ativo_destino_id: perfilId });
  const { data: matches = [] } = matchesQuery;
  const atualizarMutation = useAtualizarStatusMatch();

  if (matchesQuery.isPending && !matchesQuery.data) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Carregando matches...</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">
        Matches ({matches.length})
      </h3>

      {matches.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-muted-foreground">Nenhum match encontrado. Matches são gerados automaticamente.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {matches.map((match) => (
            <MatchCard
              key={match.id}
              match={match}
              onAtualizarStatus={(id, st) => atualizarMutation.mutateAsync({ matchId: id, status: st })}
              isUpdating={atualizarMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}
