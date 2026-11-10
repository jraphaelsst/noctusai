import { useState } from "react";

import { Input } from "@/components/ui/input";

/** The per-visita "Horário" (R11 `horario`, editable in both statuses): saved when the field loses focus. */
export function HorarioVisita({
  codigo,
  horario,
  onSalvar,
}: {
  codigo: string;
  horario: string | null;
  onSalvar: (valor: string | null) => void;
}) {
  const [valor, setValor] = useState((horario ?? "").slice(0, 5));
  return (
    <div className="shrink-0">
      <label className="block text-xs text-muted-foreground" htmlFor={`horario-${codigo}`}>
        Horário
      </label>
      <Input
        id={`horario-${codigo}`}
        type="time"
        value={valor}
        onChange={(e) => setValor(e.target.value)}
        onBlur={() => {
          if (valor !== (horario ?? "").slice(0, 5)) onSalvar(valor || null);
        }}
        className="h-8 w-28"
        data-testid={`visita-horario-${codigo}`}
      />
    </div>
  );
}
