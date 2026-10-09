import type { Marca } from "@/hooks/useMarcas";

interface MarcaSwitcherProps {
  marcas: Marca[];
  marcaId: string | null;
  onChange: (id: string) => void;
}

export function MarcaSwitcher({ marcas, marcaId, onChange }: MarcaSwitcherProps) {
  if (marcas.length === 0) return null;
  return (
    <select
      aria-label="Marca"
      value={marcaId ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm"
    >
      {marcas.map((m) => (
        <option key={m.id} value={m.id}>
          {m.name}
        </option>
      ))}
    </select>
  );
}
