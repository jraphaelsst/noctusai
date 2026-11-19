/**
 * Monthly cost cap of the criação pipeline (criacao-pipeline-contract.md M-E, owner decision 5): vendor
 * spend per org per month, default US$ 15, editable by org admins. Every change is an event server-side.
 * When the cap is hit the card shows `falhou` (cota), so this is where the owner raises it.
 */
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { COTA_PADRAO_USD, useAtualizarCota, useCotaCriacao } from "@/hooks/geracao/useCriacao";
import { mensagemErroServidor } from "@/lib/erroServidor";

const usd = (n: number) => n.toLocaleString("pt-BR", { style: "currency", currency: "USD" });

/** "15", "15,50", "15.5" -> number; anything else (blank, negative, text) -> null. */
export function parseLimiteUsd(texto: string): number | null {
  const t = texto.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

export function CotaCriacaoDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const cota = useCotaCriacao();
  const atualizar = useAtualizarCota();
  const [texto, setTexto] = useState<string | null>(null);

  const salvo = cota.data?.limite_usd_mes;
  const valor = texto ?? (salvo != null ? String(salvo).replace(".", ",") : "");
  const parsed = parseLimiteUsd(valor);
  const invalido = valor !== "" && parsed === null;
  const padrao = cota.data?.padrao_usd_mes ?? COTA_PADRAO_USD;

  function salvar() {
    if (parsed === null) return;
    atualizar.mutate(
      { limite_usd_mes: parsed },
      {
        onSuccess: () => {
          toast.success("Limite mensal atualizado.");
          setTexto(null);
          onClose();
        },
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível salvar o limite mensal.")),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Limite mensal de custo</DialogTitle>
          <DialogDescription>
            Teto de gasto com voz, avatar e vídeo por mês. Ao atingir o limite, os cards param com o aviso de cota e
            nada é gerado em silêncio. O padrão é {usd(padrao)}.
          </DialogDescription>
        </DialogHeader>
        {cota.showSkeleton ? (
          <Skeleton className="h-10 w-full" data-testid="cota-skeleton" />
        ) : cota.isError && !cota.data ? (
          <div role="alert" className="space-y-2 text-sm">
            <p className="text-destructive">Não foi possível carregar o limite mensal.</p>
            <Button size="sm" variant="outline" onClick={() => void cota.refetch()}>
              Tentar novamente
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            <label className="block space-y-1 text-sm">
              <span>Limite mensal (US$)</span>
              <Input
                inputMode="decimal"
                aria-label="Limite mensal em dólares"
                aria-invalid={invalido}
                aria-describedby="cota-ajuda"
                value={valor}
                onChange={(e) => setTexto(e.target.value)}
              />
            </label>
            <p id="cota-ajuda" className={invalido ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
              {invalido
                ? "Use um valor em dólares, por exemplo 15 ou 15,50."
                : cota.data?.gasto_usd_mes != null
                  ? `Gasto neste mês: ${usd(cota.data.gasto_usd_mes)}.`
                  : "Gasto deste mês ainda não medido."}
            </p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button disabled={parsed === null || atualizar.isPending || !cota.data} onClick={salvar}>
            {atualizar.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
