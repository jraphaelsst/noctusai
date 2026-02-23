import { ColunaFunil as ColunaFunilType } from '@/types/clientes';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { ETAPAS_CONFIG } from '@/lib/etapasConfig';
import { ClienteCard } from './ClienteCard';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';

interface ColunaFunilProps {
  coluna: ColunaFunilType;
  onRegistrarAtividade?: (clienteId: string) => void;
  onArquivar?: (clienteId: string) => void;
}

export function ColunaFunil({ coluna, onRegistrarAtividade, onArquivar }: ColunaFunilProps) {
  const config = ETAPAS_CONFIG[coluna.etapa];
  const { setNodeRef } = useDroppable({
    id: coluna.etapa,
  });

  return (
    <div className="flex-shrink-0 w-80">
      <Card className="h-full flex flex-col">
        <div className={`p-4 border-b ${config.bgColor} ${config.borderColor}`}>
          <div className="flex items-center justify-between mb-2">
            <h3 className={`font-semibold ${config.color}`}>{config.label}</h3>
            <Badge variant="secondary">{coluna.total}</Badge>
          </div>
          <p className="text-sm font-medium">
            {new Intl.NumberFormat('pt-BR', {
              style: 'currency',
              currency: 'BRL',
            }).format(coluna.valorTotal)}
          </p>
        </div>

        <div ref={setNodeRef} className="flex-1 p-3 overflow-y-auto">
          <SortableContext
            items={coluna.cards.map((c) => c.id)}
            strategy={verticalListSortingStrategy}
          >
            {coluna.cards.map((cliente) => (
              <ClienteCard
                key={cliente.id}
                cliente={cliente}
                onRegistrarAtividade={onRegistrarAtividade}
                onArquivar={onArquivar}
              />
            ))}
          </SortableContext>

          {coluna.cards.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-8">
              Nenhum cliente nesta etapa
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
