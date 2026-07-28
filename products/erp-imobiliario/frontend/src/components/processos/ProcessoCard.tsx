import { ProcessoVenda } from '@/types/processos';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { ExternalLink, Archive, ArchiveRestore } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { formatCurrency } from '@/lib/utils';

interface ProcessoCardProps {
  processo: ProcessoVenda;
  onArquivar?: (processoId: string) => void;
  isDragging?: boolean;
}

// Drag-and-drop wiring is owned by the `KanbanCard` organ wrapper
// (`@noctusai/lib/components`) that renders this via `renderCard`.
// `isDragging` is only the DragOverlay ghost-copy flag.
export function ProcessoCard({ processo, onArquivar, isDragging }: ProcessoCardProps) {
  const navigate = useNavigate();

  const style = { opacity: isDragging ? 0.5 : 1 };

  const cliente = processo.cliente;
  const nomeCliente = cliente?.nome ?? 'Cliente sem nome';

  const iniciais = nomeCliente
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  const tempoRelativo = processo.updated_at
    ? formatDistanceToNow(new Date(processo.updated_at), {
        addSuffix: true,
        locale: ptBR,
      })
    : null;

  return (
    <Card
      style={style}
      className={`p-3 mb-2 cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow ${
        processo.arquivado ? 'opacity-60' : ''
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold flex-shrink-0">
          {iniciais}
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-sm truncate mb-1">{nomeCliente}</h4>

          {processo.negociacao?.titulo && (
            <p className="text-xs text-muted-foreground truncate mb-1">
              {processo.negociacao.titulo}
            </p>
          )}

          <div className="flex flex-wrap gap-1 mb-2">
            <Badge variant="outline" className="text-xs">
              {formatCurrency(Number(processo.valor))}
            </Badge>
            {processo.arquivado && (
              <Badge variant="secondary" className="text-xs">
                Arquivado
              </Badge>
            )}
          </div>

          {tempoRelativo && (
            <p className="text-xs text-muted-foreground mb-2">{tempoRelativo}</p>
          )}

          {processo.corretor && (
            <p className="text-xs text-muted-foreground truncate">
              {processo.corretor.nome}
            </p>
          )}
        </div>
      </div>

      <div className="flex gap-1 mt-3 pt-2 border-t">
        {cliente && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            // stopPropagation is mandatory: the card body carries the organ's
            // drag listeners, so an unguarded click is swallowed as a drag.
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/clientes/${cliente.id}`);
            }}
          >
            <ExternalLink className="w-3 h-3" />
          </Button>
        )}
        {onArquivar && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            title={processo.arquivado ? 'Restaurar processo' : 'Arquivar processo'}
            onClick={(e) => {
              e.stopPropagation();
              onArquivar(processo.id);
            }}
          >
            {processo.arquivado ? (
              <ArchiveRestore className="w-3 h-3" />
            ) : (
              <Archive className="w-3 h-3" />
            )}
          </Button>
        )}
      </div>
    </Card>
  );
}
