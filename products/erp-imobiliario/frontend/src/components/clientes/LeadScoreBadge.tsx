import { useEffect, useRef } from 'react';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@noctusai/seed/components/ui/popover';
import { useLeadScore } from '@/hooks/useAI';
import { Cliente } from '@/types/clientes';
import { Brain, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';

interface LeadScoreBadgeProps {
  cliente: Cliente;
}

function getScoreConfig(score: number) {
  if (score >= 80) return { label: 'Quente', color: 'bg-green-100 text-green-800 border-green-300' };
  if (score >= 60) return { label: 'Morno', color: 'bg-yellow-100 text-yellow-800 border-yellow-300' };
  if (score >= 40) return { label: 'Frio', color: 'bg-orange-100 text-orange-800 border-orange-300' };
  return { label: 'Gelado', color: 'bg-red-100 text-red-800 border-red-300' };
}

export function LeadScoreBadge({ cliente }: LeadScoreBadgeProps) {
  const { mutate: scoreLeadMutate, isPending, isError } = useLeadScore();
  const hasFired = useRef(false);

  // Auto-trigger scoring when no stored score exists
  useEffect(() => {
    if (cliente.lead_score == null && !hasFired.current && !isPending) {
      hasFired.current = true;
      scoreLeadMutate({ cliente_id: cliente.id });
    }
  }, [cliente.id, cliente.lead_score, isPending, scoreLeadMutate]);

  // Reset guard when cliente changes
  useEffect(() => {
    hasFired.current = false;
  }, [cliente.id]);

  const isStale =
    cliente.lead_score != null &&
    cliente.lead_score_updated_at &&
    cliente.updated_at > cliente.lead_score_updated_at;

  const handleRecalculate = () => {
    scoreLeadMutate({ cliente_id: cliente.id });
  };

  // Loading state
  if (isPending) {
    return (
      <Badge variant="outline" className="gap-1 animate-pulse">
        <Loader2 className="w-3 h-3 animate-spin" />
        Analisando...
      </Badge>
    );
  }

  // Error state (e.g. OpenAI not configured)
  if (isError && cliente.lead_score == null) {
    return (
      <Badge variant="outline" className="gap-1 text-muted-foreground">
        <AlertTriangle className="w-3 h-3" />
        IA indisponivel
      </Badge>
    );
  }

  // No score yet and not loading/errored — nothing to show
  if (cliente.lead_score == null) {
    return null;
  }

  const config = getScoreConfig(cliente.lead_score);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Badge
          variant="outline"
          className={`gap-1 cursor-pointer ${config.color} ${isStale ? 'ring-1 ring-yellow-400' : ''}`}
        >
          <Brain className="w-3 h-3" />
          {cliente.lead_score} — {config.label}
          {isStale && <AlertTriangle className="w-3 h-3 ml-0.5" />}
        </Badge>
      </PopoverTrigger>
      <PopoverContent className="w-80">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="font-semibold text-sm">Lead Score IA</h4>
            <span className={`text-2xl font-bold ${config.color} px-2 py-0.5 rounded`}>
              {cliente.lead_score}
            </span>
          </div>

          {cliente.lead_score_justificativa && (
            <p className="text-sm text-muted-foreground">
              {cliente.lead_score_justificativa}
            </p>
          )}

          {cliente.lead_score_updated_at && (
            <p className="text-xs text-muted-foreground">
              Calculado{' '}
              {formatDistanceToNow(new Date(cliente.lead_score_updated_at), {
                addSuffix: true,
                locale: ptBR,
              })}
            </p>
          )}

          {isStale && (
            <p className="text-xs text-yellow-600 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Dados do cliente foram alterados desde o ultimo calculo
            </p>
          )}

          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={handleRecalculate}
            disabled={isPending}
          >
            <RefreshCw className={`w-3 h-3 mr-2 ${isPending ? 'animate-spin' : ''}`} />
            Recalcular
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
