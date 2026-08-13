/**
 * RevisaoGrupoCard — one review-queue group: its reason code, the shared
 * key, every candidate's evidence (name, touch count, contact window), and
 * the two operator actions (merge / manter separados). PROJECT.md §5 names
 * exactly these two actions — no candidate-survivor picker is offered (see
 * `useClientesRevisao.ts` file header, assumption 2).
 *
 * C5 shows extra hint copy (`REVISAO_MOTIVO_HINT`) — the dangerous case
 * where a shared phone/email is two genuinely different people
 * (PROJECT.md §3: the +5511974781330 census finding). Showing the evidence
 * — the shared key, every candidate's name and touch count — IS the C5
 * mitigation; a human reads it, not a heuristic.
 */
import { GitMerge, ShieldAlert, Users2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatDate } from "@noctusai/lib";
import {
  REVISAO_MOTIVO_HINT,
  REVISAO_MOTIVO_LABEL,
  type RevisaoGrupo,
} from "@/hooks/useClientesRevisao";
import { formatCountOrDash } from "@/hooks/useClientes";

export interface RevisaoGrupoCardProps {
  grupo: RevisaoGrupo;
  onMerge: (grupo: RevisaoGrupo) => void;
  onManterSeparados: (grupo: RevisaoGrupo) => void;
  merging: boolean;
  rejecting: boolean;
}

export function RevisaoGrupoCard({
  grupo,
  onMerge,
  onManterSeparados,
  merging,
  rejecting,
}: RevisaoGrupoCardProps) {
  const busy = merging || rejecting;
  const isC5 = grupo.motivo === "C5";

  return (
    <Card data-testid="revisao-grupo-card" data-motivo={grupo.motivo}>
      <CardContent className="space-y-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Badge
            variant="outline"
            data-testid="revisao-motivo-badge"
            className={
              isC5
                ? "border-destructive/40 bg-destructive/10 text-destructive"
                : "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400"
            }
          >
            {isC5 && <ShieldAlert className="mr-1 h-3 w-3" />}
            {grupo.motivo} · {REVISAO_MOTIVO_LABEL[grupo.motivo]}
          </Badge>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Users2 className="h-3.5 w-3.5" />
            {grupo.candidatos.length} candidatos
          </span>
        </div>

        <p className="text-xs text-muted-foreground" data-testid="revisao-motivo-hint">
          {REVISAO_MOTIVO_HINT[grupo.motivo]}
        </p>

        <p className="text-xs text-muted-foreground">
          Chave compartilhada:{" "}
          <span className="font-mono text-foreground">{grupo.chave_canonica}</span>
        </p>

        <ul className="space-y-2 rounded-md border border-border bg-muted/30 p-3">
          {grupo.candidatos.map((c) => (
            <li
              key={c.id}
              data-testid="revisao-candidato"
              className="flex flex-wrap items-center justify-between gap-2 text-sm"
            >
              <span className="font-medium">{c.nome}</span>
              <span className="flex gap-3 text-xs text-muted-foreground">
                <span>{formatCountOrDash(c.touch_count)} toques</span>
                <span>
                  {formatDate(c.primeiro_contato_em)} – {formatDate(c.ultimo_contato_em)}
                </span>
              </span>
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            size="sm"
            disabled={busy}
            onClick={() => onMerge(grupo)}
            data-testid="revisao-mesclar-btn"
          >
            <GitMerge className="mr-2 h-4 w-4" />
            {merging ? "Mesclando…" : "Mesclar"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => onManterSeparados(grupo)}
            data-testid="revisao-manter-separados-btn"
          >
            {rejecting ? "Salvando…" : "Manter separados"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
