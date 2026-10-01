/**
 * Status chip for one party certidão cell, with the same tooltip detail as
 * `CertidoesMatrizSection` (Número / Emitida em / Válida até) plus the stale
 * warning. Text always travels with the color.
 */
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDate } from "@/lib/utils";
import type { CertidaoParteCelula } from "@/types/certidoesPartes";

import { avisoVencida, CHIP_ESTILO, chipDaCelula } from "./certidoesCelula";

export function CertidaoCelulaChip({
  celula,
  testId,
}: {
  celula: CertidaoParteCelula;
  testId?: string;
}) {
  const chip = chipDaCelula(celula);
  const aviso = avisoVencida(celula);
  const temDetalhe =
    celula.numero ||
    celula.emitida_em ||
    celula.validade_ate ||
    celula.analise_ia ||
    celula.erro_mensagem ||
    aviso;
  const corpo = (
    <span
      data-testid={testId}
      className={`inline-block rounded px-2 py-1 text-xs font-medium ${CHIP_ESTILO[chip.tom]}`}
    >
      {chip.rotulo}
    </span>
  );
  if (!temDetalhe) return corpo;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{corpo}</TooltipTrigger>
      <TooltipContent className="max-w-xs space-y-1 text-xs">
        {celula.numero && <p>Número: {celula.numero}</p>}
        {celula.emitida_em && <p>Emitida em: {formatDate(celula.emitida_em)}</p>}
        {celula.validade_ate && <p>Válida até: {formatDate(celula.validade_ate)}</p>}
        {aviso && <p className="text-amber-300">{aviso}</p>}
        {celula.analise_ia && <p>{celula.analise_ia}</p>}
        {celula.erro_mensagem && <p className="text-red-300">{celula.erro_mensagem}</p>}
      </TooltipContent>
    </Tooltip>
  );
}
