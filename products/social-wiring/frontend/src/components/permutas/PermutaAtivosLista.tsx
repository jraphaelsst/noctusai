/**
 * PermutaAtivosLista — the swap REGISTRY tab of /permutas: list, filter,
 * register, edit and remove `permuta_ativos`.
 *
 * Before this existed the registry was frozen at the legacy import
 * (2026-09-06): the page could only run the engine over rows nobody could
 * add to or correct.
 *
 * Loading follows the two-signal rule (→ KB § PATTERNS/frontend/
 * lying-loading-state.md): the skeleton only before the first answer, a
 * spinner beside the title on refetch, and the list stays mounted.
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Loader2, Pencil, Plus, Search, Trash2 } from "lucide-react";

import {
  NATUREZA_LABELS,
  STATUS_ATIVO_LABELS,
  type AtivoPayload,
  type Natureza,
  type PermutaAtivo,
  type StatusAtivo,
  useAtualizarAtivo,
  useCriarAtivo,
  usePermutaAtivos,
  useRemoverAtivo,
} from "@/hooks/usePermutas";
import { PermutaAtivoDialog } from "@/components/permutas/PermutaAtivoDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
import { TableSkeleton } from "@noctusai/lib/design-system";

const BRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});

/** NUMERIC columns can arrive as strings from PostgREST. */
function moeda(v: number | string | null | undefined): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? BRL.format(n) : "—";
}

function erroDoServidor(err: unknown, fallback: string): string {
  const msg = (err as { message?: string } | null)?.message;
  return msg && msg.trim() ? msg : fallback;
}

/** What the row IS, catalog first for a pointer row. */
function resumo(a: PermutaAtivo) {
  const cat = a.catalogo ?? null;
  const ref = a.imovel_codigo || a.codigo || "—";
  const titulo =
    cat?.titulo || cat?.categoria || a.tipo_imovel || NATUREZA_LABELS[a.natureza] || "Permuta";
  const local = [cat?.bairro ?? a.bairro, cat?.cidade ?? a.cidade, cat?.uf ?? a.uf]
    .filter(Boolean)
    .join(", ");
  const valor = cat?.valor_venda ?? a.valor;
  return { ref, titulo, local, valor, foraDoCatalogo: a.natureza === "imovel" && a.catalogo === null };
}

function faixa(a: PermutaAtivo): string | null {
  const min = a.faixa_preco_min;
  const max = a.faixa_preco_max;
  if (min == null && max == null) return null;
  if (min != null && max != null) return `${moeda(min)} – ${moeda(max)}`;
  return min != null ? `a partir de ${moeda(min)}` : `até ${moeda(max)}`;
}

function normalizar(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function PermutaAtivosLista() {
  const [natureza, setNatureza] = useState<Natureza | undefined>(undefined);
  const [incluirInativos, setIncluirInativos] = useState(false);
  const [busca, setBusca] = useState("");
  const [dialogAberto, setDialogAberto] = useState(false);
  const [editando, setEditando] = useState<PermutaAtivo | null>(null);
  const [removendo, setRemovendo] = useState<PermutaAtivo | null>(null);

  const q = usePermutaAtivos(natureza, { incluirInativos });
  const criar = useCriarAtivo();
  const atualizar = useAtualizarAtivo();
  const remover = useRemoverAtivo();

  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;

  const filtrados = useMemo(() => {
    const itens = q.data ?? [];
    const termo = normalizar(busca.trim());
    if (!termo) return itens;
    return itens.filter((a) => {
      const r = resumo(a);
      const alvo = [
        r.ref,
        r.titulo,
        r.local,
        a.proprietario_nome,
        a.proprietario_telefone,
        a.observacoes,
      ]
        .filter(Boolean)
        .join(" ");
      return normalizar(alvo).includes(termo);
    });
  }, [q.data, busca]);

  function abrirNovo() {
    setEditando(null);
    setDialogAberto(true);
  }

  function abrirEdicao(a: PermutaAtivo) {
    setEditando(a);
    setDialogAberto(true);
  }

  async function handleSalvar(payload: AtivoPayload) {
    // Errors propagate to the dialog (shown inline) AND get a toast.
    try {
      if (editando) {
        await atualizar.mutateAsync({ ativoId: editando.id, body: payload });
        toast.success("Permuta atualizada", {
          description: "Gere os embeddings de novo para a análise semântica.",
        });
      } else {
        await criar.mutateAsync(payload as AtivoPayload & { natureza: Natureza });
        toast.success("Permuta cadastrada");
      }
      setDialogAberto(false);
    } catch (err) {
      toast.error(editando ? "Erro ao atualizar permuta" : "Erro ao cadastrar permuta", {
        description: erroDoServidor(err, "Tente novamente"),
      });
      throw err;
    }
  }

  async function handleRemover() {
    if (!removendo) return;
    try {
      await remover.mutateAsync(removendo.id);
      toast.success("Permuta removida");
      setRemovendo(null);
    } catch (err) {
      toast.error("Erro ao remover permuta", {
        description: erroDoServidor(err, "Tente novamente"),
      });
    }
  }

  return (
    <div className="space-y-4" data-testid="permuta-ativos-lista">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={natureza === undefined ? "default" : "outline"}
            onClick={() => setNatureza(undefined)}
          >
            Todas
          </Button>
          {(Object.keys(NATUREZA_LABELS) as Natureza[]).map((n) => (
            <Button
              key={n}
              size="sm"
              variant={natureza === n ? "default" : "outline"}
              onClick={() => setNatureza(n)}
            >
              {NATUREZA_LABELS[n]}
            </Button>
          ))}
          {isRefreshing && (
            <Loader2
              className="h-4 w-4 animate-spin self-center text-muted-foreground"
              data-testid="permuta-ativos-refreshing"
            />
          )}
        </div>
        <Button onClick={abrirNovo}>
          <Plus className="mr-2 h-4 w-4" />
          Nova permuta
        </Button>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Buscar por código, proprietário, bairro ou descrição…"
            aria-label="Buscar permutas"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={incluirInativos}
            onChange={(e) => setIncluirInativos(e.target.checked)}
          />
          Incluir pausadas, concluídas e arquivadas
        </label>
      </div>

      {showSkeleton ? (
        <TableSkeleton rows={5} />
      ) : q.isError ? (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            Não foi possível carregar as permutas.{" "}
            {erroDoServidor(q.error, "Tente recarregar a página.")}
          </CardContent>
        </Card>
      ) : filtrados.length === 0 ? (
        <Card>
          <CardContent className="space-y-2 p-6 text-sm text-muted-foreground">
            {busca.trim() ? (
              <p>Nenhuma permuta corresponde a “{busca.trim()}”.</p>
            ) : (
              <>
                <p>Nenhum imóvel em permuta{natureza ? ` em “${NATUREZA_LABELS[natureza]}”` : ""}.</p>
                <p>Cadastre um imóvel aberto a permuta para que o motor encontre pares.</p>
              </>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            {filtrados.length} registro{filtrados.length === 1 ? "" : "s"}
          </p>
          {filtrados.map((a) => {
            const r = resumo(a);
            const fx = faixa(a);
            const status = (a.status as StatusAtivo) in STATUS_ATIVO_LABELS
              ? STATUS_ATIVO_LABELS[a.status as StatusAtivo]
              : a.status;
            return (
              <Card key={a.id} data-testid="permuta-ativo-linha">
                <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm">{r.ref}</span>
                      <span className="font-medium">{r.titulo}</span>
                      <Badge variant="outline">{NATUREZA_LABELS[a.natureza] ?? a.natureza}</Badge>
                      {a.status !== "ativo" && <Badge variant="secondary">{status}</Badge>}
                      {r.foraDoCatalogo && (
                        <Badge variant="outline" className="text-warning-foreground">
                          Fora do catálogo
                        </Badge>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-x-3 text-sm text-muted-foreground">
                      {r.local && <span>{r.local}</span>}
                      <span className="font-semibold tabular-nums text-foreground">{moeda(r.valor)}</span>
                      {fx && <span>Procura: {fx}</span>}
                    </div>
                    {a.proprietario_nome && (
                      <div className="text-sm text-muted-foreground">
                        Proprietário: {a.proprietario_nome}
                        {a.proprietario_telefone ? ` · ${a.proprietario_telefone}` : ""}
                      </div>
                    )}
                    {(a.observacoes || a.interesses_descricao) && (
                      <p className="border-l-2 pl-2 text-sm italic text-muted-foreground">
                        “{a.observacoes || a.interesses_descricao}”
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Editar ${r.ref}`}
                      onClick={() => abrirEdicao(a)}
                    >
                      <Pencil className="mr-1 h-3.5 w-3.5" />
                      Editar
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Remover ${r.ref}`}
                      onClick={() => setRemovendo(a)}
                    >
                      <Trash2 className="mr-1 h-3.5 w-3.5" />
                      Remover
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <PermutaAtivoDialog
        open={dialogAberto}
        onOpenChange={setDialogAberto}
        ativo={editando}
        salvando={criar.isPending || atualizar.isPending}
        onSalvar={handleSalvar}
      />

      <AlertDialog
        open={removendo !== null}
        onOpenChange={(aberto) => {
          if (!aberto && !remover.isPending) setRemovendo(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover esta permuta?</AlertDialogTitle>
            <AlertDialogDescription>
              {removendo ? `${resumo(removendo).ref} — ` : ""}
              os critérios e todos os matches deste registro também serão
              apagados, inclusive os que já têm decisão. Para apenas tirá-lo do
              matching, edite e mude o status para Pausado ou Arquivado.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remover.isPending}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              disabled={remover.isPending}
              onClick={(e) => {
                // Keep the dialog open until the request settles.
                e.preventDefault();
                void handleRemover();
              }}
            >
              {remover.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default PermutaAtivosLista;
