/**
 * Conversation rail (contract §7.2): "Conversas", `+`, inline rename (max 100,
 * "Salvando..."), "Apagar conversa" (confirm), "Ver mais conversas" and the
 * CoreStudio empty copy.
 */
import { useState } from "react";
import { Check, Loader2, MessageSquarePlus, Pencil, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ConfirmarModal } from "@/components/pesquisa/ConfirmarModal";
import type { Conversa } from "@/types/geracao";

interface Props {
  conversas: Conversa[];
  selecionadaId: string | null;
  showSkeleton: boolean;
  isRefreshing: boolean;
  erro: boolean;
  onTentarNovamente: () => void;
  temMais: boolean;
  carregandoMais: boolean;
  onVerMais: () => void;
  onSelecionar: (id: string) => void;
  onNova: () => void;
  onRenomear: (id: string, titulo: string) => Promise<void>;
  onApagar: (id: string) => Promise<void>;
}

export function ConversasRail({
  conversas,
  selecionadaId,
  showSkeleton,
  isRefreshing,
  erro,
  onTentarNovamente,
  temMais,
  carregandoMais,
  onVerMais,
  onSelecionar,
  onNova,
  onRenomear,
  onApagar,
}: Props) {
  const [editando, setEditando] = useState<string | null>(null);
  const [titulo, setTitulo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [apagar, setApagar] = useState<Conversa | null>(null);
  const [apagando, setApagando] = useState(false);

  async function salvarTitulo(id: string) {
    const t = titulo.trim();
    if (!t) {
      setEditando(null);
      return;
    }
    setSalvando(true);
    try {
      await onRenomear(id, t.slice(0, 100));
      setEditando(null);
    } finally {
      setSalvando(false);
    }
  }

  async function confirmarApagar() {
    if (!apagar) return;
    setApagando(true);
    try {
      await onApagar(apagar.id);
      setApagar(null);
    } finally {
      setApagando(false);
    }
  }

  return (
    <aside aria-label="Conversas" className="flex w-full flex-col gap-2 md:w-64 md:shrink-0">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Conversas</h2>
        <Button type="button" size="icon" variant="ghost" aria-label="Nova conversa" onClick={onNova}>
          <MessageSquarePlus className="h-4 w-4" />
        </Button>
      </div>

      {showSkeleton ? (
        <div className="space-y-2" data-testid="conversas-skeleton">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : erro ? (
        <div role="alert" className="rounded-md border border-destructive/40 p-3 text-sm">
          <p>Não foi possível carregar as conversas.</p>
          <Button type="button" size="sm" variant="outline" className="mt-2" onClick={onTentarNovamente}>
            Tentar novamente
          </Button>
        </div>
      ) : conversas.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhuma conversa para este agente.</p>
      ) : (
        <ul className={cn("space-y-1", isRefreshing && "opacity-80")}>
          {conversas.map((c) => (
            <li key={c.id}>
              {editando === c.id ? (
                <div className="flex items-center gap-1">
                  <Input
                    aria-label="Título da conversa"
                    value={titulo}
                    maxLength={100}
                    autoFocus
                    disabled={salvando}
                    onChange={(e) => setTitulo(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void salvarTitulo(c.id);
                      if (e.key === "Escape") setEditando(null);
                    }}
                  />
                  {salvando ? (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Loader2 className="h-3 w-3 animate-spin" /> Salvando...
                    </span>
                  ) : (
                    <>
                      <Button type="button" size="icon" variant="ghost" aria-label="Salvar título" onClick={() => void salvarTitulo(c.id)}>
                        <Check className="h-4 w-4" />
                      </Button>
                      <Button type="button" size="icon" variant="ghost" aria-label="Cancelar" onClick={() => setEditando(null)}>
                        <X className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                </div>
              ) : (
                <div
                  className={cn(
                    "group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm",
                    c.id === selecionadaId ? "bg-muted font-medium" : "hover:bg-muted/60",
                  )}
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left"
                    title={c.titulo}
                    aria-current={c.id === selecionadaId ? "true" : undefined}
                    onClick={() => onSelecionar(c.id)}
                  >
                    {c.titulo}
                  </button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    aria-label={`Renomear conversa ${c.titulo}`}
                    onClick={() => {
                      setTitulo(c.titulo);
                      setEditando(c.id);
                    }}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    aria-label={`Apagar conversa ${c.titulo}`}
                    onClick={() => setApagar(c)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {temMais && (
        <Button type="button" variant="ghost" size="sm" disabled={carregandoMais} onClick={onVerMais}>
          {carregandoMais ? "Carregando..." : "Ver mais conversas"}
        </Button>
      )}

      <ConfirmarModal
        open={!!apagar}
        onOpenChange={(o) => !o && setApagar(null)}
        titulo="Apagar conversa"
        descricao={`A conversa "${apagar?.titulo ?? ""}" e todas as suas mensagens serão apagadas. Esta ação não pode ser desfeita.`}
        rotuloConfirmar="Apagar conversa"
        onConfirmar={() => void confirmarApagar()}
        pendente={apagando}
      />
    </aside>
  );
}
