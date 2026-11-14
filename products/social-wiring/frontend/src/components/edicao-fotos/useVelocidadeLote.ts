/**
 * useVelocidadeLote -- the speed (Urgente / Econômico) a new Edição de Fotos batch will use. The preselection is the
 * org's `velocidade_padrao`; an Econômico default or choice the org cannot use is SAID (`padraoEconomicoIndisponivel`),
 * never silently swapped; if the org settings failed to load nothing is preselected and the user must choose.
 * Extracted from `NovoLote` so ImobShotAI's funnel applies the same rule.
 */
import { useState } from "react";

import {
  fotosPermissions,
  type Capacidades,
  type LoteVelocidade,
  type OrgConfiguracoes,
} from "@/hooks/useEdicaoFotos";

export function useVelocidadeLote(
  capacidades: Capacidades | null | undefined,
  configuracoes: OrgConfiguracoes | null | undefined,
) {
  const [escolhida, setEscolhida] = useState<LoteVelocidade | null>(null);
  const economicoDisponivel = fotosPermissions.economicoDisponivel(capacidades);
  const economicoBloqueadoMotivo = fotosPermissions.economicoBloqueadoMotivo(capacidades);

  const padraoEconomicoIndisponivel = configuracoes?.velocidade_padrao === "economico" && !economicoDisponivel;
  const padrao: LoteVelocidade | null = configuracoes
    ? padraoEconomicoIndisponivel
      ? "urgente"
      : configuracoes.velocidade_padrao
    : null;
  const velocidade: LoteVelocidade | null =
    escolhida === "economico" && !economicoDisponivel ? null : (escolhida ?? padrao);

  return {
    velocidade,
    escolhida,
    escolher: setEscolhida,
    economicoDisponivel,
    economicoBloqueadoMotivo,
    padraoEconomicoIndisponivel,
  };
}
