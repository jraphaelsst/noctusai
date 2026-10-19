import { pct, type Painel } from "@/hooks/useJuliaPainel";
import { JULIA_LABEL } from "@/nav/julia";

export function Funil({ f }: { f: Painel["funil"] }) {
  const etapas = [
    { id: "topo", label: "Topo de funil", valor: f.topo, p: f.topo > 0 ? 100 : 0 },
    { id: "atendidos", label: `Atendimentos (atendidos pela ${JULIA_LABEL})`, valor: f.atendidos, p: pct(f.atendidos, f.topo) },
    { id: "enviados", label: "Encaminhados (enviados ao SW)", valor: f.enviados, p: pct(f.enviados, f.topo) },
  ];
  return (
    <ol className="space-y-2" data-testid="painel-funil">
      {etapas.map((e) => (
        <li key={e.id} data-testid={`funil-${e.id}`}>
          <div className="flex justify-between text-sm">
            <span>{e.label}</span>
            <span><strong>{e.valor}</strong> · <span data-testid={`funil-${e.id}-pct`}>{e.p}%</span></span>
          </div>
          <div className="h-2 rounded bg-muted"><div className="h-2 rounded bg-primary" style={{ width: `${e.p}%` }} /></div>
        </li>
      ))}
    </ol>
  );
}
