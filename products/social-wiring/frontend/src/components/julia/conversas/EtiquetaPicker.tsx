/**
 * "Selecionar etiqueta" popover — search, optional "Sem etiqueta", and
 * "Criar nova etiqueta". Shared by the kanban "Adicionar coluna" and the
 * Cliente column's Etiquetas [+].
 */
import { useState, type ReactNode } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { mensagemErroConversas, useEtiquetaMutations, useEtiquetas, type Etiqueta } from "@/hooks/useJuliaConversas";

export const SEM_ETIQUETA = "__sem";

interface Props {
  trigger: ReactNode;
  /** Tag ids that must not be offered again (already a column / already on the contact). */
  excluir?: string[];
  /** Offer the "Sem etiqueta" pseudo-column. */
  comSemEtiqueta?: boolean;
  onSelect: (etiqueta: Etiqueta | typeof SEM_ETIQUETA) => void;
}

export function EtiquetaPicker({ trigger, excluir = [], comSemEtiqueta = false, onSelect }: Props) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const { data: etiquetas = [] } = useEtiquetas();
  const { criar } = useEtiquetaMutations();

  const q = busca.trim().toLowerCase();
  const lista = etiquetas.filter((e) => !excluir.includes(e.id) && e.nome.toLowerCase().includes(q));
  const existe = etiquetas.some((e) => e.nome.toLowerCase() === q);

  function escolher(e: Etiqueta | typeof SEM_ETIQUETA) {
    onSelect(e);
    setAberto(false);
    setBusca("");
  }
  function criarNova() {
    criar.mutate({ nome: busca.trim() }, {
      onSuccess: (nova) => escolher(nova),
      onError: (e) => toast.error(mensagemErroConversas(e, "Não foi possível criar a etiqueta.")),
    });
  }

  return (
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent className="w-64 p-2" align="start" data-testid="etiqueta-picker">
        <p className="px-1 pb-1 text-xs font-medium text-muted-foreground">Selecionar etiqueta</p>
        <Input
          autoFocus
          placeholder="Buscar etiqueta"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          className="h-8 text-sm"
          aria-label="Buscar etiqueta"
        />
        <ul className="mt-2 max-h-48 space-y-0.5 overflow-y-auto">
          {comSemEtiqueta && !excluir.includes(SEM_ETIQUETA) && (!q || "sem etiqueta".includes(q)) && (
            <li>
              <button type="button" className="w-full rounded px-2 py-1 text-left text-sm hover:bg-muted"
                onClick={() => escolher(SEM_ETIQUETA)}>Sem etiqueta</button>
            </li>
          )}
          {lista.map((e) => (
            <li key={e.id}>
              <button type="button" className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm hover:bg-muted"
                onClick={() => escolher(e)}>
                <span className="h-2.5 w-2.5 rounded-full bg-primary/60" style={e.cor ? { background: e.cor } : undefined} />
                {e.nome}
              </button>
            </li>
          ))}
          {lista.length === 0 && !comSemEtiqueta && (
            <li className="px-2 py-1 text-xs text-muted-foreground">Nenhuma etiqueta encontrada.</li>
          )}
        </ul>
        <button
          type="button"
          disabled={!busca.trim() || existe || criar.isPending}
          onClick={criarNova}
          className="mt-2 flex w-full items-center gap-1 rounded px-2 py-1 text-left text-sm text-primary hover:bg-muted disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" /> Criar nova etiqueta{busca.trim() && !existe ? ` "${busca.trim()}"` : ""}
        </button>
      </PopoverContent>
    </Popover>
  );
}
