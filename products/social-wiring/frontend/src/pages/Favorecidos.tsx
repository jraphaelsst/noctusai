/**
 * Favorecidos — the org's registry of payees (who receives a parcela). A
 * cadastro alongside Imobiliárias / Testemunhas: the card SELECTS from here
 * (Negociação → Favorecidos) instead of free-typing bank data per deal.
 *
 * 🔴 LGPD-first: the list shows MASKED CPF/CNPJ and PIX only; the clear values
 * appear solely inside the edit dialog (`FavorecidoDialog`). Search is by NAME —
 * a document-looking term is neither sent to the server nor placed in a URL.
 * Deactivate is a soft delete (the row stays, so past contracts keep their
 * payee); an inactive row can be reactivated here.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, Loader2, Pencil, Plus, Power, PowerOff, Search } from "lucide-react";

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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FavorecidoDialog } from "@/components/favorecidos/FavorecidoDialog";
import {
  PIX_TIPOS,
  termoDeBuscaSeguro,
  useDeactivateFavorecidoRegistro,
  useFavorecidos,
  useUpdateFavorecidoRegistro,
  type FavorecidoFiltroAtivo,
  type FavorecidoResumo,
} from "@/hooks/useFavorecidosRegistro";
import { mensagemErroServidor } from "@/lib/erroServidor";

const BUSCA_DEBOUNCE_MS = 250;

function rotuloPix(tipo: string | null): string {
  return PIX_TIPOS.find((t) => t.value === tipo)?.label ?? "PIX";
}

export default function Favorecidos() {
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [filtro, setFiltro] = useState<FavorecidoFiltroAtivo>("ativos");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editandoId, setEditandoId] = useState<string | null>(null);
  const [desativando, setDesativando] = useState<FavorecidoResumo | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setBuscaAplicada(busca), BUSCA_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [busca]);

  const termoSeguro = termoDeBuscaSeguro(busca);
  const query = useFavorecidos({ q: buscaAplicada, ativo: filtro });
  const desativar = useDeactivateFavorecidoRegistro();
  const atualizar = useUpdateFavorecidoRegistro();

  // 🔴 Two signals, never `isLoading`. → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;
  const items = query.data?.items ?? [];

  function abrirNovo() {
    setEditandoId(null);
    setDialogOpen(true);
  }

  function abrirEdicao(f: FavorecidoResumo) {
    setEditandoId(f.id);
    setDialogOpen(true);
  }

  function confirmarDesativar() {
    if (!desativando) return;
    desativar.mutate(desativando.id, {
      onSuccess: () => {
        toast.success("Favorecido desativado.");
        setDesativando(null);
      },
      onError: (err) =>
        toast.error(mensagemErroServidor(err, "Não foi possível desativar o favorecido.")),
    });
  }

  function reativar(f: FavorecidoResumo) {
    atualizar.mutate(
      { id: f.id, patch: { ativo: true } },
      {
        onSuccess: () => toast.success("Favorecido reativado."),
        onError: (err) =>
          toast.error(mensagemErroServidor(err, "Não foi possível reativar o favorecido.")),
      },
    );
  }

  return (
    <div className="space-y-6 p-6" data-testid="favorecidos-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Favorecidos</h1>
          <p className="text-sm text-muted-foreground">
            Quem recebe as parcelas — cadastrados uma vez e escolhidos por
            negociação na aba Favorecidos do card. Dados sensíveis aparecem
            mascarados; o valor completo só no diálogo de edição.
          </p>
        </div>
        <Button onClick={abrirNovo} data-testid="favorecidos-novo">
          <Plus className="mr-1 h-4 w-4" />
          Novo favorecido
        </Button>
      </div>

      <Card>
        <CardHeader className="space-y-3">
          <CardTitle className="text-base">Cadastro</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-60 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-8"
                placeholder="Buscar por nome…"
                aria-label="Buscar favorecido por nome"
                autoComplete="off"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                data-testid="favorecidos-busca"
              />
            </div>
            <div className="w-40">
              <Select
                value={filtro}
                onValueChange={(v) => setFiltro(v as FavorecidoFiltroAtivo)}
              >
                <SelectTrigger aria-label="Situação" data-testid="favorecidos-filtro">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ativos">Ativos</SelectItem>
                  <SelectItem value="inativos">Inativos</SelectItem>
                  <SelectItem value="todos">Todos</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {termoSeguro === null && (
            <p
              className="text-xs text-warning-foreground"
              data-testid="favorecidos-busca-documento"
            >
              A busca é por nome — não digite CPF/CNPJ aqui.
            </p>
          )}
        </CardHeader>
        <CardContent className="space-y-2">
          {isRefreshing && (
            <p
              className="text-xs text-muted-foreground"
              data-testid="favorecidos-refreshing"
            >
              Atualizando…
            </p>
          )}
          {showSkeleton ? (
            <p
              className="flex items-center gap-2 text-sm text-muted-foreground"
              data-testid="favorecidos-skeleton"
            >
              <Loader2 className="h-4 w-4 animate-spin" />
              Carregando favorecidos…
            </p>
          ) : query.isError && !query.data ? (
            <div className="space-y-3" data-testid="favorecidos-erro">
              <p className="flex items-center gap-1.5 text-sm text-destructive">
                <AlertCircle className="h-4 w-4" />
                Não foi possível carregar os favorecidos.
              </p>
              <Button size="sm" variant="outline" onClick={() => query.refetch()}>
                Tentar novamente
              </Button>
            </div>
          ) : items.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="favorecidos-vazio">
              {buscaAplicada || filtro !== "ativos"
                ? "Nenhum favorecido encontrado com esses filtros."
                : "Nenhum favorecido cadastrado. Use “Novo favorecido” para começar."}
            </p>
          ) : (
            items.map((f) => (
              <div
                key={f.id}
                className="flex items-center justify-between gap-3 rounded-md border p-3"
                data-testid={`favorecido-reg-${f.id}`}
              >
                <div className="min-w-0 space-y-0.5">
                  <p className="flex items-center gap-1.5 text-sm font-medium">
                    <span className="truncate">{f.nome}</span>
                    <Badge variant="outline" className="text-[10px]">
                      {f.tipo_pessoa}
                    </Badge>
                    {!f.ativo && (
                      <Badge
                        variant="outline"
                        className="text-[10px] text-warning-foreground"
                        data-testid={`favorecido-reg-inativo-${f.id}`}
                      >
                        Inativo
                      </Badge>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {f.tipo_pessoa === "PJ" ? "CNPJ" : "CPF"}{" "}
                    {f.cpf_cnpj_mascarado ?? "—"}
                    {" · "}
                    {f.banco ?? "—"}
                    {f.banco_requer_revisao && (
                      <Badge
                        variant="outline"
                        className="ml-1 text-[10px] text-warning-foreground"
                      >
                        Revisar dados bancários
                      </Badge>
                    )}
                    {f.pix_mascarado
                      ? ` · ${rotuloPix(f.pix_tipo)} ${f.pix_mascarado}`
                      : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Editar ${f.nome}`}
                    onClick={() => abrirEdicao(f)}
                    data-testid={`favorecido-reg-editar-${f.id}`}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  {f.ativo ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Desativar ${f.nome}`}
                      onClick={() => setDesativando(f)}
                      data-testid={`favorecido-reg-desativar-${f.id}`}
                    >
                      <PowerOff className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Reativar ${f.nome}`}
                      disabled={atualizar.isPending}
                      onClick={() => reativar(f)}
                      data-testid={`favorecido-reg-reativar-${f.id}`}
                    >
                      <Power className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <FavorecidoDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        favorecidoId={editandoId}
      />

      <AlertDialog
        open={!!desativando}
        onOpenChange={(v) => {
          if (!v) setDesativando(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Desativar favorecido?</AlertDialogTitle>
            <AlertDialogDescription>
              {desativando?.nome} deixa de aparecer para seleção nos cards. Os
              contratos e negociações que já o usam não são alterados, e você
              pode reativá-lo depois.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                confirmarDesativar();
              }}
              disabled={desativar.isPending}
              data-testid="favorecidos-desativar-confirmar"
            >
              {desativar.isPending ? "Desativando…" : "Desativar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
