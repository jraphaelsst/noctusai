/**
 * "O que achou deste roteiro?" — Gostei / Não Gostei (+ reason on Não Gostei).
 * Contract §7.8 / §4.5 #38. Shared by EditarRoteiroModal and RoteiroAvancadoModal.
 */
import { useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useFeedbackRoteiro } from "@/hooks/geracao/useRoteiros";
import type { Roteiro } from "@/types/geracao";

export const MOTIVO_MAX = 1000;

function mensagem(e: unknown, fallback: string): string {
  const msg = e instanceof Error ? e.message.replace(/^\[\d+\]\s*/, "") : "";
  return msg || fallback;
}

export function FeedbackRoteiro({ roteiro }: { roteiro: Pick<Roteiro, "id" | "feedback" | "feedback_motivo"> }) {
  const feedback = useFeedbackRoteiro();
  const [motivoAberto, setMotivoAberto] = useState(false);
  const [motivo, setMotivo] = useState(roteiro.feedback_motivo ?? "");

  async function enviar(tipo: "gostei" | "nao_gostei", texto?: string) {
    try {
      await feedback.mutateAsync({ id: roteiro.id, feedback: tipo, motivo: texto });
      setMotivoAberto(false);
      toast.success("Obrigado pelo feedback!");
    } catch (e) {
      toast.error(mensagem(e, "Não foi possível enviar o feedback."));
    }
  }

  return (
    <div className="space-y-2" data-testid="feedback-roteiro">
      <p className="text-sm font-medium">O que achou deste roteiro?</p>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant={roteiro.feedback === "gostei" ? "default" : "outline"}
          aria-pressed={roteiro.feedback === "gostei"}
          disabled={feedback.isPending}
          onClick={() => enviar("gostei")}
        >
          <ThumbsUp className="mr-1 h-4 w-4" /> Gostei
        </Button>
        <Button
          type="button"
          size="sm"
          variant={roteiro.feedback === "nao_gostei" ? "default" : "outline"}
          aria-pressed={roteiro.feedback === "nao_gostei"}
          disabled={feedback.isPending}
          onClick={() => setMotivoAberto(true)}
        >
          <ThumbsDown className="mr-1 h-4 w-4" /> Não Gostei
        </Button>
      </div>
      {motivoAberto && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Não gostou do roteiro?</p>
          <Textarea
            aria-label="Motivo"
            rows={3}
            maxLength={MOTIVO_MAX}
            placeholder="Conte o que não funcionou (opcional)"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
          />
          <Button
            type="button"
            size="sm"
            disabled={feedback.isPending}
            onClick={() => enviar("nao_gostei", motivo.trim() || undefined)}
          >
            Enviar
          </Button>
        </div>
      )}
    </div>
  );
}
