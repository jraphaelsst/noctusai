/**
 * Post card header actions (esteira-contract.md §6.2): inline title edit, marca chip,
 * stage select, the seed `MembrosPopover` over `cs_equipe`, and the ⋯ menu
 * (Arquivar / Excluir, both confirmed).
 *
 * The seed `CardHubDialog` owns the `<h2>` title, so the inline edit lives here: a pencil
 * swaps the header slot for an input (Enter/Salvar saves, Esc cancels).
 */
import { useState } from "react";
import { MembrosPopover } from "@noctusai/lib/components";
import { MoreHorizontal, Pencil } from "lucide-react";
import { toast } from "sonner";

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
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useAtualizarPost, useEquipe, useExcluirPost } from "@/hooks/geracao/useEsteira";
import { postHub } from "@/hooks/geracao/usePostHub";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { PostDetalhe } from "@/types/esteira";
import { EtapaSelect } from "./EtapaSelect";

export function PostHeaderAcoes({ post, onExcluido }: { post: PostDetalhe; onExcluido: () => void }) {
  const [renomeando, setRenomeando] = useState(false);
  const [titulo, setTitulo] = useState(post.titulo);
  const [membrosAberto, setMembrosAberto] = useState(false);
  const [confirmar, setConfirmar] = useState<"arquivar" | "excluir" | null>(null);
  const atualizar = useAtualizarPost();
  const excluir = useExcluirPost();
  const equipeQ = useEquipe();
  const membrosMut = postHub.useSetMembrosMutation(post.id);

  const selecionados = post.membros.map((m) => m.id);
  const equipe = (equipeQ.data ?? []).filter((m) => m.ativo || selecionados.includes(m.id));
  const erro = (fallback: string) => (e: unknown) => toast.error(mensagemErroServidor(e, fallback));

  function salvarTitulo() {
    const t = titulo.trim();
    if (!t || t === post.titulo) return setRenomeando(false);
    atualizar.mutate(
      { id: post.id, patch: { titulo: t } },
      { onSuccess: () => setRenomeando(false), onError: erro("Não foi possível renomear o post.") },
    );
  }

  function executar() {
    if (confirmar === "arquivar") {
      atualizar.mutate(
        { id: post.id, patch: { arquivado: !post.arquivado } },
        {
          onSuccess: () => toast.success(post.arquivado ? "Post desarquivado." : "Post arquivado."),
          onError: erro("Não foi possível arquivar o post."),
        },
      );
    } else if (confirmar === "excluir") {
      excluir.mutate(post.id, {
        onSuccess: () => {
          toast.success("Post excluído.");
          onExcluido();
        },
        onError: erro("Não foi possível excluir o post."),
      });
    }
    setConfirmar(null);
  }

  return (
    <>
      {renomeando ? (
        <div className="flex items-center gap-1" data-testid="titulo-edicao">
          <Input
            aria-label="Título do post"
            className="h-8 w-48"
            autoFocus
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") salvarTitulo();
              if (e.key === "Escape") {
                setTitulo(post.titulo);
                setRenomeando(false);
              }
            }}
          />
          <Button size="sm" disabled={!titulo.trim() || atualizar.isPending} onClick={salvarTitulo}>
            Salvar
          </Button>
        </div>
      ) : (
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8"
          aria-label="Renomear post"
          onClick={() => {
            setTitulo(post.titulo);
            setRenomeando(true);
          }}
        >
          <Pencil className="h-4 w-4" />
        </Button>
      )}
      <Badge variant="secondary" data-testid="post-marca">
        {post.marca_nome}
      </Badge>
      <EtapaSelect postId={post.id} etapaId={post.etapa_id} />
      <MembrosPopover
        open={membrosAberto}
        onOpenChange={setMembrosAberto}
        allMembros={equipe}
        selectedMembroIds={selecionados}
        saving={membrosMut.isPending}
        onToggleMembro={(id) =>
          membrosMut.mutate(selecionados.includes(id) ? selecionados.filter((x) => x !== id) : [...selecionados, id], {
            onError: erro("Não foi possível atualizar a equipe."),
          })
        }
      />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="icon" variant="outline" className="h-8 w-8" aria-label="Mais ações">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setConfirmar("arquivar")}>
            {post.arquivado ? "Desarquivar" : "Arquivar"}
          </DropdownMenuItem>
          <DropdownMenuItem className="text-destructive" onSelect={() => setConfirmar("excluir")}>
            Excluir
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <AlertDialog open={confirmar !== null} onOpenChange={(o) => !o && setConfirmar(null)}>
        <AlertDialogContent data-testid="confirmar-acao-post">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmar === "excluir" ? "Excluir este post?" : post.arquivado ? "Desarquivar este post?" : "Arquivar este post?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmar === "excluir"
                ? "O post, seus comentários, checklists e anexos serão apagados. A headline e o roteiro continuam na biblioteca."
                : post.arquivado
                  ? "O post volta a aparecer no quadro."
                  : "O post some do quadro, mas pode ser reativado em “Mostrar arquivados”."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={executar}>{confirmar === "excluir" ? "Excluir" : "Confirmar"}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
