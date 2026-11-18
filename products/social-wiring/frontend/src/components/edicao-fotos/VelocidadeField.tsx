/**
 * VelocidadeField -- Urgente / Econômico picker for a Edição de Fotos batch. Econômico is selectable only when the
 * org's editor model supports it (`economicoDisponivel`, server-computed); otherwise it renders locked with the
 * server's reason. Extracted from `NovoLote` so ImobShotAI's funnel reuses it. Presentational.
 */
import { Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type { LoteVelocidade } from "@/hooks/useEdicaoFotos";

export interface VelocidadeFieldProps {
  velocidade: LoteVelocidade | null;
  onChange: (v: LoteVelocidade) => void;
  /** The org settings (default speed) are still loading. */
  carregando: boolean;
  economicoDisponivel: boolean;
  economicoBloqueadoMotivo: string | null;
  padraoEconomicoIndisponivel: boolean;
  /** The org default could not be loaded and nothing was chosen yet. */
  mostrarErroPadrao: boolean;
  disabled?: boolean;
}

export function VelocidadeField({
  velocidade,
  onChange,
  carregando,
  economicoDisponivel,
  economicoBloqueadoMotivo,
  padraoEconomicoIndisponivel,
  mostrarErroPadrao,
  disabled = false,
}: VelocidadeFieldProps) {
  return (
    <div className="space-y-2">
      <Label>Velocidade</Label>
      {carregando ? (
        <div data-testid="novo-lote-velocidade-loading">
          <Skeleton className="h-8 w-56" />
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={velocidade === "urgente" ? "default" : "outline"}
            size="sm"
            onClick={() => onChange("urgente")}
            disabled={disabled}
            aria-pressed={velocidade === "urgente"}
          >
            Urgente
          </Button>
          {economicoDisponivel ? (
            <Button
              type="button"
              variant={velocidade === "economico" ? "default" : "outline"}
              size="sm"
              onClick={() => onChange("economico")}
              disabled={disabled}
              aria-pressed={velocidade === "economico"}
            >
              Econômico
            </Button>
          ) : (
            <span
              className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold text-muted-foreground"
              title={economicoBloqueadoMotivo ?? "Indisponível para o modelo da organização"}
            >
              <Lock className="h-3 w-3" /> Econômico (bloqueado)
            </span>
          )}
        </div>
      )}
      {velocidade === "economico" && (
        <p className="text-xs text-muted-foreground">
          Econômico: processado em lote pela OpenAI, com 50% de desconto — pode levar até 24h.
        </p>
      )}
      {!economicoDisponivel && economicoBloqueadoMotivo && (
        <p className="text-xs text-muted-foreground">Motivo: {economicoBloqueadoMotivo}</p>
      )}
      {padraoEconomicoIndisponivel && (
        <p role="status" className="text-xs text-warning-foreground">
          O padrão da organização é Econômico, mas ele está indisponível para o modelo atual — este lote usará Urgente.
        </p>
      )}
      {mostrarErroPadrao && (
        <p role="alert" className="text-xs text-destructive">
          Não foi possível carregar o padrão da organização — escolha a velocidade.
        </p>
      )}
    </div>
  );
}
