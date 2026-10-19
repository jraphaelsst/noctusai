/** "Ver o que a Julia sabe" — renders GET /preview (the exact markdown the agent receives). */
import { AlertCircle, Loader2 } from "lucide-react";
import { Dialog, DialogBody, DialogFooter, DialogHeader } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { usePreviewConhecimento } from "@/hooks/useJuliaConhecimento";

export function PreviewModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const q = usePreviewConhecimento(open);
  const showSkeleton = q.isPending && !q.data;
  return (
    <Dialog open={open} onClose={onClose} title="O que a Julia sabe" className="max-w-2xl">
      <DialogHeader><h2 className="text-lg font-semibold">O que a Julia sabe</h2></DialogHeader>
      <DialogBody>
        {showSkeleton ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="preview-skeleton"><Loader2 className="h-4 w-4 animate-spin" /> Carregando…</div>
        ) : q.data ? (
          q.data.markdown.trim() ? <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap text-sm" data-testid="preview-md">{q.data.markdown}</pre>
            : <p className="text-sm text-muted-foreground" data-testid="preview-vazio">Ainda não há informações cadastradas.</p>
        ) : (
          <div className="flex items-center gap-2 text-sm" data-testid="preview-erro"><AlertCircle className="h-4 w-4 text-destructive" /> Não foi possível carregar.
            <Button size="sm" variant="outline" onClick={() => q.refetch()}>Tentar de novo</Button></div>
        )}
      </DialogBody>
      <DialogFooter><Button variant="outline" onClick={onClose}>Fechar</Button></DialogFooter>
    </Dialog>
  );
}
