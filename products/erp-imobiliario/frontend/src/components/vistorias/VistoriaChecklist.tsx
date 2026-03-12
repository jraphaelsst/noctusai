import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useUpdateVistoria } from '@/hooks/useVistorias';
import type { ChecklistItem, EstadoChecklist } from '@/types/locacoes';
import { Save } from 'lucide-react';

const ESTADO_OPTIONS: { value: EstadoChecklist; label: string; color: string }[] = [
  { value: 'bom', label: 'Bom', color: 'bg-green-100 text-green-800' },
  { value: 'regular', label: 'Regular', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'ruim', label: 'Ruim', color: 'bg-red-100 text-red-800' },
  { value: 'NA', label: 'N/A', color: 'bg-gray-100 text-gray-800' },
];

interface VistoriaChecklistProps {
  vistoriaId: string;
  checklist: ChecklistItem[];
  readOnly?: boolean;
}

export function VistoriaChecklist({ vistoriaId, checklist, readOnly }: VistoriaChecklistProps) {
  const [items, setItems] = useState<ChecklistItem[]>([...checklist]);
  const [hasChanges, setHasChanges] = useState(false);
  const { mutate: updateVistoria, isPending } = useUpdateVistoria();

  const updateItem = (index: number, field: keyof ChecklistItem, value: string) => {
    const updated = [...items];
    updated[index] = { ...updated[index], [field]: value };
    setItems(updated);
    setHasChanges(true);
  };

  const handleSave = () => {
    updateVistoria(
      { id: vistoriaId, checklist: items },
      { onSuccess: () => setHasChanges(false) }
    );
  };

  if (!checklist || checklist.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Nenhum item no checklist</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {!readOnly && hasChanges && (
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={isPending}>
            <Save className="w-4 h-4 mr-2" />
            {isPending ? 'Salvando...' : 'Salvar Alterações'}
          </Button>
        </div>
      )}

      <Card>
        <div className="divide-y">
          {items.map((item, index) => {
            const estadoOpt = ESTADO_OPTIONS.find((o) => o.value === item.estado);
            return (
              <div key={index} className="flex items-center gap-3 p-3">
                <span className="text-sm font-medium flex-1 min-w-0">{item.item}</span>

                {readOnly ? (
                  <Badge variant="outline" className={estadoOpt?.color || ''}>
                    {estadoOpt?.label || item.estado}
                  </Badge>
                ) : (
                  <Select
                    value={item.estado}
                    onValueChange={(v) => updateItem(index, 'estado', v)}
                  >
                    <SelectTrigger className="w-[110px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ESTADO_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}

                {readOnly ? (
                  item.observacao && (
                    <span className="text-xs text-muted-foreground max-w-[200px] truncate">
                      {item.observacao}
                    </span>
                  )
                ) : (
                  <Input
                    className="w-40"
                    placeholder="Obs."
                    value={item.observacao}
                    onChange={(e) => updateItem(index, 'observacao', e.target.value)}
                  />
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
