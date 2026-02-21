import { Meta, TipoMeta } from "@/types";
import { MetaCard } from "@/components/ui/meta-card";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

interface SortableMetaCardProps {
  meta: Meta;
  onEdit: (meta: Meta) => void;
  onDelete: (id: string) => void;
  isSelectable: boolean;
  isSelected: boolean;
  onSelect: (id: string, selected: boolean) => void;
}

function SortableMetaCard({
  meta,
  onEdit,
  onDelete,
  isSelectable,
  isSelected,
  onSelect,
}: SortableMetaCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: meta.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <MetaCard
        meta={meta}
        onEdit={onEdit}
        onDelete={onDelete}
        isSelectable={isSelectable}
        isSelected={isSelected}
        onSelect={onSelect}
      />
    </div>
  );
}

interface MetasDraggableSectionProps {
  metas: Meta[];
  tipo: TipoMeta;
  onEdit: (meta: Meta) => void;
  onDelete: (id: string) => void;
  onReorder: (metasIds: string[]) => void;
  isSelectable: boolean;
  selectedIds: Set<string>;
  onSelect: (id: string, selected: boolean) => void;
}

export function MetasDraggableSection({
  metas,
  tipo,
  onEdit,
  onDelete,
  onReorder,
  isSelectable,
  selectedIds,
  onSelect,
}: MetasDraggableSectionProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Mínimo de 8px de movimento para ativar drag
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const oldIndex = metas.findIndex((m) => m.id === active.id);
      const newIndex = metas.findIndex((m) => m.id === over.id);

      const reordered = arrayMove(metas, oldIndex, newIndex);
      onReorder(reordered.map((m) => m.id));
    }
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      <SortableContext
        items={metas.map((m) => m.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {metas.map((meta) => (
            <SortableMetaCard
              key={meta.id}
              meta={meta}
              onEdit={onEdit}
              onDelete={onDelete}
              isSelectable={isSelectable}
              isSelected={selectedIds.has(meta.id)}
              onSelect={onSelect}
            />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}
