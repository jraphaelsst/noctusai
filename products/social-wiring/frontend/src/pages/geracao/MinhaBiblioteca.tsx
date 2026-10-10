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
  useAtualizarPerfil,
  useCriarReferencias,
  usePerfisMonitorados,
  useReferencias,
  useRemoverPerfil,
  useRemoverReferencia,
  useSincronizarPerfil,
} from "@/hooks/geracao/useBiblioteca";
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
  erro: "Erro",
};

const msg = (e: unknown, fallback: string) =>
  e instanceof Error && e.message ? e.message : fallback;

export default function MinhaBiblioteca() {
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  const [busca, setBusca] = useState("");
  const buscaDeb = useDebouncedValue(busca, 300);
  const perfisQ = usePerfisMonitorados();
  const refsQ = useReferencias(marcaId, buscaDeb);
  const criar = useCriarReferencias();
  const sincronizar = useSincronizarPerfil();
  const atualizar = useAtualizarPerfil();
  const removerPerfil = useRemoverPerfil();
  const removerRef = useRemoverReferencia();

  const [perfisSel, setPerfisSel] = useState<string[]>([]);
  const [auto, setAuto] = useState(true);
  const [refRemover, setRefRemover] = useState<Referencia | null>(null);
  const [perfilRemover, setPerfilRemover] = useState<{ id: string; handle: string } | null>(null);

  const perfis = perfisQ.data ?? [];
  const refs = refsQ.data ?? [];
  const jaRef = new Set(refs.filter((r) => r.modo === "perfil" && r.perfil).map((r) => r.perfil!.id));
  const disponiveis = perfis.filter((p) => !jaRef.has(p.id));
  const monitoramentoOff = perfis.some((p) => p.ingestao_ativa === false);

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

  async function alternarPausa(id: string, status: PerfilStatus) {
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
      await removerPerfil.mutateAsync({ id: perfilRemover.id, marca_id: marcaId });
      toast.success("Perfil removido.");
      setPerfilRemover(null);
    } catch (e) {
      toast.error(msg(e, "Perfil em uso por outra marca ou não pôde ser removido."));
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
        <div role="status" className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
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
            <MultiSelectPopover
              label="Perfis da biblioteca"
              options={disponiveis.map((p) => ({
                value: p.id,
                label: `@${p.handle} (${p.virais} virais)`,
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
              <SolicitarPerfil marcaId={marcaId} />
            ) : (
              <p className="text-sm text-muted-foreground">Cadastre uma marca primeiro.</p>
            )}
          </TabsContent>
        </Tabs>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">Perfis monitorados</h2>
        {perfisQ.showSkeleton ? (
          <Skeleton className="h-24 w-full" />
        ) : perfisQ.isError ? (
          <div className="text-sm text-destructive">
            Não foi possível carregar os perfis.{" "}
            <Button variant="link" className="h-auto p-0" onClick={() => perfisQ.refetch()}>
              Tentar novamente
            </Button>
          </div>
        ) : perfis.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum perfil monitorado ainda. Use "Solicitar Perfil" acima.
          </p>
        ) : (
          <div className={cn("overflow-x-auto rounded-md border", perfisQ.isRefreshing && "opacity-70")}>
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th className="p-2">Perfil</th>
                  <th className="p-2">Status</th>
                  <th className="p-2">Virais</th>
                  <th className="p-2">Última atualização</th>
                  <th className="p-2">Ações</th>
                </tr>
              </thead>
              <tbody>
                {perfis.map((p) => (
                  <tr key={p.id} className="border-t">
                    <td className="p-2">
                      <Link
                        className="text-primary hover:underline"
                        to={`/media-creation/biblioteca?perfil=${encodeURIComponent(p.id)}`}
                      >
                        @{p.handle}
                      </Link>
                    </td>
                    <td className="p-2">
                      <Badge variant="outline">{PERFIL_STATUS_ROTULO[p.status]}</Badge>
                      {p.erro_mensagem && (
                        <span className="ml-2 text-xs text-muted-foreground">{p.erro_mensagem}</span>
                      )}
                    </td>
                    <td className="p-2">{compactoPtBr(p.virais)}</td>
                    <td className="p-2">{dataPtBr(p.ultima_sync_em)}</td>
                    <td className="flex flex-wrap gap-1 p-2">
                      <Button size="sm" variant="outline" onClick={() => atualizarAgora(p.id)}>
                        Atualizar agora
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => alternarPausa(p.id, p.status)}>
                        {p.status === "pausado" ? "Retomar" : "Pausar"}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setPerfilRemover({ id: p.id, handle: p.handle })}
                      >
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
        descricao={`Remover @${perfilRemover?.handle ?? ""} apaga seus virais, miniaturas e transcrições. Não é possível se outra marca ainda o referencia.`}
        rotuloConfirmar="Remover perfil"
        onConfirmar={confirmarRemoverPerfil}
        pendente={removerPerfil.isPending}
      />
    </div>
  );
}
