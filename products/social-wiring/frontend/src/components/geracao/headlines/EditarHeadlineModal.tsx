/**
 * Edit a headline's text (contract §4.4 #27: PATCH keeps `texto_original`).
 * Used by P1 Dashboard, P2 Chat and P7–P9 Headlines. When the host passes a
 * `roteiroBloco` (Favoritas / Sugeridas, page-map-v2 §18/§19) it becomes
 * CoreStudio's "Editar Headline e Roteiro": the roteiro text is edited through
 * FE-3's `useEdicaoRoteiro` (optimistic-lock 409 included); blank = unchanged.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useEditarHeadline } from "@/hooks/geracao/useHeadlineMutations";
import type { Headline, Roteiro } from "@/types/geracao";
import { HEADLINE_TEXTO_MAX } from "../labels";
import { CONTEUDO_MAX, MSG_CONFLITO, type useEdicaoRoteiro } from "../roteiro/RoteiroEdicao";

export interface RoteiroBloco {
  /** Undefined while loading or when the roteiro is not ready to edit. */
  roteiro: Roteiro | undefined;
  carregando: boolean;
  edicao: ReturnType<typeof useEdicaoRoteiro>;
  onRecarregar: () => void;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  headline: Pick<Headline, "id" | "texto" | "texto_original"> | null;
  onSalvo?: (h: Headline) => void;
  roteiroBloco?: RoteiroBloco;
}

export function EditarHeadlineModal({ open, onOpenChange, headline, onSalvo, roteiroBloco }: Props) {
  const [texto, setTexto] = useState("");
  const editar = useEditarHeadline();

  useEffect(() => {
    if (open && headline) setTexto(headline.texto);
  }, [open, headline]);

  const limpo = texto.trim();
  const excedeu = limpo.length > HEADLINE_TEXTO_MAX;
  const alterou = !!headline && limpo !== headline.texto.trim();
  const edicao = roteiroBloco?.edicao;
  const roteiroEditavel = !!roteiroBloco?.roteiro;
  // Blank roteiro = "don't change it" (CoreStudio); an untouched textarea is unchanged too.
  const roteiroAlterado = roteiroEditavel && !!edicao && edicao.alterou && edicao.conteudo.trim() !== "";
  const salvando = editar.isPending || !!edicao?.salvando;
  const podeSalvar =
    !!headline &&
    limpo.length > 0 &&
    !excedeu &&
    (alterou || roteiroAlterado) &&
    (!roteiroAlterado || !!edicao?.valido) &&
    !salvando;

  async function salvar() {
    if (!headline || !podeSalvar) return;
    try {
      if (alterou) {
        const salva = await editar.mutateAsync({ id: headline.id, texto: limpo });
        toast.success("Headline atualizada.");
        onSalvo?.(salva);
      }
    } catch (e) {
      toast.error(e instanceof Error && e.message ? e.message : "Não foi possível salvar a headline.");
      return;
    }
    if (roteiroAlterado && edicao) {
      // Keeps the modal open on a 409 / failure (edicao.conflito / toast already surfaced).
      const r = await edicao.salvar();
      if (!r) return;
    }
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !salvando && onOpenChange(o)}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{roteiroBloco ? "Editar Headline e Roteiro" : "Editar headline"}</DialogTitle>
          <DialogDescription>O texto original gerado pela IA é preservado.</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="geracao-editar-headline">Headline</Label>
          <Textarea
            id="geracao-editar-headline"
            rows={4}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            aria-invalid={excedeu}
          />
          <p className={`text-xs ${excedeu ? "text-destructive" : "text-muted-foreground"}`}>
            {limpo.length}/{HEADLINE_TEXTO_MAX} caracteres
          </p>
          {headline?.texto_original && headline.texto_original !== headline.texto && (
            <p className="text-xs text-muted-foreground">Original: {headline.texto_original}</p>
          )}
        </div>
        {roteiroBloco && (
          <div className="space-y-1.5">
            {edicao?.conflito && (
              <div role="alert" className="flex items-center justify-between rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
                <span>{MSG_CONFLITO}</span>
                <Button type="button" size="sm" variant="outline" onClick={roteiroBloco.onRecarregar}>
                  Recarregar
                </Button>
              </div>
            )}
            {roteiroBloco.carregando ? (
              <Skeleton className="h-32 w-full" data-testid="editar-headline-roteiro-skeleton" />
            ) : roteiroEditavel && edicao ? (
              <>
                <Label htmlFor="geracao-editar-headline-roteiro">Roteiro</Label>
                <Textarea
                  id="geracao-editar-headline-roteiro"
                  rows={8}
                  className="font-mono text-sm"
                  placeholder="Deixe em branco para não alterar o roteiro"
                  value={edicao.conteudo}
                  onChange={(e) => edicao.setConteudo(e.target.value)}
                  aria-invalid={edicao.conteudo.length > CONTEUDO_MAX}
                />
                <p className="text-xs text-muted-foreground">
                  Deixar em branco mantém o roteiro atual · {edicao.conteudo.length.toLocaleString("pt-BR")}/
                  {CONTEUDO_MAX.toLocaleString("pt-BR")} caracteres
                </p>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                O roteiro desta headline ainda não está pronto para edição.
              </p>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" disabled={salvando} onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button disabled={!podeSalvar} onClick={salvar}>
            {salvando ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
