/**
 * Edit a headline's text (contract §4.4 #27: PATCH keeps `texto_original`).
 * Used by P1 Dashboard, P2 Chat and P7–P9 Headlines.
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
import { Textarea } from "@/components/ui/textarea";
import { useEditarHeadline } from "@/hooks/geracao/useHeadlineMutations";
import type { Headline } from "@/types/geracao";
import { HEADLINE_TEXTO_MAX } from "../labels";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  headline: Pick<Headline, "id" | "texto" | "texto_original"> | null;
  onSalvo?: (h: Headline) => void;
}

export function EditarHeadlineModal({ open, onOpenChange, headline, onSalvo }: Props) {
  const [texto, setTexto] = useState("");
  const editar = useEditarHeadline();

  useEffect(() => {
    if (open && headline) setTexto(headline.texto);
  }, [open, headline]);

  const limpo = texto.trim();
  const excedeu = limpo.length > HEADLINE_TEXTO_MAX;
  const alterou = !!headline && limpo !== headline.texto.trim();
  const podeSalvar = !!headline && limpo.length > 0 && !excedeu && alterou && !editar.isPending;

  async function salvar() {
    if (!headline || !podeSalvar) return;
    try {
      const salva = await editar.mutateAsync({ id: headline.id, texto: limpo });
      toast.success("Headline atualizada.");
      onSalvo?.(salva);
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error && e.message ? e.message : "Não foi possível salvar a headline.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !editar.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Editar headline</DialogTitle>
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
        <DialogFooter>
          <Button variant="outline" disabled={editar.isPending} onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button disabled={!podeSalvar} onClick={salvar}>
            {editar.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
