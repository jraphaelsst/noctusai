import { useState } from 'react';
import { FiltrosFunil } from '@/components/clientes/FiltrosFunil';
import { ColunaFunil } from '@/components/clientes/ColunaFunil';
import { NovoClienteDialog } from '@/components/clientes/NovoClienteDialog';
import { useFunil, useMoverClienteEtapa } from '@/hooks/useFunil';
import { useToggleArquivarCliente } from '@/hooks/useClientes';
import { useFunilFiltrosStore } from '@/store/funilFiltrosStore';
import { DndContext, DragEndEvent, DragOverlay, DragStartEvent, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { ClienteCard } from '@/components/clientes/ClienteCard';
import { EtapaFunil } from '@/types/clientes';
import { Skeleton } from '@/components/ui/skeleton';

export default function Funil() {
  const [novoClienteOpen, setNovoClienteOpen] = useState(false);
  const [atividadeClienteId, setAtividadeClienteId] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);

  const filtrosStore = useFunilFiltrosStore();
  const { data: colunas, isLoading } = useFunil({
    ...filtrosStore,
    etapa: filtrosStore.etapa === 'todas' ? undefined : filtrosStore.etapa,
  });
  const { mutate: moverCliente } = useMoverClienteEtapa();
  const { mutate: toggleArquivar } = useToggleArquivarCliente();

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);

    if (!over) return;

    const clienteId = active.id as string;
    const paraEtapa = over.id as EtapaFunil;

    // Encontrar o cliente atual
    const colunaOrigem = colunas?.find((c) =>
      c.cards.some((card) => card.id === clienteId)
    );
    const cliente = colunaOrigem?.cards.find((c) => c.id === clienteId);

    if (!cliente || cliente.etapa_atual === paraEtapa) return;

    // Calcular novo índice se foi dropado sobre outro card
    let novo_indice: number | undefined;
    if (typeof over.id === 'string' && over.id !== paraEtapa) {
      const colunaDestino = colunas?.find((c) => c.etapa === paraEtapa);
      const indice = colunaDestino?.cards.findIndex((c) => c.id === over.id);
      novo_indice = indice !== undefined && indice >= 0 ? indice : undefined;
    }

    moverCliente({
      cliente_id: clienteId,
      para_etapa: paraEtapa,
      novo_indice,
    });
  };

  const clienteAtivo = colunas
    ?.flatMap((c) => c.cards)
    .find((c) => c.id === activeId);

  if (isLoading) {
    return (
      <div className="container mx-auto p-4 sm:p-6">
        <Skeleton className="h-12 w-64 mb-6" />
        <div className="flex gap-4 overflow-x-auto pb-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="w-80 h-96 flex-shrink-0" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <FiltrosFunil onNovoCliente={() => setNovoClienteOpen(true)} />

      <DndContext
        sensors={sensors}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="flex gap-4 overflow-x-auto pb-4">
          {colunas?.map((coluna) => (
            <ColunaFunil
              key={coluna.etapa}
              coluna={coluna}
              onRegistrarAtividade={setAtividadeClienteId}
              onArquivar={toggleArquivar}
            />
          ))}
        </div>

        <DragOverlay>
          {clienteAtivo && (
            <div className="rotate-3 scale-105">
              <ClienteCard cliente={clienteAtivo} isDragging />
            </div>
          )}
        </DragOverlay>
      </DndContext>

      <NovoClienteDialog open={novoClienteOpen} onOpenChange={setNovoClienteOpen} />
    </div>
  );
}
