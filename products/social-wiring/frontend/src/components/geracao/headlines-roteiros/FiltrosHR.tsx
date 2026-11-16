/** Filters of "Headlines e Roteiros": q, Estrutura, perfil, status do roteiro (estruturas-contract §6.9). */
import { Input } from "@/components/ui/input";
import type { EstruturaResumo } from "@/types/estruturas";
import { FILTRO_STATUS } from "./rotulos";

export interface FiltrosHRValor {
  busca: string;
  estruturaId: string;
  perfilId: string;
  status: string;
}

const SELECT = "h-9 rounded-md border border-input bg-background px-2 text-sm";

export function FiltrosHR({
  valor,
  onChange,
  estruturas,
}: {
  valor: FiltrosHRValor;
  onChange: (v: FiltrosHRValor) => void;
  /** Library Estruturas the marca can filter by (also yields the profile options). */
  estruturas: EstruturaResumo[];
}) {
  const perfis = [...new Map(estruturas.map((e) => [e.perfil.id, e.perfil])).values()];
  const set = (p: Partial<FiltrosHRValor>) => onChange({ ...valor, ...p });
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Input
        aria-label="Pesquisar headlines e roteiros"
        placeholder="Pesquisar..."
        className="max-w-xs"
        value={valor.busca}
        onChange={(e) => set({ busca: e.target.value })}
      />
      <select aria-label="Filtrar por estrutura" className={SELECT} value={valor.estruturaId} onChange={(e) => set({ estruturaId: e.target.value })}>
        <option value="">Todas as estruturas</option>
        {estruturas.map((e) => (
          <option key={e.id} value={e.id}>
            #{e.codigo} · @{e.perfil.handle}
          </option>
        ))}
      </select>
      <select aria-label="Filtrar por perfil" className={SELECT} value={valor.perfilId} onChange={(e) => set({ perfilId: e.target.value })}>
        <option value="">Todos os perfis</option>
        {perfis.map((p) => (
          <option key={p.id} value={p.id}>
            @{p.handle}
          </option>
        ))}
      </select>
      <select aria-label="Filtrar por status do roteiro" className={SELECT} value={valor.status} onChange={(e) => set({ status: e.target.value })}>
        {FILTRO_STATUS.map((s) => (
          <option key={s.valor} value={s.valor}>
            {s.rotulo}
          </option>
        ))}
      </select>
    </div>
  );
}
