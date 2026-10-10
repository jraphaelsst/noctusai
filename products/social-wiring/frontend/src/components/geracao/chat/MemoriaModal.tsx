/** Memória modal (contract §7.2): what the AI knows about the user across chats. ≤500 chars per item, ≤50 items. */
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAdicionarMemoria, useMemorias, useRemoverMemoria } from "@/hooks/geracao/useChat";

export const MEMORIA_MAX = 500;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marcaId: string | null;
}

const msg = (e: unknown, fallback: string) =>
  e instanceof Error && e.message ? e.message.replace(/^\[\d+\]\s*/, "") : fallback;

export function MemoriaModal({ open, onOpenChange, marcaId }: Props) {
  const q = useMemorias(marcaId, open);
  const adicionar = useAdicionarMemoria();
  const remover = useRemoverMemoria();
  const [texto, setTexto] = useState("");
  const itens = q.data ?? [];

  async function salvar() {
    const t = texto.trim();
    if (!t || !marcaId) return;
    try {
      await adicionar.mutateAsync({ marca_id: marcaId, texto: t });
      setTexto("");
      toast.success("Memória salva.");
    } catch (e) {
      toast.error(msg(e, "Não foi possível salvar (limite de 50 memórias por marca)."));
    }
  }

  async function apagar(id: string) {
    try {
      await remover.mutateAsync(id);
    } catch (e) {
      toast.error(msg(e, "Não foi possível apagar a memória."));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Memória</DialogTitle>
          <DialogDescription>
            O que a IA sabe sobre você em todos os chats de Roteiro e Headline. Ex.: &quot;guarda na memória que eu não
            uso emojis&quot;.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Textarea
            aria-label="Nova memória"
            value={texto}
            maxLength={MEMORIA_MAX}
            rows={3}
            placeholder="Ex.: Meu público são donos de clínica de estética."
            onChange={(e) => setTexto(e.target.value)}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {texto.length}/{MEMORIA_MAX}
            </span>
            <Button type="button" size="sm" disabled={!texto.trim() || adicionar.isPending || !marcaId} onClick={() => void salvar()}>
              {adicionar.isPending ? "Salvando..." : "Salvar"}
            </Button>
          </div>
        </div>

        <div className="max-h-64 overflow-y-auto">
          {q.showSkeleton ? (
            <div className="space-y-2" data-testid="memorias-skeleton">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : q.isError && !q.data ? (
            <div role="alert" className="text-sm">
              Não foi possível carregar as memórias.{" "}
              <Button type="button" size="sm" variant="outline" onClick={() => void q.refetch()}>
                Tentar novamente
              </Button>
            </div>
          ) : itens.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nada salvo ainda.</p>
          ) : (
            <ul className="space-y-2" aria-busy={q.isRefreshing}>
              {itens.map((m) => (
                <li key={m.id} className="flex items-start justify-between gap-2 rounded-md border p-2 text-sm">
                  <span className="whitespace-pre-wrap">{m.texto}</span>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={remover.isPending}
                    onClick={() => void apagar(m.id)}
                  >
                    Apagar
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
