/**
 * Minhas extrações (`/media-creation/cerebro/extracoes`) — table of per-marca
 * extractions, search, "Carregar mais", Nova Extração, Ver (edit + apply), Excluir.
 * Contract: cerebro-contract.md §4 (19-24), §6, §10 (pasted text only in v1).
 * Loading: two signals off `data`, never `.isLoading` (lying-loading-state.md).
 */
import { useEffect, useState } from "react";
import { AlertCircle, ArrowLeft, Loader2, Plus, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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
import { Textarea } from "@/components/ui/textarea";
import { NovaExtracaoModal } from "@/components/cerebro/NovaExtracaoModal";
import { MAX_CONTEUDO, STATUS_EXTRACAO_ROTULO, mensagemErro } from "@/components/cerebro/labels";
import { ConfirmarModal } from "@/components/pesquisa/ConfirmarModal";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import {
  PAGE_SIZE,
  useAplicarExtracao,
  useAtualizarExtracao,
  useExcluirExtracao,
  useExtracao,
  useExtracoes,
} from "@/hooks/useExtracoes";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { ExtractionSummary } from "@/types/cerebro";

const CEREBRO = "/media-creation/cerebro";

function formatarData(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

export default function MinhasExtracoes() {
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  const [busca, setBusca] = useState("");
  const q = useDebouncedValue(busca, 300);
  const [limit, setLimit] = useState(PAGE_SIZE);
  useEffect(() => setLimit(PAGE_SIZE), [marcaId, q]);

  const listQ = useExtracoes(marcaId, q, limit);
  const itens = listQ.data?.items ?? [];
  const total = listQ.data?.total ?? 0;

  const [novaAberta, setNovaAberta] = useState(false);
  const [verId, setVerId] = useState<string | null>(null);
  const [excluir, setExcluir] = useState<ExtractionSummary | null>(null);
  const excluirM = useExcluirExtracao();

  async function onExcluir() {
    if (!excluir) return;
    try {
      await excluirM.mutateAsync(excluir.id);
      toast.success("Extração excluída.");
      setExcluir(null);
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível excluir a extração."));
    }
  }

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to={CEREBRO} className="mb-1 inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline">
            <ArrowLeft className="h-3.5 w-3.5" />
            Voltar
          </Link>
          <h1 className="text-2xl font-semibold">Minhas extrações</h1>
          <p className="text-sm text-muted-foreground">Segundo cérebro</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
          <Button onClick={() => setNovaAberta(true)} disabled={!marcaId}>
            <Plus className="mr-1.5 h-4 w-4" />
            Nova Extração
          </Button>
        </div>
      </header>

      {marcasQ.isPending && !marcasQ.data ? (
        <Skeleton className="h-40 w-full" />
      ) : marcasQ.isError && !marcasQ.data ? (
        <ErroBloco texto="Não foi possível carregar as marcas." onRetry={() => void marcasQ.refetch()} />
      ) : !marcaId ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Cadastre uma marca em Clientes para criar extrações.
        </p>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <Input
              aria-label="Pesquisar"
              className="max-w-sm"
              placeholder="Pesquisar..."
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
            {listQ.isRefreshing && (
              <span role="status" className="flex items-center gap-1 text-sm text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Atualizando…
              </span>
            )}
          </div>

          {listQ.showSkeleton ? (
            <div className="space-y-2" aria-busy="true" data-testid="extracoes-skeleton">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : listQ.isError && !listQ.data ? (
            <ErroBloco texto="Não foi possível carregar as extrações." onRetry={() => void listQ.refetch()} />
          ) : itens.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">Nenhuma extração encontrada.</p>
          ) : (
            <>
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-left">
                    <tr>
                      <th className="p-3">ID</th>
                      <th className="p-3">Data</th>
                      <th className="p-3">Nome</th>
                      <th className="p-3">Cérebros</th>
                      <th className="p-3">Status</th>
                      <th className="p-3 text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {itens.map((e) => (
                      <tr key={e.id} className="border-t" data-testid="extracao-linha">
                        <td className="p-3 font-mono text-xs">{e.id.slice(0, 8)}</td>
                        <td className="p-3">{formatarData(e.created_at)}</td>
                        <td className="p-3 font-medium">{e.name}</td>
                        <td className="p-3">{e.targets.map((t) => t.brain_name).join(", ")}</td>
                        <td className="p-3">
                          <Badge variant={e.status === "error" ? "destructive" : "outline"}>
                            {STATUS_EXTRACAO_ROTULO[e.status]}
                          </Badge>
                        </td>
                        <td className="p-3 text-right">
                          <div className="flex justify-end gap-2">
                            <Button size="sm" variant="outline" onClick={() => setVerId(e.id)}>
                              Ver
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => setExcluir(e)}>
                              Excluir
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {itens.length < total && (
                <div className="flex justify-center">
                  <Button variant="outline" onClick={() => setLimit((l) => l + PAGE_SIZE)} disabled={listQ.isRefreshing}>
                    Carregar mais
                  </Button>
                </div>
              )}
            </>
          )}
        </>
      )}

      {marcaId && <NovaExtracaoModal open={novaAberta} onOpenChange={setNovaAberta} marcaId={marcaId} />}
      <VerExtracaoModal id={verId} onClose={() => setVerId(null)} />
      <ConfirmarModal
        open={!!excluir}
        onOpenChange={(o) => !o && setExcluir(null)}
        titulo="Excluir extração"
        descricao={`Tem certeza que deseja excluir «${excluir?.name ?? ""}»? O texto já anexado aos cérebros permanece.`}
        rotuloConfirmar="Excluir"
        onConfirmar={() => void onExcluir()}
        pendente={excluirM.isPending}
      />
    </div>
  );
}

function VerExtracaoModal({ id, onClose }: { id: string | null; onClose: () => void }) {
  const detQ = useExtracao(id);
  const det = detQ.data;
  const atualizar = useAtualizarExtracao();
  const aplicar = useAplicarExtracao();
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const transcriptServidor = det?.transcript ?? "";
  useEffect(() => {
    setTexto(transcriptServidor);
    setErro(null);
  }, [id, transcriptServidor]);

  const editavel = det?.status === "ready" || det?.status === "applied";
  const sujo = editavel && texto !== transcriptServidor;
  const pendentes = (det?.targets ?? []).filter((t) => !t.applied_at);

  async function onSalvar() {
    if (!det) return;
    try {
      await atualizar.mutateAsync({ id: det.id, transcript: texto });
      toast.success("Transcrição salva.");
      setErro(null);
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível salvar a transcrição."));
    }
  }

  async function onAplicar() {
    if (!det) return;
    try {
      const r = await aplicar.mutateAsync({ id: det.id });
      toast.success(
        r.applied.length > 0 ? "Extração aplicada aos cérebros." : "Nenhum cérebro pendente para aplicar.",
      );
      setErro(null);
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível aplicar a extração."));
    }
  }

  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{det?.name ?? "Extração"}</DialogTitle>
          <DialogDescription>
            {det ? `${STATUS_EXTRACAO_ROTULO[det.status]} · ${formatarData(det.created_at)}` : "Carregando…"}
          </DialogDescription>
        </DialogHeader>

        {detQ.showSkeleton ? (
          <Skeleton className="h-40 w-full" />
        ) : detQ.isError && !det ? (
          <ErroBloco texto="Não foi possível carregar a extração." onRetry={() => void detQ.refetch()} />
        ) : det ? (
          <div className="space-y-4">
            {det.status === "error" && (
              <p role="alert" className="text-sm text-destructive">
                {det.error_message ?? "A extração falhou."}
              </p>
            )}
            {det.status === "transcribing" && (
              <p role="status" className="flex items-center gap-1 text-sm text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Transcrevendo…
              </p>
            )}
            <ul className="flex flex-wrap gap-2" aria-label="Cérebros de destino">
              {det.targets.map((t) => (
                <li key={t.brain_id}>
                  <Badge variant={t.applied_at ? "secondary" : "outline"}>
                    {t.brain_name} · {t.applied_at ? "Aplicado" : "Pendente"}
                  </Badge>
                </li>
              ))}
            </ul>
            <Textarea
              aria-label="Transcrição"
              rows={12}
              value={texto}
              maxLength={MAX_CONTEUDO}
              readOnly={!editavel}
              onChange={(e) => setTexto(e.target.value)}
            />
            {erro && (
              <p role="alert" className="text-sm text-destructive">
                {erro}
              </p>
            )}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
          {editavel && (
            <>
              <Button variant="outline" onClick={() => void onSalvar()} disabled={!sujo || atualizar.isPending}>
                {atualizar.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                Salvar
              </Button>
              <Button onClick={() => void onAplicar()} disabled={sujo || pendentes.length === 0 || aplicar.isPending}>
                {aplicar.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                Aplicar aos cérebros
              </Button>
            </>
          )}
        </DialogFooter>
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
