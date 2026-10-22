/** "N de M textos" + the missing required list (S3a §4). Renders nothing when the server sends null (legado). */
import { Badge } from "@noctusai/lib/design-system";
import type { ConteudoStatusDetail } from "@/api/studio/types-geracao";

export function CompletudeCard({ status }: { status: ConteudoStatusDetail | null | undefined }) {
  if (!status) return null;
  return (
    <div className="rounded-lg border border-border bg-card p-4" data-testid="completude-card">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Completude</p>
      <p className="mt-2 text-xl font-semibold tabular-nums" data-testid="completude-contagem">
        {status.textos_preenchidos} de {status.textos_total} textos
      </p>
      {status.obrigatorios_faltando.length > 0 ? (
        <div className="mt-2 space-y-1" data-testid="completude-faltando">
          <p className="text-xs text-muted-foreground">Obrigatórios faltando:</p>
          <div className="flex flex-wrap gap-1">
            {status.obrigatorios_faltando.map((c) => (
              <Badge key={c} variant="destructive" className="font-mono">
                {c}
              </Badge>
            ))}
          </div>
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">Nenhum texto obrigatório faltando.</p>
      )}
    </div>
  );
}

/** Badge for an item produced by AI generation; `estado` "editado" once a human changed it. */
export function GeradoBadge({ estado }: { estado: "gerado" | "editado" | undefined }) {
  if (!estado) return null;
  return (
    <Badge variant="outline" data-testid={`gerado-${estado}`}>
      {estado === "gerado" ? "Gerado por IA" : "Gerado · editado"}
    </Badge>
  );
}
