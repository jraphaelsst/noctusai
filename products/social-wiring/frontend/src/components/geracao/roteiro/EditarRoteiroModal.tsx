/**
 * Editar Roteiro (contract §7.8): Nome + markdown + Copiar, Gostei/Não Gostei,
 * ⋯ Reprocessar ("Informação Adicional:"), footer Cancelar / Atualizar.
 * Opened from Roteiros (👁 / `?open=`). Real status only: while the roteiro is
 * still being produced the body shows its `etapa`, not a fake progress bar.
 */
import { useState } from "react";
import { AlertCircle, Loader2, MoreHorizontal, RefreshCw } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useReprocessarRoteiro, useRoteiro } from "@/hooks/geracao/useRoteiros";
import type { Roteiro } from "@/types/geracao";
import { StatusBadge } from "../StatusBadge";
import { FeedbackRoteiro } from "./FeedbackRoteiro";
import { RoteiroCorpo, useEdicaoRoteiro } from "./RoteiroEdicao";

export const INFO_ADICIONAL_MAX = 2000;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  roteiroId: string | null;
  /** Reprocessar creates a NEW roteiro (#39); the host may want to open it. */
  onReprocessado?: (novo: Roteiro) => void;
}

export function EditarRoteiroModal({ open, onOpenChange, roteiroId, onReprocessado }: Props) {
  const q = useRoteiro(open ? roteiroId : null);
  const roteiro = q.data;
  const edicao = useEdicaoRoteiro(roteiro);
  const reprocessar = useReprocessarRoteiro();
  const [menuAberto, setMenuAberto] = useState(false);
  const [reprocessoAberto, setReprocessoAberto] = useState(false);
  const [info, setInfo] = useState("");

  async function confirmarReprocesso() {
    if (!roteiro) return;
    try {
      const novo = await reprocessar.mutateAsync({
        id: roteiro.id,
        instrucoes_adicionais: info.trim() || undefined,
      });
      toast.success("Reprocessando: um novo roteiro foi criado.");
      setReprocessoAberto(false);
      setInfo("");
      onReprocessado?.(novo);
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error && e.message ? e.message.replace(/^\[\d+\]\s*/, "") : "Não foi possível reprocessar.");
    }
  }

  const pronto = roteiro?.status === "completo";

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !edicao.salvando && onOpenChange(o)}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <div className="flex items-center justify-between gap-2 pr-6">
              <DialogTitle>Editar Roteiro</DialogTitle>
              {roteiro && (
                <div className="relative flex items-center gap-2">
                  <StatusBadge status={roteiro.status} />
                  {pronto && (
                    <>
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        aria-label="Mais ações"
                        aria-expanded={menuAberto}
                        onClick={() => setMenuAberto((v) => !v)}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                      {menuAberto && (
                        <div className="absolute right-0 top-9 z-10 rounded-md border bg-popover p-1 shadow-md">
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setMenuAberto(false);
                              setReprocessoAberto(true);
                            }}
                          >
                            <RefreshCw className="mr-1 h-4 w-4" /> Reprocessar
                          </Button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
            <DialogDescription>{roteiro?.headline_texto ?? "Carregando roteiro…"}</DialogDescription>
          </DialogHeader>

          {q.showSkeleton && (
            <div className="space-y-2" data-testid="editar-roteiro-skeleton">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-64 w-full" />
            </div>
          )}

          {q.isError && !roteiro && (
            <div role="alert" className="flex items-center justify-between rounded-md border p-3 text-sm">
              <span className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-destructive" /> Não foi possível carregar o roteiro.
              </span>
              <Button size="sm" variant="outline" onClick={() => q.refetch()}>
                Tentar novamente
              </Button>
            </div>
          )}

          {roteiro && !pronto && roteiro.status !== "falha" && (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground" role="status">
              <Loader2 className="h-4 w-4 animate-spin" />
              {roteiro.status === "perguntas"
                ? "Este roteiro aguarda suas respostas às perguntas estratégicas."
                : `${roteiro.etapa ?? "Gerando roteiro…"} Isto pode levar 1–2 minutos.`}
            </div>
          )}

          {roteiro?.status === "falha" && (
            <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
              {roteiro.erro ?? "Não foi possível gerar o roteiro."}
            </div>
          )}

          {roteiro && pronto && (
            <div className="space-y-4">
              <RoteiroCorpo roteiro={roteiro} edicao={edicao} onRecarregar={() => q.refetch()} />
              <FeedbackRoteiro roteiro={roteiro} />
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" disabled={edicao.salvando} onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            {pronto && (
              <Button disabled={!edicao.alterou || !edicao.valido || edicao.salvando} onClick={() => void edicao.salvar()}>
                {edicao.salvando ? "Atualizando…" : "Atualizar"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={reprocessoAberto} onOpenChange={(o) => !reprocessar.isPending && setReprocessoAberto(o)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Reprocessar Roteiro</DialogTitle>
            <DialogDescription>
              Cria um novo roteiro com as mesmas entradas, mais a informação adicional abaixo.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="roteiro-info-adicional">Informação Adicional:</Label>
            <Textarea
              id="roteiro-info-adicional"
              rows={5}
              maxLength={INFO_ADICIONAL_MAX}
              value={info}
              onChange={(e) => setInfo(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              {info.length}/{INFO_ADICIONAL_MAX} caracteres
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={reprocessar.isPending} onClick={() => setReprocessoAberto(false)}>
              Cancelar
            </Button>
            <Button disabled={reprocessar.isPending} onClick={confirmarReprocesso}>
              {reprocessar.isPending ? "Reprocessando…" : "Reprocessar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
