import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { STATUS_ROTULO, type StatusGeracao } from "./labels";

const ESTILO: Record<StatusGeracao, string> = {
  criando: "border-transparent bg-muted text-muted-foreground",
  perguntas: "border-transparent bg-warning-light text-warning-foreground",
  processando: "border-transparent bg-info-light text-info",
  completo: "border-transparent bg-success-light text-success",
  falha: "border-transparent bg-destructive/10 text-destructive",
};

interface Props {
  status: StatusGeracao;
  className?: string;
}

/** Real job status (Criando / Processando / Completo / Falha, + Perguntas for roteiros). */
export function StatusBadge({ status, className }: Props) {
  return (
    <Badge variant="outline" data-status={status} className={cn(ESTILO[status], className)}>
      {STATUS_ROTULO[status]}
    </Badge>
  );
}
