/**
 * Per-field provenance marker — PLATFORM ADMINS ONLY (contract DC2, §11.3). A field in `referencia` or
 * `ia_sugerido` is "pending review": the badge says who filled it and offers `Confirmar` (flips it to
 * `admin` without touching the content). `fonte` and `admin` fields render nothing. Orgs never see this:
 * the server omits `proveniencia` for them, so there is nothing to render.
 */
import { Check } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ehPendente, ROTULO_PROVENIENCIA } from "./rotulos";
import type { OrigemCampo } from "@/types/estruturas";

interface Props {
  origem: OrigemCampo | undefined;
  /** What the badge is about, for the accessible name ("a fórmula", "o tempo do bloco 2"). */
  campo: string;
  onConfirmar?: () => void;
  /** Dirty draft or a write in flight: confirming would race the edit. */
  desabilitado?: boolean;
  motivoDesabilitado?: string;
}

export function ProvenienciaBadge({ origem, campo, onConfirmar, desabilitado, motivoDesabilitado }: Props) {
  if (!ehPendente(origem)) return null;
  return (
    <span className="inline-flex items-center gap-1.5" data-testid="proveniencia-badge">
      <Badge
        variant="outline"
        className="border-amber-500/50 bg-amber-500/10 font-normal text-amber-800 dark:text-amber-300"
      >
        {ROTULO_PROVENIENCIA[origem]}
      </Badge>
      {onConfirmar && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-6 gap-1 px-2 text-xs"
          disabled={desabilitado}
          title={desabilitado ? motivoDesabilitado : undefined}
          aria-label={`Confirmar ${campo}`}
          onClick={onConfirmar}
        >
          <Check className="h-3 w-3" aria-hidden="true" /> Confirmar
        </Button>
      )}
    </span>
  );
}
