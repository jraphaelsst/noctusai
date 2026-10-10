/**
 * Campanhas — which imóveis a Meta campaign / adset / ad / form stands for
 * (CONTRACT §1.1). Resolution at intake reads this registry.
 *
 * States: skeleton (`isPending && !data`) / error / empty / list, with an
 * `isRefreshing` indicator that never replaces the list. Delete is a soft
 * delete behind a confirm.
 *
 * Route: /campanhas (status_pagina 'campanhas', migration 218).
 */
import { useState } from "react";
import { AlertCircle, Loader2, Megaphone, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { mensagemDoErro } from "@/components/card/mensagemDoErro";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCampanhaMutations, useCampanhasLista, type Campanha } from "@/hooks/useCampanhas";

import { CampanhaDialog, NIVEL_LABEL } from "./CampanhaDialog";

export default function Campanhas() {
  const lista = useCampanhasLista();
  const { remover } = useCampanhaMutations();
  const [editando, setEditando] = useState<Campanha | "nova" | null>(null);
  const [excluindo, setExcluindo] = useState<Campanha | null>(null);

  function confirmarExclusao() {
    if (!excluindo) return;
    remover.mutate(
      { id: excluindo.id },
      {
        onSuccess: () => {
          toast.success("Campanha excluída.");
          setExcluindo(null);
        },
        onError: (err) => {
          toast.error(mensagemDoErro(err, "Não foi possível excluir a campanha."));
          setExcluindo(null);
        },
      },
    );
  }

  const campanhas = lista.data ?? [];

  return (
    <div className="space-y-6 p-6" data-testid="campanhas-page">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            Campanhas
            {lista.isRefreshing && (
              <Loader2
                className="h-4 w-4 animate-spin text-muted-foreground"
                data-testid="campanhas-atualizando"
              />
            )}
          </h1>
          <p className="text-sm text-muted-foreground">
            Ligue campanhas, conjuntos, anúncios e formulários do Meta aos imóveis anunciados.
          </p>
        </div>
        <Button onClick={() => setEditando("nova")} data-testid="campanhas-nova">
          <Plus className="mr-1 h-4 w-4" />
          Nova campanha
        </Button>
      </div>

      {lista.showSkeleton ? (
        <div className="space-y-3" data-testid="campanhas-skeleton">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : lista.isError && !lista.data ? (
        <div
          className="flex items-center gap-2 rounded-md border border-destructive/40 p-4 text-sm text-destructive"
          role="alert"
          data-testid="campanhas-erro"
        >
          <AlertCircle className="h-4 w-4" />
          {mensagemDoErro(lista.error, "Não foi possível carregar as campanhas.")}
          <Button variant="outline" size="sm" className="ml-auto" onClick={() => lista.refetch()}>
            Tentar de novo
          </Button>
        </div>
      ) : campanhas.length === 0 ? (
        <div
          className="flex flex-col items-center gap-3 rounded-md border border-dashed p-10 text-center"
          data-testid="campanhas-vazio"
        >
          <Megaphone className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Nenhuma campanha cadastrada. Sem ela, o imóvel do lead só vem do campo REF do formulário.
          </p>
          <Button onClick={() => setEditando("nova")}>Criar a primeira campanha</Button>
        </div>
      ) : (
        <ul className="space-y-3" data-testid="campanhas-lista">
          {campanhas.map((c) => (
            <li key={c.id}>
              <Card data-testid={`campanha-${c.id}`}>
                <CardContent className="flex items-start gap-4 p-4">
                  <div className="min-w-0 flex-1 space-y-2">
                    <p className="font-medium">{c.nome}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {c.imoveis.length === 0 && (
                        <span className="text-xs text-muted-foreground">Sem imóveis</span>
                      )}
                      {c.imoveis.map((i) => (
                        <Badge key={i.codigo} variant="secondary" title={i.titulo ?? undefined}>
                          {i.codigo}
                        </Badge>
                      ))}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {c.veiculacoes.length === 0 && (
                        <span className="text-xs text-muted-foreground">Sem veiculações</span>
                      )}
                      {c.veiculacoes.map((v) => (
                        <Badge key={v.id} variant="outline">
                          {NIVEL_LABEL[v.nivel]} · {v.ref_codigo}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Editar ${c.nome}`}
                    onClick={() => setEditando(c)}
                    data-testid={`campanha-editar-${c.id}`}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Excluir ${c.nome}`}
                    onClick={() => setExcluindo(c)}
                    data-testid={`campanha-excluir-${c.id}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {editando && (
        <CampanhaDialog
          key={editando === "nova" ? "nova" : editando.id}
          open
          campanha={editando === "nova" ? null : editando}
          onClose={() => setEditando(null)}
        />
      )}

      <AlertDialog open={!!excluindo} onOpenChange={(o) => !o && setExcluindo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir campanha?</AlertDialogTitle>
            <AlertDialogDescription>
              “{excluindo?.nome}” deixa de resolver leads do Meta. Os atendimentos já criados não
              mudam.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                confirmarExclusao();
              }}
              data-testid="campanha-excluir-confirmar"
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
