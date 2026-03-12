import { Cliente } from '@/types/clientes';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ExternalLink, MessageSquare, Archive, Brain } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { formatCurrency } from '@/lib/utils';

interface ClienteCardProps {
  cliente: Cliente;
  onRegistrarAtividade?: (clienteId: string) => void;
  onArquivar?: (clienteId: string) => void;
  isDragging?: boolean;
}

export function ClienteCard({ cliente, onRegistrarAtividade, onArquivar, isDragging }: ClienteCardProps) {
  const navigate = useNavigate();
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({ id: cliente.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const iniciais = cliente.nome
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  const tempoRelativo = cliente.updated_at
    ? formatDistanceToNow(new Date(cliente.updated_at), {
        addSuffix: true,
        locale: ptBR,
      })
    : null;

  return (
    <Card
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className="p-3 mb-2 cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold flex-shrink-0">
          {iniciais}
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-sm truncate mb-1">{cliente.nome}</h4>

          <div className="flex flex-wrap gap-1 mb-2">
            <Badge variant="secondary" className="text-xs">
              {cliente.probabilidade}%
            </Badge>
            <Badge variant="outline" className="text-xs">
              {formatCurrency(Number(cliente.valor_estimado))}
            </Badge>
            {cliente.origem && (
              <Badge variant="outline" className="text-xs">
                {cliente.origem}
              </Badge>
            )}
            {cliente.lead_score != null && (
              <Badge
                variant="outline"
                className={`text-xs gap-0.5 ${
                  cliente.lead_score >= 80
                    ? 'bg-green-100 text-green-800'
                    : cliente.lead_score >= 60
                      ? 'bg-yellow-100 text-yellow-800'
                      : cliente.lead_score >= 40
                        ? 'bg-orange-100 text-orange-800'
                        : 'bg-red-100 text-red-800'
                }`}
              >
                <Brain className="w-3 h-3" />
                {cliente.lead_score}
              </Badge>
            )}
          </div>

          {tempoRelativo && (
            <p className="text-xs text-muted-foreground mb-2">{tempoRelativo}</p>
          )}

          {cliente.usuario && (
            <p className="text-xs text-muted-foreground truncate">
              {cliente.usuario.nome}
            </p>
          )}
        </div>
      </div>

      <div className="flex gap-1 mt-3 pt-2 border-t">
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
        {onRegistrarAtividade && (
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
              onArquivar(cliente.id);
            }}
          >
            <Archive className="w-3 h-3" />
          </Button>
        )}
      </div>
    </Card>
  );
}
