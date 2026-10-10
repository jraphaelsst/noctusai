/** AI review verdict for one answer: chip + reason + accept/dismiss (contract §6). */
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Answer } from "@/types/cerebro";

interface Props {
  answer: Answer;
  pendente?: boolean;
  onDecidir: (action: "accept" | "dismiss") => void;
}

export function SugestaoRevisao({ answer, pendente = false, onDecidir }: Props) {
  const { verdict, reason, improved } = answer.review;
  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-sm" data-testid="sugestao-revisao">
      <Badge variant={verdict === "approved" ? "secondary" : "destructive"}>
        {verdict === "approved" ? "Aprovada" : "Rejeitada"}
      </Badge>
      {reason && <p>Motivo: {reason}</p>}
      {improved ? (
        <>
          <div>
            <p className="font-medium">Resposta sugerida</p>
            <p className="whitespace-pre-wrap text-muted-foreground">{improved}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={pendente} onClick={() => onDecidir("accept")}>
              Usar sugestão
            </Button>
            <Button size="sm" variant="outline" disabled={pendente} onClick={() => onDecidir("dismiss")}>
              Manter minha resposta
            </Button>
          </div>
        </>
      ) : (
        <Button size="sm" variant="outline" disabled={pendente} onClick={() => onDecidir("dismiss")}>
          OK
        </Button>
      )}
    </div>
  );
}
