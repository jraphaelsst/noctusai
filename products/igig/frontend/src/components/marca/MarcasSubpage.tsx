/**
 * Clientes card → "Marcas": the cliente's N marcas (roadmap R9) + the
 * cliente's Cofre de Acessos. Replaces the standalone Central da Marca page
 * (`/marca` now redirects to `/clientes`).
 *
 * Marcas are chips on top (mobile-first: they wrap, no sideways scroll);
 * the selected marca's `MarcaPanel` renders below. "Nova marca" creates one
 * named after what the user typed (default: the cliente's name).
 */
import { useEffect, useState } from "react";
import { Button, Input, Skeleton } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { useCriarMarca, useMarcas, useRemoverMarca } from "@/hooks/useMarca";
import { describeError } from "@/lib/errors";
import { CofreAcessos } from "./CofreAcessos";
import { MarcaPanel } from "./MarcaPanel";

export function MarcasSubpage({ clienteId, clienteNome }: { clienteId: string; clienteNome: string }) {
  const { marcas, loading, isError, error } = useMarcas(clienteId);
  const criar = useCriarMarca();
  const remover = useRemoverMarca();
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [criando, setCriando] = useState(false);
  const [novoNome, setNovoNome] = useState("");
  const [aRemover, setARemover] = useState<string | null>(null);

  // Keep a valid selection: first marca by default, and fall back when the
  // selected one is removed.
  useEffect(() => {
    if (marcas.length === 0) {
      if (selecionada) setSelecionada(null);
      return;
    }
    if (!selecionada || !marcas.some((m) => m.id === selecionada)) setSelecionada(marcas[0].id);
  }, [marcas, selecionada]);

  const atual = marcas.find((m) => m.id === selecionada) ?? null;
  const marcaARemover = marcas.find((m) => m.id === aRemover) ?? null;

  function criarMarca() {
    const nome = novoNome.trim() || clienteNome || "Nova marca";
    criar.mutate(
      { cliente_id: clienteId, nome },
      {
        onSuccess: (m) => {
          setSelecionada(m.id);
          setCriando(false);
          setNovoNome("");
          toast.success("Marca criada.");
        },
        onError: (e) => toast.error(describeError(e, "Não foi possível criar a marca.")),
      },
    );
  }

  return (
    <div className="space-y-4" data-testid="marcas-subpage">
      {loading ? (
        <Skeleton className="h-40 w-full" />
      ) : isError ? (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error, "Não foi possível carregar as marcas.")}
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Marcas do cliente">
            {marcas.map((m) => (
              <button
                key={m.id}
                type="button"
                role="tab"
                aria-selected={m.id === selecionada}
                onClick={() => setSelecionada(m.id)}
                className={cn(
                  "min-h-10 max-w-full truncate rounded-full border px-3 text-sm sm:min-h-8",
                  m.id === selecionada
                    ? "border-primary bg-primary/10 text-foreground"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                {m.nome}
              </button>
            ))}
            {!criando ? (
              <Button size="sm" variant="outline" className="max-sm:h-10" onClick={() => setCriando(true)}>
                <Plus className="mr-1 h-4 w-4" /> Nova marca
              </Button>
            ) : null}
          </div>

          {criando ? (
            <form
              className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-border p-3"
              onSubmit={(e) => {
                e.preventDefault();
                criarMarca();
              }}
            >
              <Input
                autoFocus
                aria-label="Nome da nova marca"
                placeholder={clienteNome || "Nome da marca"}
                value={novoNome}
                onChange={(e) => setNovoNome(e.target.value)}
                className="min-w-0 flex-1 max-sm:h-10"
              />
              <Button type="submit" className="max-sm:h-10" disabled={criar.isPending}>
                {criar.isPending ? "Criando…" : "Criar"}
              </Button>
              <Button type="button" variant="ghost" className="max-sm:h-10" onClick={() => setCriando(false)}>
                Cancelar
              </Button>
            </form>
          ) : null}

          {marcas.length === 0 && !criando ? (
            <div className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
              Nenhuma marca cadastrada para este cliente.
              <div className="mt-2">
                <Button size="sm" className="max-sm:h-10" onClick={() => setCriando(true)}>
                  <Plus className="mr-1 h-4 w-4" /> Criar marca
                </Button>
              </div>
            </div>
          ) : null}

          {atual ? (
            <div className="rounded-lg border border-border bg-card p-4">
              <MarcaPanel key={atual.id} marca={atual} onRemover={() => setARemover(atual.id)} />
            </div>
          ) : null}
        </>
      )}

      <CofreAcessos clienteId={clienteId} />

      <ConfirmDialog
        open={!!marcaARemover}
        title="Remover marca"
        description={
          <p>
            Remover a marca <strong>{marcaARemover?.nome}</strong>? Paleta, tom de voz, linhas editoriais e
            personas dela são apagados. As pautas continuam, sem marca; o cofre do cliente não é afetado.
          </p>
        }
        confirmLabel={remover.isPending ? "Removendo…" : "Remover"}
        busy={remover.isPending}
        onConfirm={() =>
          marcaARemover &&
          remover.mutate(marcaARemover.id, {
            onSuccess: () => {
              setARemover(null);
              toast.success("Marca removida.");
            },
            onError: (e) => toast.error(describeError(e, "Não foi possível remover a marca.")),
          })
        }
        onCancel={() => setARemover(null)}
      />
    </div>
  );
}
