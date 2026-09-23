/**
 * Per-file result list shared by `KnowledgeUploadDialog` and
 * `SkillFilesUploadDialog` (CONTRACT.md §G items 1/2) — "a final per-file
 * result summary that lists failures with their reason" applies to both
 * uploaders identically, so the rendering lives once.
 */
import { AlertCircle, CheckCircle2, MinusCircle, RefreshCcw } from "lucide-react";
import { Badge } from "@noctusai/lib/design-system";

export type BatchUploadStatus = "criado" | "atualizado" | "inalterado" | "erro";

export interface BatchUploadResultEntry {
  key: string;
  label: string;
  status: BatchUploadStatus;
  erro?: string;
}

const STATUS_LABEL: Record<BatchUploadStatus, string> = {
  criado: "criado",
  atualizado: "atualizado",
  inalterado: "sem alteração",
  erro: "falhou",
};

const STATUS_ICON: Record<BatchUploadStatus, typeof CheckCircle2> = {
  criado: CheckCircle2,
  atualizado: RefreshCcw,
  inalterado: MinusCircle,
  erro: AlertCircle,
};

const STATUS_VARIANT: Record<BatchUploadStatus, "default" | "outline" | "muted" | "destructive"> = {
  criado: "default",
  atualizado: "outline",
  inalterado: "muted",
  erro: "destructive",
};

export function BatchUploadResultList({ results }: { results: BatchUploadResultEntry[] }) {
  if (results.length === 0) return null;
  const failed = results.filter((r) => r.status === "erro").length;
  return (
    <div className="space-y-2" data-testid="batch-upload-results">
      <p className="text-xs font-medium text-foreground">
        {results.length} arquivo{results.length === 1 ? "" : "s"} processado{results.length === 1 ? "" : "s"}
        {failed > 0 && <span className="text-destructive"> · {failed} com falha</span>}
      </p>
      <ul className="max-h-64 space-y-1 overflow-y-auto rounded-md border border-border p-2 text-xs">
        {results.map((r) => {
          const Icon = STATUS_ICON[r.status];
          return (
            <li key={r.key} className="flex items-start gap-2" data-testid={`batch-upload-result-${r.key}`}>
              <Icon className={`mt-0.5 h-3.5 w-3.5 flex-shrink-0 ${r.status === "erro" ? "text-destructive" : "text-muted-foreground"}`} />
              <div className="min-w-0 flex-1">
                <span className="font-mono">{r.label}</span>{" "}
                <Badge variant={STATUS_VARIANT[r.status]}>{STATUS_LABEL[r.status]}</Badge>
                {r.status === "erro" && r.erro && <p className="mt-0.5 text-destructive">{r.erro}</p>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
