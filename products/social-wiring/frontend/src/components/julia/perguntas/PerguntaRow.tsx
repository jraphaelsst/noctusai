/** One essential question: switch + "Qualificatória" checkbox + locked/limit reasons. */
import { Lock } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import type { LaisPergunta } from "@/hooks/useLaisPerguntas";

export const MSG_LIMITE = "Você atingiu o limite de perguntas adicionadas";
export const MSG_LIMITE_QUALIF = "Você atingiu o limite de perguntas qualificatórias";
export const MSG_BLOQUEADA = "Esta pergunta é essencial para a identificação da operação correta";
export const MSG_CRITERIO = "Para desativar, primeiro desative os critérios de envio que usam esta pergunta";

export interface PerguntaRowProps {
  pergunta: LaisPergunta;
  ativa: boolean;
  qualificatoria: boolean;
  limiteAtivas: boolean;
  limiteQualif: boolean;
  disabled: boolean;
  onToggle: (ativa: boolean) => void;
  onQualificatoria: (v: boolean) => void;
}

export function PerguntaRow({
  pergunta: p,
  ativa,
  qualificatoria,
  limiteAtivas,
  limiteQualif,
  disabled,
  onToggle,
  onQualificatoria,
}: PerguntaRowProps) {
  let motivo: string | null = null;
  if (p.bloqueada) motivo = MSG_BLOQUEADA;
  else if (ativa && p.usada_em_criterio) motivo = MSG_CRITERIO;
  else if (!ativa && limiteAtivas) motivo = MSG_LIMITE;
  const switchOff = disabled || motivo !== null;
  const qualifOff = disabled || !ativa || (!qualificatoria && limiteQualif);
  const motivoQualif = !qualificatoria && ativa && limiteQualif ? MSG_LIMITE_QUALIF : undefined;

  return (
    <li className="flex items-start justify-between gap-4 py-3" data-testid={`pergunta-${p.chave}`}>
      <div className="min-w-0">
        <p className="flex items-center gap-1 text-sm font-medium">
          {p.bloqueada && <Lock className="h-3 w-3 text-muted-foreground" aria-hidden />}
          {p.bloqueada ? "Objetivo: comprar ou alugar" : p.label}
        </p>
        {p.dica && <p className="text-xs text-muted-foreground">{p.dica}</p>}
        {motivo && (
          <p className="text-xs text-amber-700" data-testid={`motivo-${p.chave}`}>
            {motivo}
          </p>
        )}
      </div>
      <div className="flex flex-shrink-0 items-center gap-4">
        <label
          className="flex items-center gap-2 text-xs"
          title={motivoQualif}
          data-testid={`qualif-wrap-${p.chave}`}
        >
          <Checkbox
            checked={ativa && qualificatoria}
            disabled={qualifOff}
            onCheckedChange={(v) => onQualificatoria(v === true)}
            aria-label={`Qualificatória: ${p.label}`}
            data-testid={`qualif-${p.chave}`}
          />
          Qualificatória
        </label>
        <span title={motivo ?? undefined}>
          <Switch
            checked={ativa}
            disabled={switchOff}
            onCheckedChange={onToggle}
            aria-label={`Ativar pergunta: ${p.label}`}
            data-testid={`switch-${p.chave}`}
          />
        </span>
      </div>
    </li>
  );
}
