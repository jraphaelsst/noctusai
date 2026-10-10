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
  type CardSubpage,
} from "@noctusai/lib/components";
import { Bell, FileText, Film, Lightbulb, Megaphone, MessageSquareText, ScrollText } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAtualizarPost, usePost } from "@/hooks/geracao/useEsteira";
import { flattenTimeline, postHub, useDatasPost } from "@/hooks/geracao/usePostHub";
import { useEquipe } from "@/hooks/geracao/useEsteira";
import { useIntegrationAccounts } from "@/hooks/useIntegrationAccounts";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { PostDetalhe } from "@/types/esteira";
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

function GeralSecao({ post }: { post: PostDetalhe }) {
  const [titulo, setTitulo] = useState(post.titulo);
  const atualizar = useAtualizarPost();
  const datas = useDatasPost(post.id);
  const resumoQ = postHub.useCardResumo(post.id);
  const notas = postHub.useNotaMutations(post.id);
  const checklistsQ = postHub.useChecklists(post.id);
  const checklistMut = postHub.useChecklistMutations(post.id);
  const equipeQ = useEquipe();
  const membrosMut = postHub.useSetMembrosMutation(post.id);
  const contasQ = useIntegrationAccounts({ provider: "instagram", marcaId: post.marca_id });
  const contas = contasQ.data ?? [];

  const erro = (fallback: string) => (e: unknown) => toast.error(mensagemErroServidor(e, fallback));
  const patch = (p: Parameters<typeof atualizar.mutate>[0]["patch"], falha: string) =>
    atualizar.mutate({ id: post.id, patch: p }, { onError: erro(falha) });

  const selecionados = post.membros.map((m) => m.id);
  const alternar = (id: string) =>
    membrosMut.mutate(selecionados.includes(id) ? selecionados.filter((x) => x !== id) : [...selecionados, id], {
      onError: erro("Não foi possível atualizar a equipe."),
    });

  return (
    <div className="space-y-4" data-testid="secao-geral">
      <Campo rotulo="Título">
        <div className="flex gap-2">
          <Input aria-label="Título do post" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
          <Button
            size="sm"
            disabled={!titulo.trim() || titulo.trim() === post.titulo || atualizar.isPending}
            onClick={() => patch({ titulo: titulo.trim() }, "Não foi possível renomear o post.")}
          >
            Salvar título
          </Button>
        </div>
      </Campo>

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
          <Input
            type="datetime-local"
            aria-label="Gravação agendada"
            defaultValue={isoParaDataHoraLocalSP(post.gravacao_em)}
            onBlur={(e) => {
              const iso = e.target.value ? dataHoraLocalParaIsoSP(e.target.value) : null;
              if (iso !== post.gravacao_em) patch({ gravacao_em: iso }, "Não foi possível salvar a gravação.");
            }}
          />
        </Campo>
        <Campo rotulo="Postagem prevista">
          <Input
            type="datetime-local"
            aria-label="Postagem prevista"
            defaultValue={isoParaDataHoraLocalSP(post.data_entrega)}
            onBlur={(e) => {
              const iso = e.target.value ? dataHoraLocalParaIsoSP(e.target.value) : null;
              if (iso !== post.data_entrega) {
                datas.mutate({ data_entrega: iso }, { onError: erro("Não foi possível salvar a data de postagem.") });
              }
            }}
          />
        </Campo>
      </div>

      <div className="space-y-1">
        <p className="text-sm text-muted-foreground">Equipe</p>
        {equipeQ.showSkeleton ? (
          <div className="h-8 animate-pulse rounded bg-muted" data-testid="equipe-loading" />
        ) : equipeQ.isError && !equipeQ.data ? (
          <p className="text-sm text-destructive">Não foi possível carregar a equipe.</p>
        ) : (equipeQ.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum membro na equipe ainda.</p>
        ) : (
          <div className="flex flex-wrap gap-1">
            {(equipeQ.data ?? [])
              .filter((m) => m.ativo || selecionados.includes(m.id))
              .map((m) => (
                <Button
                  key={m.id}
                  size="sm"
                  variant={selecionados.includes(m.id) ? "default" : "outline"}
                  aria-pressed={selecionados.includes(m.id)}
                  disabled={membrosMut.isPending}
                  onClick={() => alternar(m.id)}
                >
                  {m.nome}
                </Button>
              ))}
          </div>
        )}
      </div>

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
            <Badge variant="secondary" data-testid="post-marca">
              {post.marca_nome}
            </Badge>
            {postQ.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
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
