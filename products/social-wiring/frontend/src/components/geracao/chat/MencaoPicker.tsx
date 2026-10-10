/**
 * @-mention picker (contract §7.2 / #46): 4 tabs — Minha Pesquisa · Segundo
 * Cérebro · Biblioteca · Headlines. Picking an entry attaches it as a chip.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useMencoes } from "@/hooks/geracao/useChat";
import type { Mencao, MencaoTipo } from "@/types/geracao";

export const ABAS_MENCAO: { tipo: MencaoTipo; rotulo: string }[] = [
  { tipo: "pesquisa", rotulo: "Minha Pesquisa" },
  { tipo: "cerebro", rotulo: "Segundo Cérebro" },
  { tipo: "biblioteca", rotulo: "Biblioteca" },
  { tipo: "headline", rotulo: "Headlines" },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marcaId: string | null;
  anexados: Mencao[];
  limiteAtingido: boolean;
  onEscolher: (m: Mencao) => void;
}

export function MencaoPicker({ open, onOpenChange, marcaId, anexados, limiteAtingido, onEscolher }: Props) {
  const [tipo, setTipo] = useState<MencaoTipo>("pesquisa");
  const [busca, setBusca] = useState("");
  const buscaDeb = useDebouncedValue(busca, 300);
  const q = useMencoes(marcaId, tipo, buscaDeb, open);
  const itens = q.data ?? [];
  const ja = new Set(anexados.map((a) => `${a.tipo}:${a.id}`));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Mencionar com @</DialogTitle>
          <DialogDescription>Anexe pesquisas, cérebros, virais ou headlines como contexto da mensagem.</DialogDescription>
        </DialogHeader>

        <Tabs value={tipo} onValueChange={(v) => setTipo(v as MencaoTipo)}>
          <TabsList className="flex-wrap">
            {ABAS_MENCAO.map((a) => (
              <TabsTrigger key={a.tipo} value={a.tipo}>
                {a.rotulo}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <Input aria-label="Buscar menção" placeholder="Buscar..." value={busca} onChange={(e) => setBusca(e.target.value)} />
        {limiteAtingido && <p className="text-xs text-muted-foreground">Limite de 10 referências por mensagem.</p>}

        <div className="max-h-72 overflow-y-auto" aria-busy={q.isRefreshing}>
          {q.showSkeleton ? (
            <div className="space-y-2" data-testid="mencoes-skeleton">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : q.isError && !q.data ? (
            <div role="alert" className="text-sm">
              Não foi possível carregar.{" "}
              <Button type="button" size="sm" variant="outline" onClick={() => void q.refetch()}>
                Tentar novamente
              </Button>
            </div>
          ) : itens.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nada encontrado.</p>
          ) : (
            <ul className="space-y-1">
              {itens.map((m) => {
                const anexado = ja.has(`${m.tipo}:${m.id}`);
                return (
                  <li key={`${m.tipo}:${m.id}`}>
                    <button
                      type="button"
                      disabled={anexado || limiteAtingido}
                      className="w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted disabled:opacity-50"
                      onClick={() => {
                        onEscolher(m);
                        onOpenChange(false);
                      }}
                    >
                      <span className="block truncate font-medium">{m.rotulo}</span>
                      {m.detalhe && <span className="block truncate text-xs text-muted-foreground">{m.detalhe}</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
