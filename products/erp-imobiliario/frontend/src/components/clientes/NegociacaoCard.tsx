import { NegociacaoVenda } from '@/types/negociacoes';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { ExternalLink, MessageSquare, Archive, CheckCircle2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { formatCurrency } from '@/lib/utils';

interface NegociacaoCardProps {
  negociacao: NegociacaoVenda;
  onRegistrarAtividade?: (clienteId: string) => void;
  onArquivar?: (negociacaoId: string) => void;
  onAceitarProposta?: (negociacaoId: string) => void;
  aceitandoProposta?: boolean;
  isDragging?: boolean;
}

// Replaces the former `ClienteCard` (roadmap P1.5.4): the Funil's cards are
// NEGOCIAÇÕES now, because one cliente can hold several concurrent deals and a
// cliente-shaped card could only ever show one of them.
//
// Drag-and-drop wiring (ref/attributes/listeners/transform) is owned by the
// `KanbanCard` organ wrapper (`@noctusai/lib/components`) that renders this
// component via `renderCard`. `isDragging` here is only the DragOverlay
// ghost-copy flag the organ passes.
export function NegociacaoCard({
  negociacao,
  onRegistrarAtividade,
  onArquivar,
  onAceitarProposta,
  aceitandoProposta,
  isDragging,
}: NegociacaoCardProps) {
  const navigate = useNavigate();

  const style = {
    opacity: isDragging ? 0.5 : 1,
  };

  const cliente = negociacao.cliente;
  const nomeCliente = cliente?.nome ?? 'Cliente sem nome';

  const iniciais = nomeCliente
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  const tempoRelativo = negociacao.updated_at
    ? formatDistanceToNow(new Date(negociacao.updated_at), {
        addSuffix: true,
        locale: ptBR,
      })
    : null;

  // The accept-proposal seam is available ONLY from the `proposta` column
  // (user decision): accepting is what ends the negotiation, so it cannot fire
  // where no proposal is on the table. `fechado` is a Funil-internal terminal
  // state, explicitly NOT the trigger.
  const podeAceitarProposta =
    negociacao.etapa === 'proposta' && negociacao.status === 'aberta' && !!onAceitarProposta;

  return (
    <Card
      style={style}
      className="p-3 mb-2 cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold flex-shrink-0">
          {iniciais}
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-sm truncate mb-1">{nomeCliente}</h4>

          {negociacao.titulo && (
            <p className="text-xs text-muted-foreground truncate mb-1">
              {negociacao.titulo}
            </p>
          )}

          <div className="flex flex-wrap gap-1 mb-2">
            <Badge variant="secondary" className="text-xs">
              {negociacao.probabilidade}%
            </Badge>
            <Badge variant="outline" className="text-xs">
              {formatCurrency(Number(negociacao.valor_estimado))}
            </Badge>
            {cliente?.origem && (
              <Badge variant="outline" className="text-xs">
                {cliente.origem}
              </Badge>
            )}
          </div>

          {tempoRelativo && (
            <p className="text-xs text-muted-foreground mb-2">{tempoRelativo}</p>
          )}

          {negociacao.corretor && (
            <p className="text-xs text-muted-foreground truncate">
              {negociacao.corretor.nome}
            </p>
          )}
        </div>
      </div>

      {podeAceitarProposta && (
        <div className="mt-3 pt-2 border-t">
          <Button
            variant="default"
            size="sm"
            className="h-7 w-full text-xs gap-1"
            disabled={aceitandoProposta}
            // MUST stopPropagation: the card body carries the organ's dnd-kit
            // drag listeners, so without it the click is swallowed as a drag
            // start and the button never fires.
            onClick={(e) => {
              e.stopPropagation();
              onAceitarProposta?.(negociacao.id);
            }}
          >
            <CheckCircle2 className="w-3 h-3" />
            {aceitandoProposta ? 'Aceitando...' : 'Aceitar Proposta'}
          </Button>
        </div>
      )}

      <div className="flex gap-1 mt-3 pt-2 border-t">
        {cliente && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/clientes/${cliente.id}`);
            }}
          >
            <ExternalLink className="w-3 h-3" />
          </Button>
        )}
        {onRegistrarAtividade && cliente && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={(e) => {
              e.stopPropagation();
              onRegistrarAtividade(cliente.id);
            }}
          >
            <MessageSquare className="w-3 h-3" />
          </Button>
        )}
        {onArquivar && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={(e) => {
              e.stopPropagation();
              onArquivar(negociacao.id);
            }}
          >
            <Archive className="w-3 h-3" />
          </Button>
        )}
      </div>
    </Card>
  );
}
