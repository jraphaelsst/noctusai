import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { STATUS_ROTULO, type StatusGeracao } from "./labels";

const ESTILO: Record<StatusGeracao, string> = {
  criando: "border-transparent bg-muted text-muted-foreground",
  perguntas: "border-transparent bg-amber-100 text-amber-800",
  processando: "border-transparent bg-blue-100 text-blue-800",
  completo: "border-transparent bg-emerald-100 text-emerald-800",
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
