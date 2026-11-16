/**
 * Minha Biblioteca (P5, `/media-creation/minha-biblioteca`) — contract §7.5.
 * Allow-list of profiles/videos the chat and roteiros use, plus the org's
 * monitored profiles. Loading: `showSkeleton` / `isRefreshing`, never
 * `.isLoading`. While ingestion is off, profiles stay "Aguardando" and the
 * page says so instead of implying monitoring is running.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { compactoPtBr, dataPtBr } from "@/components/pesquisa/format";
import { ConfirmarModal } from "@/components/pesquisa/ConfirmarModal";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { SolicitarPerfil } from "@/components/geracao/biblioteca/SolicitarPerfil";
import { OptoutsAdmin } from "@/components/geracao/biblioteca/OptoutsAdmin";
import { MultiSelectPopover } from "@noctusai/lib/design-system";
import {
  PERFIS_POR_PAGINA,
  useAtualizarPerfil,
  useCriarReferencias,
  usePerfisBiblioteca,
  usePerfisMonitorados,
  useReferencias,
  useRemoverPerfil,
  useRemoverReferencia,
  useSincronizarPerfil,
} from "@/hooks/geracao/useBiblioteca";
import { codigoDoErro, dadoDoErro, mensagemEstruturas } from "@/components/geracao/biblioteca/estruturas/erros";
import { useTreinamentosAdmin } from "@/hooks/geracao/useTreinamentos";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { PerfilStatus, Referencia } from "@/types/geracao";


export const PERFIL_STATUS_ROTULO: Record<PerfilStatus, string> = {
  aguardando: "Aguardando",
  ativo: "Ativo",
  pausado: "Pausado",
  nao_encontrado: "Não encontrado",
  sem_conta: "Sem conta",
  sem_credencial: "Sem credencial",
  sem_orcamento: "Sem orçamento",
  erro: "Erro",
};

/**
 * A refusal is never silent: the catalogue's pt-BR sentence by `code`, then the server's own. Writes on the library
 * itself are platform-admin only (the library is platform-wide), so a member's 403 says exactly that.
 */
const msg = (e: unknown, fallback: string) =>
  mensagemEstruturas(e, fallback).replace(/^\[\d+\]\s*/, "");

export default function MinhaBiblioteca() {
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  const [busca, setBusca] = useState("");
  const buscaDeb = useDebouncedValue(busca, 300);
  // Member write controls on the library (sync / pause / remove / request) are platform-admin only; the server
  // enforces it (403), the UI just doesn't offer what it will refuse.
  const isAdmin = useTreinamentosAdmin().data === true;
  const [buscaPerfil, setBuscaPerfil] = useState("");
  const buscaPerfilDeb = useDebouncedValue(buscaPerfil, 300);
  // Picker source: searchable, first 50 matches (the library is paged server-side, ≤ 50 per request).
  const perfisQ = usePerfisMonitorados(buscaPerfilDeb);
  // The table: the whole library, one page at a time.
  const [offset, setOffset] = useState(0);
  const paginaQ = usePerfisBiblioteca({ marcaId, limit: PERFIS_POR_PAGINA, offset });
  const refsQ = useReferencias(marcaId, buscaDeb);
  const criar = useCriarReferencias();
  const sincronizar = useSincronizarPerfil();
  const atualizar = useAtualizarPerfil();
  const removerPerfil = useRemoverPerfil();
  const removerRef = useRemoverReferencia();

  const [perfisSel, setPerfisSel] = useState<string[]>([]);
  const [auto, setAuto] = useState(true);
  const [refRemover, setRefRemover] = useState<Referencia | null>(null);
  const [perfilRemover, setPerfilRemover] = useState<{ id: string; handle: string; estruturasTotal?: number } | null>(null);

  const perfis = perfisQ.data ?? [];
  const pagina = paginaQ.data?.items ?? [];
  const totalPerfis = paginaQ.data?.total ?? 0;
  const refs = refsQ.data ?? [];
  const jaRef = new Set(refs.filter((r) => r.modo === "perfil" && r.perfil).map((r) => r.perfil!.id));
  const disponiveis = perfis.filter((p) => !jaRef.has(p.id));
  const monitoramentoOff = [...perfis, ...pagina].some((p) => p.ingestao_ativa === false);

  async function salvarPerfis() {
    if (!marcaId || perfisSel.length === 0) return;
    try {
      const r = await criar.mutateAsync({
        marca_id: marcaId,
        modo: "perfil",
        perfil_ids: perfisSel.slice(0, 20),
        auto_atualizar: auto,
      });
      toast.success(`${r.criadas} perfil(is) adicionado(s) às referências.`);
      setPerfisSel([]);
    } catch (e) {
      toast.error(msg(e, "Não foi possível salvar as referências."));
    }
  }

  async function atualizarAgora(id: string) {
    try {
      await sincronizar.mutateAsync(id);
      toast.success("Atualização solicitada.");
    } catch (e) {
      toast.error(msg(e, "Não foi possível atualizar agora (limite de uma vez por hora)."));
    }
  }

  async function alternarPausa(id: string, status?: PerfilStatus) {
    try {
      await atualizar.mutateAsync({ id, status: status === "pausado" ? "ativo" : "pausado" });
    } catch (e) {
      toast.error(msg(e, "Não foi possível alterar o perfil."));
    }
  }

  async function confirmarRemoverRef() {
    if (!refRemover) return;
    try {
      await removerRef.mutateAsync(refRemover.id);
      toast.success("Referência removida.");
      setRefRemover(null);
    } catch (e) {
      toast.error(msg(e, "Não foi possível remover a referência."));
    }
  }

  async function confirmarRemoverPerfil() {
    if (!perfilRemover) return;
    try {
      await removerPerfil.mutateAsync({
        id: perfilRemover.id,
        marca_id: marcaId,
        // Second round: the admin has seen "tem N estruturas" and confirmed deleting them too.
        ...(perfilRemover.estruturasTotal != null ? { apagar_estruturas: true } : {}),
      });
      toast.success("Perfil removido.");
      setPerfilRemover(null);
    } catch (e) {
      if (codigoDoErro(e) === "perfil_com_estruturas" && perfilRemover.estruturasTotal == null) {
        // Coded refusal, shown not swallowed: keep the dialog open and ask for the explicit confirmation.
        const n = Number(dadoDoErro(e, "estruturas_total"));
        setPerfilRemover({ ...perfilRemover, estruturasTotal: Number.isFinite(n) ? n : 0 });
        return;
      }
      toast.error(msg(e, "Não foi possível remover o perfil."));
      setPerfilRemover(null);
    }
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Minha Biblioteca</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie seus perfis e vídeos de referência para usar no Chat.
          </p>
        </div>
        <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
      </header>

      {monitoramentoOff && (
        <div role="status" className="rounded-md border border-warning/40 bg-warning-light p-3 text-sm text-warning-foreground">
          Monitoramento ainda não ativado: as solicitações ficam em "Aguardando" até a ingestão
          da biblioteca ser ligada.
        </div>
      )}

      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-lg font-semibold">Adicionar referência</h2>
        <Tabs defaultValue="perfil">
          <TabsList>
            <TabsTrigger value="perfil">Perfil completo</TabsTrigger>
            <TabsTrigger value="video">Vídeos específicos</TabsTrigger>
            <TabsTrigger value="solicitar">Solicitar Perfil</TabsTrigger>
          </TabsList>

          <TabsContent value="perfil" className="mt-4 flex max-w-md flex-col gap-3">
            <Input
              aria-label="Buscar perfis da biblioteca"
              placeholder="Buscar perfil por @handle ou nome..."
              value={buscaPerfil}
              onChange={(e) => setBuscaPerfil(e.target.value)}
            />
            <MultiSelectPopover
              label="Perfis da biblioteca"
              options={disponiveis.map((p) => ({
                value: p.id,
                label: `@${p.handle}${p.nome ? ` · ${p.nome}` : ""} (${p.virais} virais)`,
              }))}
              selected={perfisSel}
              onToggle={(id) =>
                setPerfisSel((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
              }
              emptyMessage="Nenhum perfil disponível para adicionar."
            />
            <div className="flex items-center justify-between gap-3">
              <div>
                <Label htmlFor="mb-auto">Atualização automática</Label>
                <p className="text-xs text-muted-foreground">
                  Novos vídeos desses perfis entram automaticamente.
                </p>
              </div>
              <Switch id="mb-auto" checked={auto} onCheckedChange={setAuto} />
            </div>
            <Button
              className="w-fit"
              disabled={!marcaId || perfisSel.length === 0 || criar.isPending}
              onClick={salvarPerfis}
            >
              {criar.isPending ? "Salvando..." : "Salvar"}
            </Button>
          </TabsContent>

          <TabsContent value="video" className="mt-4 flex flex-col gap-3 text-sm">
            <p className="text-muted-foreground">
              Para adicionar vídeos específicos, selecione-os na Biblioteca de Virais e use
              "Adicionar à Minha Biblioteca".
            </p>
            <Button asChild variant="outline" className="w-fit">
              <Link to="/media-creation/biblioteca">Ir para a Biblioteca de Virais</Link>
            </Button>
          </TabsContent>

          <TabsContent value="solicitar" className="mt-4">
            {marcaId ? (
              <SolicitarPerfil marcaId={marcaId} contato={perfis.find((p) => p.optout_contato)?.optout_contato} />
            ) : (
              <p className="text-sm text-muted-foreground">Cadastre uma marca primeiro.</p>
            )}
          </TabsContent>
        </Tabs>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">Perfis da biblioteca</h2>
        {paginaQ.showSkeleton ? (
          <Skeleton className="h-24 w-full" />
        ) : paginaQ.isError && !paginaQ.data ? (
          <div role="alert" className="text-sm text-destructive">
            Não foi possível carregar os perfis.{" "}
            <Button variant="link" className="h-auto p-0" onClick={() => paginaQ.refetch()}>
              Tentar novamente
            </Button>
          </div>
        ) : pagina.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {isAdmin
              ? 'Nenhum perfil na biblioteca ainda. Use "Solicitar Perfil" acima.'
              : "Nenhum perfil na biblioteca ainda. A equipe NoctusAI adiciona novos perfis."}
          </p>
        ) : (
          <>
            <div className={cn("overflow-x-auto rounded-md border", paginaQ.isRefreshing && "opacity-70")}>
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left">
                  <tr>
                    <th className="p-2">Perfil</th>
                    {isAdmin && <th className="p-2">Status</th>}
                    <th className="p-2">Virais</th>
                    {isAdmin && <th className="p-2">Última atualização</th>}
                    {isAdmin && <th className="p-2">Ações</th>}
                  </tr>
                </thead>
                <tbody>
                  {pagina.map((p) => (
                    <tr key={p.id} className="border-t">
                      <td className="p-2">
                        <Link className="text-primary hover:underline" to={`/media-creation/biblioteca/perfis/${encodeURIComponent(p.id)}`}>
                          @{p.handle}
                        </Link>
                        {p.nome && <span className="ml-2 text-xs text-muted-foreground">{p.nome}</span>}
                      </td>
                      {isAdmin && (
                        <td className="p-2">
                          {p.status && <Badge variant="outline">{PERFIL_STATUS_ROTULO[p.status]}</Badge>}
                          {p.erro_mensagem && <span className="ml-2 text-xs text-muted-foreground">{p.erro_mensagem}</span>}
                        </td>
                      )}
                      <td className="p-2">{compactoPtBr(p.virais)}</td>
                      {isAdmin && <td className="p-2">{dataPtBr(p.ultima_sync_em ?? null)}</td>}
                      {isAdmin && (
                        <td className="flex flex-wrap gap-1 p-2">
                          <Button size="sm" variant="outline" onClick={() => atualizarAgora(p.id)}>
                            Atualizar agora
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => alternarPausa(p.id, p.status)}>
                            {p.status === "pausado" ? "Retomar" : "Pausar"}
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setPerfilRemover({ id: p.id, handle: p.handle })}>
                            Remover
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <nav aria-label="Paginação dos perfis" className="flex items-center justify-between gap-2 text-sm">
              <span className="text-muted-foreground" data-testid="perfis-pagina">
                {offset + 1}–{offset + pagina.length} de {totalPerfis}
              </span>
              <span className="flex gap-2">
                <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PERFIS_POR_PAGINA))}>
                  Anterior
                </Button>
                <Button size="sm" variant="outline" disabled={offset + pagina.length >= totalPerfis} onClick={() => setOffset(offset + PERFIS_POR_PAGINA)}>
                  Próxima
                </Button>
              </span>
            </nav>
          </>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Minhas referências</h2>
          <Input
            aria-label="Buscar referências"
            placeholder="Buscar por ID ou headline..."
            className="w-64"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        {refsQ.showSkeleton ? (
          <Skeleton className="h-24 w-full" />
        ) : refsQ.isError ? (
          <div className="text-sm text-destructive">
            Não foi possível carregar as referências.{" "}
            <Button variant="link" className="h-auto p-0" onClick={() => refsQ.refetch()}>
              Tentar novamente
            </Button>
          </div>
        ) : refs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {buscaDeb ? "Nenhuma referência encontrada." : "Você ainda não tem referências."}
          </p>
        ) : (
          <div className={cn("overflow-x-auto rounded-md border", refsQ.isRefreshing && "opacity-70")}>
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th className="p-2">Tipo</th>
                  <th className="p-2">Perfil / Detalhe</th>
                  <th className="p-2">Posts até</th>
                  <th className="p-2">Atualizado</th>
                  <th className="p-2" />
                </tr>
              </thead>
              <tbody>
                {refs.map((r) => (
                  <tr key={r.id} className="border-t">
                    <td className="p-2">
                      {r.modo === "perfil" ? "Perfil" : "Vídeo"}
                      {r.auto_atualizar && (
                        <Badge variant="secondary" className="ml-2">
                          Auto
                        </Badge>
                      )}
                    </td>
                    <td className="p-2">
                      {r.modo === "perfil" && r.perfil ? (
                        <Link
                          className="text-primary hover:underline"
                          to={`/media-creation/biblioteca?perfil=${encodeURIComponent(r.perfil.id)}`}
                        >
                          @{r.perfil.handle}
                        </Link>
                      ) : r.viral ? (
                        <Link
                          className="text-primary hover:underline"
                          to={`/media-creation/biblioteca?viral=${encodeURIComponent(r.viral.id)}`}
                        >
                          @{r.viral.perfil.handle} · #{r.viral.codigo}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="p-2">{r.posts_ate ? dataPtBr(r.posts_ate) : "Todos"}</td>
                    <td className="p-2">{dataPtBr(r.updated_at)}</td>
                    <td className="p-2 text-right">
                      <Button size="sm" variant="ghost" onClick={() => setRefRemover(r)}>
                        Remover
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <OptoutsAdmin />

      <ConfirmarModal
        open={!!refRemover}
        onOpenChange={(o) => !o && setRefRemover(null)}
        titulo="Remover referência"
        descricao="Esta referência deixa de ser usada pelo Chat e pelos roteiros desta marca."
        rotuloConfirmar="Remover"
        onConfirmar={confirmarRemoverRef}
        pendente={removerRef.isPending}
      />
      <ConfirmarModal
        open={!!perfilRemover}
        onOpenChange={(o) => !o && setPerfilRemover(null)}
        titulo="Remover perfil monitorado"
        descricao={
          perfilRemover?.estruturasTotal != null
            ? `@${perfilRemover.handle} tem ${perfilRemover.estruturasTotal} ${perfilRemover.estruturasTotal === 1 ? "estrutura" : "estruturas"}. Confirmar apaga o perfil, seus virais e também essas estruturas.`
            : `Remover @${perfilRemover?.handle ?? ""} apaga seus virais, miniaturas e transcrições.`
        }
        rotuloConfirmar={perfilRemover?.estruturasTotal != null ? "Apagar perfil e estruturas" : "Remover perfil"}
        onConfirmar={confirmarRemoverPerfil}
        pendente={removerPerfil.isPending}
      />
    </div>
  );
}
