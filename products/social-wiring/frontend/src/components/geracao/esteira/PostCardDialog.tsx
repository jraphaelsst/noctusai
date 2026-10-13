/**
 * PostCardDialog — the Esteira post card (esteira-contract.md §6.2, FE-2).
 *
 * A THIN ADAPTER over the seed `CardHubDialog` (SW's `ClienteCardDialog` is the
 * reference consumer): chrome, rail, comments composer, timeline, checklists,
 * lembretes and anexos are the seed's; only the post-specific sections are ours
 * (`secoes/*`). Presentation is driven by `usePost` (polls while a headline batch runs).
 *
 * Loading rule: `isLoading` handed to the dialog is `showSkeleton` (`isPending && !data`);
 * a refetch keeps the card on screen.
 */
import { useState, type ReactNode } from "react";
import {
  CardHubDialog,
  ChecklistsSection,
  DescricaoSection,
  LembretesSubpage,
  dataHoraLocalParaIsoSP,
  isoParaDataHoraLocalSP,
  type CardDatas,
  type CardSubpage,
} from "@noctusai/lib/components";
import { Bell, FileText, Film, Lightbulb, Megaphone, MessageSquareText, ScrollText } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { CampoDataCommit } from "./CampoDataCommit";
import { useAtualizarPost, usePost } from "@/hooks/geracao/useEsteira";
import { flattenTimeline, postHub } from "@/hooks/geracao/usePostHub";
import { useIntegrationAccounts } from "@/hooks/useIntegrationAccounts";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { PostDetalhe, PostUpdate, RecorrenciaPost } from "@/types/esteira";
import { PostHeaderAcoes } from "./PostHeaderAcoes";
import { HeadlineSecao } from "./secoes/HeadlineSecao";
import { ProducaoSecao } from "./secoes/ProducaoSecao";
import { PublicacaoSecao } from "./secoes/PublicacaoSecao";
import { RoteiroSecao } from "./secoes/RoteiroSecao";

export type PostSubpageKey = "geral" | "headline" | "roteiro" | "producao" | "publicacao" | "lembretes";

export interface PostCardDialogProps {
  /** The post id from `?post=`; the dialog is open while it is set. */
  postId: string | null;
  /** Called on close so the page clears `?post=`. */
  onClose: () => void;
}

function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="text-muted-foreground">{rotulo}</span>
      {children}
    </label>
  );
}

type PatchFn = (p: PostUpdate, falha: string) => void;

const LEMBRETES: { rotulo: string; minutos: number }[] = [
  { rotulo: "No horário", minutos: 0 },
  { rotulo: "15 minutos antes", minutos: 15 },
  { rotulo: "1 hora antes", minutos: 60 },
  { rotulo: "1 dia antes", minutos: 1440 },
  { rotulo: "2 dias antes", minutos: 2880 },
];
const RECORRENCIAS: { rotulo: string; valor: RecorrenciaPost }[] = [
  { rotulo: "Diária", valor: "diaria" },
  { rotulo: "Semanal", valor: "semanal" },
  { rotulo: "Mensal", valor: "mensal" },
  { rotulo: "Anual", valor: "anual" },
];
const SELECT = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";

/**
 * Datas of the card hub, written through `PATCH /posts/{id}` (the seed hub's `/card` is read-only).
 * `data_entrega` / `entrega_concluida` come with the post; the reminder lead time and the
 * recurrence are only served by the hub resumo (`datas`).
 *
 * The lead time is only RECORDED: no reminder is created from it yet
 * (NOC-REMEDIATE[esteira-datas-lembrete]), so the copy never promises a notification.
 */
function DatasPost({
  post,
  resumo,
  onPatch,
}: {
  post: PostDetalhe;
  resumo: { data?: { datas?: CardDatas } | undefined; isPending: boolean; isError: boolean };
  onPatch: PatchFn;
}) {
  const datas = resumo.data?.datas;
  const entregaLocal = post.data_entrega ? isoParaDataHoraLocalSP(post.data_entrega) : "";
  const lembrete = datas?.lembrete_minutos_antes ?? null;
  const opcoesLembrete =
    lembrete !== null && !LEMBRETES.some((l) => l.minutos === lembrete)
      ? [...LEMBRETES, { rotulo: `${lembrete} min antes`, minutos: lembrete }]
      : LEMBRETES;
  const carregando = resumo.isPending && !resumo.data;
  const falhou = resumo.isError && !resumo.data;

  return (
    <fieldset className="space-y-3 rounded border p-3" data-testid="datas-post">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Datas</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo rotulo="Postagem prevista">
          <CampoDataCommit
            tipo="datetime-local"
            rotulo="Postagem prevista"
            salvo={entregaLocal}
            onCommit={(valor) => {
              // Explicit -03:00 (São Paulo has no DST): a naive datetime would be read in the DB zone.
              const iso = valor ? `${dataHoraLocalParaIsoSP(valor)}-03:00` : null;
              onPatch({ data_entrega: iso }, "Não foi possível salvar a data de postagem.");
            }}
          />
        </Campo>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            aria-label="Entrega concluída"
            checked={post.entrega_concluida}
            onChange={(e) => onPatch({ entrega_concluida: e.target.checked }, "Não foi possível atualizar a entrega.")}
          />
          Entrega concluída
        </label>
      </div>
      {carregando ? (
        <div className="h-9 animate-pulse rounded bg-muted" data-testid="datas-loading" />
      ) : falhou ? (
        <p className="text-sm text-destructive" role="alert" data-testid="datas-erro">
          Não foi possível carregar o lembrete e a recorrência.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="Antecedência do lembrete">
            <select
              aria-label="Antecedência do lembrete"
              className={SELECT}
              value={lembrete === null ? "" : String(lembrete)}
              onChange={(e) =>
                onPatch(
                  { lembrete_minutos_antes: e.target.value === "" ? null : Number(e.target.value) },
                  "Não foi possível salvar o lembrete.",
                )
              }
            >
              <option value="">Sem lembrete</option>
              {opcoesLembrete.map((l) => (
                <option key={l.minutos} value={l.minutos}>
                  {l.rotulo}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted-foreground">Apenas registrada no post por enquanto.</span>
          </Campo>
          <Campo rotulo="Recorrência">
            <select
              aria-label="Recorrência"
              className={SELECT}
              value={datas?.recorrencia ?? ""}
              onChange={(e) =>
                onPatch(
                  { recorrencia: (e.target.value || null) as RecorrenciaPost | null },
                  "Não foi possível salvar a recorrência.",
                )
              }
            >
              <option value="">Não repete</option>
              {RECORRENCIAS.map((r) => (
                <option key={r.valor} value={r.valor}>
                  {r.rotulo}
                </option>
              ))}
            </select>
          </Campo>
        </div>
      )}
    </fieldset>
  );
}

function GeralSecao({ post }: { post: PostDetalhe }) {
  const atualizar = useAtualizarPost();
  const resumoQ = postHub.useCardResumo(post.id);
  const notas = postHub.useNotaMutations(post.id);
  const checklistsQ = postHub.useChecklists(post.id);
  const checklistMut = postHub.useChecklistMutations(post.id);
  const contasQ = useIntegrationAccounts({ provider: "instagram", marcaId: post.marca_id });
  const contas = contasQ.data ?? [];

  const erro = (fallback: string) => (e: unknown) => toast.error(mensagemErroServidor(e, fallback));
  const patch: PatchFn = (p, falha) =>
    atualizar.mutate({ id: post.id, patch: p }, { onError: erro(falha) });

  return (
    <div className="space-y-4" data-testid="secao-geral">
      {post.motivo_bloqueio && (
        <p className="rounded border border-destructive/40 p-2 text-sm text-destructive" data-testid="motivo-bloqueio">
          Motivo do bloqueio: {post.motivo_bloqueio}
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Campo rotulo="Conta de destino">
          <select
            aria-label="Conta de destino"
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={post.conta?.id ?? ""}
            onChange={(e) => patch({ conta_id: e.target.value || null }, "Não foi possível alterar a conta.")}
          >
            <option value="">Sem conta</option>
            {contas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.account_label}
              </option>
            ))}
          </select>
        </Campo>
        <Campo rotulo="Gravação agendada">
          <CampoDataCommit
            tipo="date"
            rotulo="Gravação agendada"
            salvo={post.gravacao_em ? post.gravacao_em.slice(0, 10) : ""}
            // `gravacao_em` is a DATE column: send `YYYY-MM-DD`, never a datetime.
            onCommit={(dia) => patch({ gravacao_em: dia }, "Não foi possível salvar a gravação.")}
          />
        </Campo>
      </div>

      <DatasPost post={post} resumo={resumoQ} onPatch={patch} />

      <DescricaoSection
        corpo={resumoQ.data?.descricao?.corpo ?? ""}
        saving={notas.create.isPending}
        onSave={(corpo) =>
          notas.create.mutate({ corpo, tipo: "descricao" }, { onError: erro("Não foi possível salvar a descrição.") })
        }
      />

      <ChecklistsSection
        checklists={checklistsQ.data ?? []}
        loading={checklistsQ.isPending}
        onRemoveChecklist={(id) => checklistMut.removeChecklist.mutate(id)}
        onAddItem={(checklistId, texto) => checklistMut.addItem.mutate({ checklistId, texto })}
        onToggleItem={(checklistId, itemId, concluido) =>
          checklistMut.toggleItem.mutate({ checklistId, itemId, concluido })
        }
        onRemoveItem={(checklistId, itemId) => checklistMut.removeItem.mutate({ checklistId, itemId })}
      />
    </div>
  );
}

function LembretesSecao({ postId, membros }: { postId: string; membros: PostDetalhe["membros"] }) {
  const q = postHub.useLembretes(postId);
  const mut = postHub.useLembreteMutations(postId);
  return (
    <LembretesSubpage
      lembretes={q.data ?? []}
      loading={q.isPending && !q.data}
      refreshing={q.isFetching && !!q.data}
      error={q.isError && !q.data ? "Não foi possível carregar os lembretes." : null}
      responsaveis={membros}
      creating={mut.criar.isPending}
      onCreate={(body) => mut.criar.mutate(body)}
      onUpdate={(id, body) => mut.atualizar.mutate({ lembreteId: id, body })}
      onDelete={(id) => mut.remover.mutate(id)}
    />
  );
}

export function PostCardDialog({ postId, onClose }: PostCardDialogProps) {
  const open = !!postId;
  const postQ = usePost(postId);
  const post = postQ.data;
  const id = postId ?? "";
  const timelineQ = postHub.useTimeline(postId);
  const notas = postHub.useNotaMutations(id);

  const erro = postQ.isError && !post ? "erro" : null;
  const naoEncontrado = postQ.isError && (postQ.error as { status?: number } | null)?.status === 404;

  const subpages: CardSubpage<PostSubpageKey>[] = post
    ? [
        { key: "geral", label: "Geral", icon: FileText, render: () => <GeralSecao post={post} /> },
        { key: "headline", label: "Headline", icon: Lightbulb, render: () => <HeadlineSecao post={post} /> },
        { key: "roteiro", label: "Roteiro", icon: ScrollText, render: () => <RoteiroSecao post={post} /> },
        { key: "producao", label: "Produção", icon: Film, render: () => <ProducaoSecao post={post} /> },
        {
          key: "publicacao",
          label: "Publicação",
          icon: Megaphone,
          // Fields seed from the post once; remount when the post changes (not on every poll).
          render: () => <PublicacaoSecao key={post.id} post={post} />,
        },
        {
          key: "lembretes",
          label: "Lembretes",
          icon: Bell,
          render: () => <LembretesSecao postId={post.id} membros={post.membros} />,
        },
      ]
    : [{ key: "geral", label: "Geral", icon: MessageSquareText, render: () => null }];

  return (
    <CardHubDialog<PostSubpageKey>
      open={open}
      onClose={onClose}
      isLoading={postQ.showSkeleton}
      error={naoEncontrado ? null : erro}
      notFound={naoEncontrado}
      nome={post?.titulo ?? "Post"}
      testId="post-card-dialog"
      subpages={subpages}
      headerActions={
        post ? (
          <>
            {postQ.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
            <PostHeaderAcoes key={post.id} post={post} onExcluido={onClose} />
          </>
        ) : null
      }
      activity={{
        timeline: {
          entries: flattenTimeline(timelineQ.data?.pages),
          loading: timelineQ.isPending && !timelineQ.data,
          error: timelineQ.isError && !timelineQ.data ? "Não foi possível carregar a atividade." : null,
          hasMore: timelineQ.hasNextPage,
          loadingMore: timelineQ.isFetchingNextPage,
          onLoadMore: () => void timelineQ.fetchNextPage(),
        },
        composer: {
          posting: notas.create.isPending,
          onPost: (corpo) =>
            notas.create.mutate(
              { corpo },
              { onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível comentar.")) },
            ),
        },
      }}
    />
  );
}
