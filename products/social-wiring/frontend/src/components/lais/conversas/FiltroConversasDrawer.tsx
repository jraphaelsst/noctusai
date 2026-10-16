/** "Filtro de conversas" drawer (live Lais a6). Draft is applied only on Filtrar. */
import { useState } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTeamMembers } from "@/hooks/useTeam";
import {
  FILTROS_VAZIOS, SEM_RESPONSAVEL, useEtiquetas,
  type FiltrosConversas, type OperacaoConversa, type StatusAtendimento, type StatusSw,
} from "@/hooks/useLaisConversas";

const OPERACOES: { key: OperacaoConversa; label: string }[] = [
  { key: "aluguel", label: "Aluguel" },
  { key: "compra", label: "Compra" },
  { key: "administracao", label: "Administração" },
  { key: "atualizacao", label: "Atualização" },
];
const STATUS_SW: { key: StatusSw; label: string }[] = [
  { key: "enviado_sw", label: "Enviado ao SW" },
  { key: "nao_pronto", label: "Não pronto" },
];
const ATENDIMENTO: { key: StatusAtendimento; label: string }[] = [
  { key: "julia", label: "Julia atendendo" },
  { key: "manual", label: "Atendimento manual" },
];

function alternar<T>(lista: T[], v: T): T[] {
  return lista.includes(v) ? lista.filter((x) => x !== v) : [...lista, v];
}

function Grupo({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{titulo}</legend>
      {children}
    </fieldset>
  );
}

interface Props {
  filtros: FiltrosConversas;
  onAplicar: (f: FiltrosConversas) => void;
  onClose: () => void;
}

export function FiltroConversasDrawer({ filtros, onAplicar, onClose }: Props) {
  const [d, setD] = useState<FiltrosConversas>(filtros);
  const { data: membros = [] } = useTeamMembers();
  const { data: etiquetas = [] } = useEtiquetas();
  const set = (p: Partial<FiltrosConversas>) => setD((x) => ({ ...x, ...p }));

  const check = (label: string, on: boolean, toggle: () => void) => (
    <label key={label} className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={on} onChange={toggle} /> {label}
    </label>
  );

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <aside role="dialog" aria-label="Filtro de conversas" className="flex h-full w-full max-w-sm flex-col bg-background shadow-xl" data-testid="filtro-drawer">
        <header className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-base font-semibold">Filtro de conversas</h2>
          <Button variant="ghost" size="icon" aria-label="Fechar" onClick={onClose}><X className="h-4 w-4" /></Button>
        </header>
        <div className="flex-1 space-y-5 overflow-y-auto p-4">
          <Grupo titulo="Operações">
            {OPERACOES.map((o) => (
              <label key={o.key} className="flex items-center gap-2 text-sm">
                <input type="radio" name="operacao" checked={d.operacao === o.key}
                  onChange={() => set({ operacao: o.key })} /> {o.label}
              </label>
            ))}
          </Grupo>
          <Grupo titulo="Status SW">
            {STATUS_SW.map((o) => check(o.label, d.statusSw.includes(o.key), () => set({ statusSw: alternar(d.statusSw, o.key) })))}
          </Grupo>
          <Grupo titulo="Status de atendimento">
            {ATENDIMENTO.map((o) => check(o.label, d.atendimento.includes(o.key), () => set({ atendimento: alternar(d.atendimento, o.key) })))}
          </Grupo>
          <Grupo titulo="Responsável">
            {check("Sem responsável", d.responsaveis.includes(SEM_RESPONSAVEL), () => set({ responsaveis: alternar(d.responsaveis, SEM_RESPONSAVEL) }))}
            {membros.map((m) => check(m.nome || m.email, d.responsaveis.includes(m.id), () => set({ responsaveis: alternar(d.responsaveis, m.id) })))}
          </Grupo>
          <Grupo titulo="Equipe">
            {/* Equipes arrive with wave 11 (Distribuição); until then there is nothing to pick. */}
            <p className="text-xs text-muted-foreground">Nenhuma equipe cadastrada.</p>
          </Grupo>
          <Grupo titulo="Etiquetas">
            {etiquetas.length === 0 && <p className="text-xs text-muted-foreground">Nenhuma etiqueta criada.</p>}
            {etiquetas.map((e) => check(e.nome, d.etiquetas.includes(e.id), () => set({ etiquetas: alternar(d.etiquetas, e.id) })))}
          </Grupo>
        </div>
        <footer className="flex justify-end gap-2 border-t p-3">
          <Button variant="outline" onClick={() => { setD({ ...FILTROS_VAZIOS, q: filtros.q }); }}>Limpar</Button>
          <Button onClick={() => { onAplicar(d); onClose(); }}>Filtrar</Button>
        </footer>
      </aside>
    </div>
  );
}
