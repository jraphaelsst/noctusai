/**
 * Assuntos Virais tab of Minha Pesquisa (contract wave2 §4.5). Approved = pill
 * cloud, Pendente = card list with Aprovar/Rejeitar. Loading follows the
 * two-signal rule (showSkeleton / isRefreshing), never `.isLoading`.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Loader2, RefreshCw, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AssuntoFontesModal } from "@/components/pesquisa/AssuntoFontesModal";
import { ConfirmarModal } from "@/components/pesquisa/ConfirmarModal";
import { compactoPtBr } from "@/components/pesquisa/format";
import {
  useAdicionarAssuntos,
  useAprovarAssunto,
  useAssuntosCounts,
  useAssuntosEmMassa,
  useAssuntosVirais,
  useEsvaziarAssuntos,
  useExcluirAssunto,
  useRejeitarAssunto,
  type AssuntoStatus,
  type ViralTopic,
} from "@/hooks/useAssuntosVirais";

const BULK_CHUNK = 500;
export const EXTRAIR_ASSUNTOS_HREF =
  "/media-creation/pesquisa/extrair?tipo=assuntos_virais";

type Confirmacao =
  | { tipo: "remover"; assunto: ViralTopic }
  | { tipo: "excluir-selecionados" }
  | { tipo: "esvaziar" };

interface Props {
  marcaId: string;
}

export function AssuntosVirais({ marcaId }: Props) {
  const [status, setStatus] = useState<AssuntoStatus>("approved");
  const [novo, setNovo] = useState("");
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [confirmar, setConfirmar] = useState<Confirmacao | null>(null);
  const [aberto, setAberto] = useState<ViralTopic | null>(null);

  const countsQ = useAssuntosCounts(marcaId);
  const listaQ = useAssuntosVirais(marcaId, status);
  const { items, total } = listaQ;

  const adicionar = useAdicionarAssuntos();
  const aprovar = useAprovarAssunto();
  const rejeitar = useRejeitarAssunto();
  const excluir = useExcluirAssunto();
  const emMassa = useAssuntosEmMassa();
  const esvaziar = useEsvaziarAssuntos();

  // Selection never outlives the view it was made in.
  useEffect(() => {
    setSelecionados(new Set());
  }, [marcaId, status]);

  function alternar(id: string) {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submeterNovo() {
    const topic = novo.trim();
    if (!topic) {
      toast.error("Digite um tópico válido!");
      return;
    }
    try {
      const r = await adicionar.mutateAsync({
        marca_id: marcaId,
        topics: [topic],
      });
      toast.success(
        r.saved > 0 ? "Assunto viral adicionado." : "Este assunto já existe.",
      );
      setNovo("");
    } catch {
      toast.error("Não foi possível adicionar o assunto.");
    }
  }

  async function decidir(a: ViralTopic, acao: "aprovar" | "rejeitar") {
    try {
      if (acao === "aprovar") await aprovar.mutateAsync(a.id);
      else await rejeitar.mutateAsync(a.id);
      toast.success(
        acao === "aprovar" ? "Assunto aprovado." : "Assunto rejeitado.",
      );
    } catch {
      toast.error("Não foi possível atualizar o assunto.");
    }
  }

  async function executarEmMassa(action: "approve" | "reject" | "delete") {
    const ids = [...selecionados];
    try {
      let afetados = 0;
      for (let i = 0; i < ids.length; i += BULK_CHUNK) {
        const r = await emMassa.mutateAsync({
          marca_id: marcaId,
          action,
          ids: ids.slice(i, i + BULK_CHUNK),
        });
        afetados += r.affected;
      }
      toast.success(`${afetados} assunto(s) atualizado(s).`);
      setSelecionados(new Set());
    } catch {
      toast.error("Não foi possível concluir a ação em massa.");
    } finally {
      setConfirmar(null);
    }
  }

  async function executarConfirmacao() {
    if (!confirmar) return;
    if (confirmar.tipo === "excluir-selecionados")
      return executarEmMassa(status === "pending" ? "reject" : "delete");
    try {
      if (confirmar.tipo === "remover") {
        await excluir.mutateAsync(confirmar.assunto.id);
        toast.success("Tópico removido.");
      } else {
        const r = await esvaziar.mutateAsync({ marca_id: marcaId, status });
        toast.success(`${r.deleted} assunto(s) removido(s).`);
        setSelecionados(new Set());
      }
    } catch {
      toast.error("Não foi possível concluir a exclusão.");
    } finally {
      setConfirmar(null);
    }
  }

  const todos = items.length > 0 && items.every((i) => selecionados.has(i.id));
  const statusRotulo = status === "approved" ? "aprovados" : "pendentes";
  const confirmando =
    excluir.isPending || esvaziar.isPending || emMassa.isPending;

  return (
    <div className="space-y-5" data-testid="assuntos-virais">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border bg-card p-4">
        <div>
          <h2 className="text-sm font-semibold">Extrair assuntos virais</h2>
          <p className="text-sm text-muted-foreground">
            Use esta opção para extrair assuntos virais dos seus posts e
            adicionar aos seus assuntos virais.
          </p>
        </div>
        <Button asChild>
          <Link to={EXTRAIR_ASSUNTOS_HREF}>
            <Sparkles className="mr-1.5 h-4 w-4" />
            Extrair Assuntos Virais
          </Link>
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div
          className="inline-flex rounded-md border"
          role="group"
          aria-label="Status dos assuntos"
        >
          <Button
            size="sm"
            variant={status === "approved" ? "default" : "ghost"}
            onClick={() => setStatus("approved")}
          >
            Aprovado
          </Button>
          <Button
            size="sm"
            variant={status === "pending" ? "default" : "ghost"}
            onClick={() => setStatus("pending")}
          >
            Pendente ({countsQ.data?.pending ?? 0})
          </Button>
        </div>
        <span className="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
          {listaQ.isRefreshing && (
            <span role="status" className="flex items-center gap-1">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Atualizando…
            </span>
          )}
          {total} {total === 1 ? "assunto" : "assuntos"}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            aria-label="Selecionar todos"
            checked={todos}
            onCheckedChange={(c) =>
              setSelecionados(
                c === true ? new Set(items.map((i) => i.id)) : new Set(),
              )
            }
          />
          Selecionar todos
        </label>
        {status === "pending" && (
          <Button
            size="sm"
            disabled={selecionados.size === 0 || emMassa.isPending}
            onClick={() => void executarEmMassa("approve")}
          >
            Aprovar selecionados ({selecionados.size})
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          disabled={selecionados.size === 0}
          onClick={() => setConfirmar({ tipo: "excluir-selecionados" })}
        >
          Excluir selecionados ({selecionados.size})
        </Button>
        <Button
          size="sm"
          variant="destructive"
          disabled={total === 0}
          onClick={() => setConfirmar({ tipo: "esvaziar" })}
        >
          Esvaziar
        </Button>
      </div>

      {status === "approved" && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void submeterNovo();
          }}
        >
          <Input
            aria-label="Novo assunto viral"
            placeholder="Digite um novo assunto viral..."
            maxLength={255}
            value={novo}
            onChange={(e) => setNovo(e.target.value)}
          />
          <Button type="submit" disabled={adicionar.isPending}>
            Adicionar
          </Button>
        </form>
      )}

      {listaQ.showSkeleton ? (
        <div
          className="space-y-2"
          aria-busy="true"
          data-testid="assuntos-skeleton"
        >
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : listaQ.isError && !listaQ.data ? (
        <div
          role="alert"
          className="flex flex-col items-center gap-3 py-12 text-sm"
        >
          <AlertCircle className="h-6 w-6 text-destructive" />
          Não foi possível carregar os assuntos virais.
          <Button
            variant="outline"
            size="sm"
            onClick={() => void listaQ.refetch()}
          >
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Tentar novamente
          </Button>
        </div>
      ) : items.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          {status === "pending"
            ? "Nenhum item pendente"
            : "Nenhum assunto viral aprovado ainda."}
        </p>
      ) : status === "approved" ? (
        <div className="flex flex-wrap gap-2" data-testid="assuntos-pills">
          {items.map((a) => (
            <div
              key={a.id}
              className="flex items-center gap-2 rounded-full border bg-card py-1 pl-3 pr-1 text-sm"
            >
              <Checkbox
                aria-label={`Selecionar assunto: ${a.topic}`}
                checked={selecionados.has(a.id)}
                onCheckedChange={() => alternar(a.id)}
              />
              <button
                type="button"
                className="text-left hover:underline"
                onClick={() => setAberto(a)}
              >
                {a.topic}
              </button>
              <span className="text-xs text-muted-foreground">
                {a.total_plays != null
                  ? `${compactoPtBr(a.total_plays)} Views`
                  : "Manual"}
              </span>
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6 rounded-full"
                aria-label={`Remover: ${a.topic}`}
                onClick={() => setConfirmar({ tipo: "remover", assunto: a })}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-2" data-testid="assuntos-pendentes">
          {items.map((a) => (
            <div
              key={a.id}
              className="flex items-center gap-3 overflow-hidden rounded-md border bg-card pr-3"
            >
              <div className="w-1 self-stretch bg-orange-500" aria-hidden />
              <Checkbox
                aria-label={`Selecionar assunto: ${a.topic}`}
                checked={selecionados.has(a.id)}
                onCheckedChange={() => alternar(a.id)}
              />
              <button
                type="button"
                className="min-w-0 flex-1 py-3 text-left"
                title="Clique para ver os virais"
                onClick={() => setAberto(a)}
              >
                <p className="break-words text-sm">{a.topic}</p>
                <p className="text-xs text-muted-foreground">
                  {a.total_plays != null
                    ? `${compactoPtBr(a.total_plays)} Views`
                    : "Manual"}
                </p>
              </button>
              <Badge variant="secondary">Pendente</Badge>
              <Button size="sm" onClick={() => void decidir(a, "aprovar")}>
                Aprovar
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => void decidir(a, "rejeitar")}
              >
                Rejeitar
              </Button>
            </div>
          ))}
        </div>
      )}

      {listaQ.hasNextPage && (
        <div className="flex justify-center">
          <Button
            variant="outline"
            disabled={listaQ.isFetchingNextPage}
            onClick={() => void listaQ.fetchNextPage()}
          >
            {listaQ.isFetchingNextPage ? "Carregando…" : "Ver mais"}
          </Button>
        </div>
      )}

      <AssuntoFontesModal assunto={aberto} onClose={() => setAberto(null)} />

      <ConfirmarModal
        open={confirmar !== null}
        onOpenChange={(o) => !o && setConfirmar(null)}
        pendente={confirmando}
        titulo={
          confirmar?.tipo === "esvaziar"
            ? "Esvaziar assuntos virais?"
            : confirmar?.tipo === "excluir-selecionados"
              ? "Excluir assuntos selecionados?"
              : "Remover tópico?"
        }
        descricao={
          confirmar?.tipo === "esvaziar"
            ? `Você realmente deseja esvaziar TODOS os assuntos virais ${statusRotulo}? Esta ação não pode ser desfeita.`
            : confirmar?.tipo === "excluir-selecionados"
              ? `${selecionados.size} assunto(s) serão removidos.`
              : "Você realmente deseja remover este tópico viral?"
        }
        rotuloConfirmar={
          confirmar?.tipo === "esvaziar" ? "Esvaziar" : "Excluir"
        }
        onConfirmar={() => void executarConfirmacao()}
      />
    </div>
  );
}
