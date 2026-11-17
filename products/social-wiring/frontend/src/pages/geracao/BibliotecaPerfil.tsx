/**
 * Library profile page (`/media-creation/biblioteca/perfis/:perfilId`, contract §11.3): header from
 * `GET /biblioteca/perfis/{id}`, the profile's Estruturas and its videos. Platform admins also get
 * sync / pause / "monitorar" / delete (delete explains `perfil_com_estruturas` and asks twice).
 */
import { QueryErrorState, useConfirm } from "@noctusai/lib/components";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { compactoPtBr, dataPtBr } from "@/components/pesquisa/format";
import { ViralCard } from "@/components/geracao/biblioteca/ViralCard";
import { ViralModal } from "@/components/geracao/biblioteca/ViralModal";
import { FILTROS_VAZIOS } from "@/components/geracao/biblioteca/filtros";
import { EstruturasLista } from "@/components/geracao/biblioteca/estruturas/EstruturasLista";
import { codigoDoErro, dadoDoErro, mensagemEstruturas, statusDoErro } from "@/components/geracao/biblioteca/estruturas/erros";
import { FILTROS_ESTRUTURAS_VAZIOS, type FiltrosEstruturas } from "@/components/geracao/biblioteca/estruturas/filtros";
import { ROTULO_PERFIL_STATUS } from "@/components/geracao/biblioteca/estruturas/rotulos";
import {
  useAtualizarPerfil,
  usePerfilBiblioteca,
  useRemoverPerfil,
  useSincronizarPerfil,
  useViraisBiblioteca,
} from "@/hooks/geracao/useBiblioteca";
import { useEstruturasAdmin } from "@/hooks/geracao/useEstruturas";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { ViralCard as ViralCardT } from "@/types/geracao";

const VOLTAR = "/media-creation/biblioteca?aba=perfis";
const VIDEOS_NA_PAGINA = 12;

export default function BibliotecaPerfil() {
  const { perfilId = "" } = useParams<{ perfilId: string }>();
  const navigate = useNavigate();
  const confirmar = useConfirm();
  const [params, setParams] = useSearchParams();
  const marcasQ = useMarcas();
  const { marcaId } = useMarcaPesquisa(marcasQ.data ?? []);
  const adminQ = useEstruturasAdmin();
  const isAdmin = adminQ.data === true;

  const perfilQ = usePerfilBiblioteca(perfilId, marcaId);
  const videosQ = useViraisBiblioteca(marcaId, { ...FILTROS_VAZIOS, perfilId, ordem: "mais_recentes", somenteVirais: false });
  const sincronizar = useSincronizarPerfil();
  const atualizar = useAtualizarPerfil();
  const remover = useRemoverPerfil();
  const [filtros, setFiltros] = useState<FiltrosEstruturas>(FILTROS_ESTRUTURAS_VAZIOS);

  const p = perfilQ.data;
  const viralAberto = params.get("viral");

  function abrirViral(v: ViralCardT) {
    const next = new URLSearchParams(params);
    next.set("viral", v.id);
    setParams(next);
  }
  function fecharViral() {
    const next = new URLSearchParams(params);
    next.delete("viral");
    setParams(next, { replace: true });
  }

  async function agora(fn: () => Promise<unknown>, ok: string, falha: string) {
    try {
      await fn();
      toast.success(ok);
    } catch (e) {
      toast.error(mensagemEstruturas(e, falha));
    }
  }

  async function excluir() {
    if (!p) return;
    if (!(await confirmar({ title: `Excluir @${p.handle} da biblioteca?`, description: "O perfil e seus vídeos saem da biblioteca da plataforma.", confirmLabel: "Excluir", tone: "danger" }))) return;
    try {
      await remover.mutateAsync({ id: p.id });
    } catch (e) {
      if (codigoDoErro(e) === "perfil_com_estruturas") {
        const n = Number(dadoDoErro(e, "estruturas_total") ?? p.estruturas_total ?? 0);
        const ok = await confirmar({
          title: "Apagar também as estruturas?",
          description: `Este perfil tem ${n === 1 ? "1 estrutura" : `${n} estruturas`}. Excluir o perfil apaga todas elas, sem volta.`,
          confirmLabel: "Apagar perfil e estruturas",
          tone: "danger",
        });
        if (!ok) return;
        try {
          await remover.mutateAsync({ id: p.id, apagar_estruturas: true });
        } catch (e2) {
          toast.error(mensagemEstruturas(e2, "Não foi possível excluir o perfil."));
          return;
        }
      } else {
        toast.error(mensagemEstruturas(e, "Não foi possível excluir o perfil."));
        return;
      }
    }
    toast.success("Perfil excluído da biblioteca.");
    navigate(VOLTAR, { replace: true });
  }

  if (perfilQ.showSkeleton) {
    return (
      <div className="flex flex-col gap-4 p-6" aria-busy="true" aria-label="Carregando perfil">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (perfilQ.isError && !p) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Voltar />
        {statusDoErro(perfilQ.error) === 404 ? (
          <div role="alert" className="rounded-md border border-dashed p-8 text-center text-sm">
            <p className="font-medium">Perfil não encontrado</p>
            <p className="mt-1 text-muted-foreground">Ele pode ter sido removido da biblioteca.</p>
          </div>
        ) : (
          <QueryErrorState query={perfilQ} title="Não foi possível carregar o perfil." />
        )}
      </div>
    );
  }
  if (!p) return null;

  const videos = videosQ.data?.items.slice(0, VIDEOS_NA_PAGINA) ?? [];
  const pausado = p.status === "pausado";

  return (
    <div className="flex flex-col gap-6 p-6">
      <Voltar />
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          {p.foto_url ? (
            <img src={p.foto_url} alt="" className="h-16 w-16 rounded-full object-cover" />
          ) : (
            <span aria-hidden="true" className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-lg font-semibold uppercase text-primary-foreground">
              {p.handle.slice(0, 2)}
            </span>
          )}
          <div className="flex flex-col gap-1">
            <h1 className="text-2xl font-semibold">@{p.handle}</h1>
            {p.nome && <p className="text-sm text-muted-foreground">{p.nome}</p>}
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {p.seguidores != null && <span>{compactoPtBr(p.seguidores)} seguidores ·</span>}
              <span>{p.estruturas_total != null ? (p.estruturas_total === 1 ? "1 estrutura" : `${p.estruturas_total} estruturas`) : "— estruturas"}</span>
              {p.ultima_sync_em !== undefined && <span>· Última sincronização: {dataPtBr(p.ultima_sync_em)}</span>}
              {p.monitorar === false ? <Badge variant="outline">Somente biblioteca</Badge> : p.status ? <Badge variant="secondary">{ROTULO_PERFIL_STATUS[p.status] ?? p.status}</Badge> : null}
              {perfilQ.isRefreshing && <span className="text-xs">Atualizando…</span>}
            </div>
            <a className="inline-flex w-fit items-center gap-1 text-sm text-primary hover:underline" href={`https://www.instagram.com/${encodeURIComponent(p.handle)}/`} target="_blank" rel="noopener noreferrer">
              Ver no Instagram <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </div>
        </div>

        {isAdmin && (
          <div className="flex flex-col items-end gap-3" role="group" aria-label="Ações do administrador">
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="outline" size="sm" disabled={sincronizar.isPending} onClick={() => agora(() => sincronizar.mutateAsync(p.id), "Sincronização solicitada.", "Não foi possível sincronizar agora.")}>
                Sincronizar agora
              </Button>
              <Button variant="outline" size="sm" disabled={atualizar.isPending} onClick={() => agora(() => atualizar.mutateAsync({ id: p.id, status: pausado ? "ativo" : "pausado" }), pausado ? "Monitoramento retomado." : "Monitoramento pausado.", "Não foi possível alterar o perfil.")}>
                {pausado ? "Retomar" : "Pausar"}
              </Button>
              <Button variant="outline" size="sm" className="text-destructive" disabled={remover.isPending} onClick={() => void excluir()}>
                Excluir
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Switch id="perfil-monitorar" checked={p.monitorar !== false} disabled={atualizar.isPending} onCheckedChange={(v) => agora(() => atualizar.mutateAsync({ id: p.id, monitorar: v }), v ? "Monitoramento ligado." : "Monitoramento desligado.", "Não foi possível alterar o monitoramento.")} />
              <Label htmlFor="perfil-monitorar">Monitorar novos vídeos</Label>
            </div>
          </div>
        )}
      </header>

      <EstruturasLista filtros={filtros} onFiltros={setFiltros} isAdmin={isAdmin} marcaId={marcaId} perfilId={p.id} />

      <section aria-label="Vídeos" className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Vídeos{videosQ.data ? ` (${videosQ.data.total.toLocaleString("pt-BR")})` : ""}</h2>
          {videosQ.data && videosQ.data.total > VIDEOS_NA_PAGINA && (
            <Link className="text-sm text-primary hover:underline" to={`/media-creation/biblioteca?perfil=${encodeURIComponent(p.id)}`}>
              Ver todos os vídeos deste perfil
            </Link>
          )}
        </div>
        {!marcaId && !marcasQ.isPending ? (
          <p className="text-sm text-muted-foreground">Cadastre uma marca para ver os vídeos da biblioteca.</p>
        ) : videosQ.showSkeleton || marcasQ.isPending ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-6" aria-busy="true">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="aspect-[9/16] w-full" />
            ))}
          </div>
        ) : videosQ.isError && !videosQ.data ? (
          <QueryErrorState query={videosQ} title="Não foi possível carregar os vídeos." />
        ) : videos.length === 0 ? (
          <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            Nenhum vídeo deste perfil na biblioteca ainda.
            {p.monitorar === false ? " Ele não é monitorado: os vídeos entram por link." : ""}
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-6">
            {videos.map((v) => (
              <ViralCard key={v.id} viral={v} onAbrir={abrirViral} />
            ))}
          </div>
        )}
      </section>

      <ViralModal open={!!viralAberto} onOpenChange={(o) => !o && fecharViral()} marcaId={marcaId} viralId={viralAberto} />
    </div>
  );
}

function Voltar() {
  return (
    <Link to={VOLTAR} className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Voltar para os perfis
    </Link>
  );
}
