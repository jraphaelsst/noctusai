/**
 * Cérebros Personalizados (`/media-creation/cerebro`) — per-marca brains:
 * 4 Sistema + custom, bio card, create modal. Contract: cerebro-contract.md §6.
 * Loading: two signals off `data`, never `.isLoading` (lying-loading-state.md).
 */
import { useEffect, useState } from "react";
import { AlertCircle, Brain, Loader2, Plus, RefreshCw } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { BioPerfilCard } from "@/components/cerebro/BioPerfilCard";
import { STATUS_CEREBRO_ROTULO, mensagemErro } from "@/components/cerebro/labels";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { useCerebroBrains, useCriarBrain } from "@/hooks/useCerebro";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { BrainSummary } from "@/types/cerebro";

const CEREBRO = "/media-creation/cerebro";

/** Sistema brain never touched yet starts at the questionnaire; everything else opens the editor. */
export function destinoDoCerebro(b: BrainSummary): string {
  const semResposta = b.kind === "sistema" && (b.answered ?? 0) === 0 && b.content_chars === 0;
  return semResposta ? `${CEREBRO}/${b.id}/perguntas` : `${CEREBRO}/${b.id}`;
}

export default function CerebroLista() {
  const navigate = useNavigate();
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);
  const brainsQ = useCerebroBrains(marcaId);
  const brains = brainsQ.data ?? [];
  const [criarAberto, setCriarAberto] = useState(false);

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Cérebros Personalizados</h1>
          <p className="text-sm text-muted-foreground">Segundo cérebro</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
          <Button variant="outline" asChild>
            <Link to={`${CEREBRO}/extracoes`}>Minhas extrações</Link>
          </Button>
          <Button onClick={() => setCriarAberto(true)} disabled={!marcaId}>
            <Plus className="mr-1.5 h-4 w-4" />
            Criar Cérebro
          </Button>
        </div>
      </header>

      {marcasQ.isPending && !marcasQ.data ? (
        <Skeleton className="h-40 w-full" />
      ) : marcasQ.isError && !marcasQ.data ? (
        <ErroBloco texto="Não foi possível carregar as marcas." onRetry={() => void marcasQ.refetch()} />
      ) : !marcaId ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Cadastre uma marca em Clientes para criar seus cérebros.
        </p>
      ) : (
        <>
          <BioPerfilCard marcaId={marcaId} />

          {brainsQ.isRefreshing && (
            <span role="status" className="flex items-center gap-1 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Atualizando…
            </span>
          )}

          {brainsQ.showSkeleton ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-busy="true" data-testid="cerebro-skeleton">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-36 w-full" />
              ))}
            </div>
          ) : brainsQ.isError && !brainsQ.data ? (
            <ErroBloco texto="Não foi possível carregar os cérebros." onRetry={() => void brainsQ.refetch()} />
          ) : brains.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">Nenhum cérebro encontrado.</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {brains.map((b) => (
                <article key={b.id} className="flex flex-col gap-3 rounded-lg border bg-card p-4" data-testid="cerebro-card">
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="flex items-center gap-2 text-base font-semibold">
                      <Brain className="h-4 w-4 text-muted-foreground" />
                      {b.name}
                    </h2>
                    {b.kind === "sistema" && <Badge variant="secondary">Sistema</Badge>}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <Badge variant="outline">{STATUS_CEREBRO_ROTULO[b.status]}</Badge>
                    {b.total_questions != null && (
                      <span>
                        {b.answered ?? 0} de {b.total_questions} respondidas
                      </span>
                    )}
                  </div>
                  <Button className="mt-auto" variant="outline" asChild>
                    <Link to={destinoDoCerebro(b)}>Acessar Cérebro</Link>
                  </Button>
                </article>
              ))}
            </div>
          )}
        </>
      )}

      {marcaId && (
        <CriarCerebroModal
          open={criarAberto}
          onOpenChange={setCriarAberto}
          marcaId={marcaId}
          onCriado={(id) => navigate(`${CEREBRO}/${id}`)}
        />
      )}
    </div>
  );
}

function CriarCerebroModal({
  open,
  onOpenChange,
  marcaId,
  onCriado,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  marcaId: string;
  onCriado: (id: string) => void;
}) {
  const [nome, setNome] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const criar = useCriarBrain();

  useEffect(() => {
    if (open) {
      setNome("");
      setErro(null);
    }
  }, [open]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const name = nome.trim();
    if (!name) {
      setErro("Informe o nome do cérebro.");
      return;
    }
    try {
      const b = await criar.mutateAsync({ marca_id: marcaId, name });
      onOpenChange(false);
      toast.success("Cérebro criado.");
      onCriado(b.id);
    } catch (err) {
      setErro(mensagemErro(err, "Não foi possível criar o cérebro."));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={(e) => void onSubmit(e)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Criar Cérebro Personalizado</DialogTitle>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="cerebro-nome">Nome do Cérebro:</Label>
            <Input
              id="cerebro-nome"
              value={nome}
              maxLength={80}
              placeholder="Ex: Reels Instagram"
              onChange={(e) => setNome(e.target.value)}
              autoComplete="off"
            />
            {erro && (
              <p role="alert" className="text-sm text-destructive">
                {erro}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={criar.isPending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={criar.isPending}>
              {criar.isPending ? "Criando…" : "Criar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ErroBloco({ texto, onRetry }: { texto: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 py-16 text-sm">
      <AlertCircle className="h-6 w-6 text-destructive" />
      {texto}
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
        Tentar novamente
      </Button>
    </div>
  );
}
