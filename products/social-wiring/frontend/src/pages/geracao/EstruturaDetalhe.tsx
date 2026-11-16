/**
 * Estrutura detail (`/media-creation/biblioteca/estruturas/:id`, contract §11.3).
 * Members: formula, ordered blocks (tempo / instrução / nota / ×N), source video, "Usar no chat".
 * Platform admins (`GET /estruturas/admin`): the same page as an editor — formula/formato/objetivos, blocks
 * add/remove/reorder with the catalog type select, per-field provenance with Confirmar, Publicar on a rascunho,
 * archive/restore/delete. Members never receive provenance, rascunho or arquivada (the server answers 404).
 *
 * Loading: `showSkeleton` / `isRefreshing`; a 404 is its own state ("não encontrada"), never a blank page.
 */
import { QueryErrorState } from "@noctusai/lib/components";
import { ArrowLeft, ExternalLink, MessageSquare } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EstruturaEditor } from "@/components/geracao/biblioteca/estruturas/EstruturaEditor";
import { EstruturaLeitura } from "@/components/geracao/biblioteca/estruturas/EstruturaLeitura";
import { statusDoErro } from "@/components/geracao/biblioteca/estruturas/erros";
import {
  ROTULO_FORMATO,
  ROTULO_OBJETIVO,
  ROTULO_ORIGEM_ESTRUTURA,
  ROTULO_STATUS,
  rotuloCodigo,
} from "@/components/geracao/biblioteca/estruturas/rotulos";
import { useEstruturaDetalhe, useEstruturasAdmin, useTiposBloco } from "@/hooks/geracao/useEstruturas";

const VOLTAR = "/media-creation/biblioteca?aba=estruturas";

export default function EstruturaDetalhePage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const adminQ = useEstruturasAdmin();
  const q = useEstruturaDetalhe(id);
  const tiposQ = useTiposBloco();
  const isAdmin = adminQ.data === true;
  const e = q.data;

  if (q.showSkeleton) {
    return (
      <div className="flex flex-col gap-4 p-6" aria-busy="true" aria-label="Carregando estrutura">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (q.isError && !e) {
    const naoEncontrada = statusDoErro(q.error) === 404;
    return (
      <div className="flex flex-col gap-4 p-6">
        <Voltar />
        {naoEncontrada ? (
          <div role="alert" className="rounded-md border border-dashed p-8 text-center text-sm">
            <p className="font-medium">Estrutura não encontrada</p>
            <p className="mt-1 text-muted-foreground">Ela pode ter sido arquivada, removida ou ainda ser um rascunho.</p>
          </div>
        ) : (
          <QueryErrorState query={q} title="Não foi possível carregar a estrutura." />
        )}
      </div>
    );
  }
  if (!e) return null;

  return (
    <div className="flex flex-col gap-5 p-6">
      <Voltar />
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold">Estrutura {rotuloCodigo(e.codigo)}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Link className="text-primary hover:underline" to={`/media-creation/biblioteca/perfis/${encodeURIComponent(e.perfil.id)}`}>
              @{e.perfil.handle}
            </Link>
            {e.formato && <Badge variant="secondary">{ROTULO_FORMATO[e.formato]}</Badge>}
            {e.objetivos.map((o) => (
              <Badge key={o} variant="outline">
                {ROTULO_OBJETIVO[o]}
              </Badge>
            ))}
            {isAdmin && e.status !== "ativa" && <Badge>{ROTULO_STATUS[e.status]}</Badge>}
            {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
          </div>
        </div>
        {e.status === "ativa" && (
          <Button asChild>
            <Link to={`/media-creation/chat?estrutura=${encodeURIComponent(e.id)}`}>
              <MessageSquare className="mr-2 h-4 w-4" aria-hidden="true" /> Usar no chat
            </Link>
          </Button>
        )}
      </header>

      {e.viral && (
        <section aria-label="Vídeo de origem" className="flex items-center gap-3 rounded-lg border p-3 text-sm">
          {e.viral.thumbnail_url ? (
            <img src={e.viral.thumbnail_url} alt="" loading="lazy" className="h-20 w-11 rounded object-cover" />
          ) : null}
          <div className="flex flex-col gap-1">
            <p className="font-medium">Vídeo de origem (viral {rotuloCodigo(e.viral.codigo)})</p>
            <div className="flex flex-wrap gap-3">
              <Link className="text-primary hover:underline" to={`/media-creation/biblioteca?viral=${encodeURIComponent(e.viral.id)}`}>
                Abrir na biblioteca
              </Link>
              <a className="inline-flex items-center gap-1 text-primary hover:underline" href={e.viral.permalink} target="_blank" rel="noopener noreferrer">
                Ver post <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
            </div>
          </div>
        </section>
      )}

      {isAdmin && e.origem && (
        <p className="text-xs text-muted-foreground" data-testid="estrutura-origem">
          {ROTULO_ORIGEM_ESTRUTURA[e.origem]}
          {e.referencia_rotulo ? ` · ${e.referencia_rotulo}` : ""}
          {e.ref_externa ? ` · ref. externa ${e.ref_externa}` : ""}
          {e.formula_herdada_de ? ` · fórmula herdada de ${e.formula_herdada_de}` : ""}
        </p>
      )}

      {isAdmin ? (
        tiposQ.showSkeleton ? (
          <Skeleton className="h-64 w-full" />
        ) : tiposQ.isError && !tiposQ.data ? (
          <QueryErrorState query={tiposQ} title="Não foi possível carregar os tipos de bloco." />
        ) : (
          <EstruturaEditor
            detalhe={e}
            tipos={tiposQ.data ?? []}
            onRecarregar={async () => (await q.refetch()).data}
            onExcluida={() => navigate(VOLTAR, { replace: true })}
          />
        )
      ) : (
        <EstruturaLeitura detalhe={e} tipos={tiposQ.data ?? []} />
      )}
    </div>
  );
}

function Voltar() {
  return (
    <Link to={VOLTAR} className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Voltar para a Biblioteca
    </Link>
  );
}
