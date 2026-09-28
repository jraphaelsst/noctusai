/**
 * Ninho Vazio display vocabulary — labels for the enum values the API
 * returns (grupoterapia level, member status, subscription/payment state).
 *
 * Tier NAMES and PRICES are never here: they come from the API
 * (`/api/planos/publicos`, `/api/portal/minha-conta`) because they are
 * editable data (CONTRACT.md §Tiers — "data, not code").
 */
import type { NivelGrupoterapia } from "@/hooks/useEu";
import type { Ciclo } from "@/hooks/usePlanos";
import { formatBRLFromCents } from "@/lib/money";

/** What each grupoterapia level includes, in the member's own words. */
export const NIVEL_DESCRICAO: Record<NivelGrupoterapia, string> = {
  nenhum: "Plataforma e conteúdos, sem grupoterapia",
  ouvir: "Assiste às grupoterapias",
  falar: "Assiste às grupoterapias e tem vez de fala",
};

export const MEMBRO_STATUS_LABEL: Record<string, string> = {
  pendente: "Aguardando confirmação",
  ativo: "Ativa",
  atrasado: "Pagamento em atraso",
  pausado: "Pausada",
  cancelado: "Encerrada",
};

export const ASSINATURA_ESTADO_LABEL: Record<string, string> = {
  iniciada: "Aguardando o primeiro pagamento",
  ativa: "Ativa",
  inadimplente: "Pagamento em atraso",
  carencia: "Pagamento pendente",
  expirada: "Encerrada",
  cancelada: "Cancelada",
  pausada: "Pausada",
};

export const PAGAMENTO_ESTADO_LABEL: Record<string, string> = {
  pendente: "Em aberto",
  pago: "Pago",
  falhou: "Não aprovado",
  estornado: "Estornado",
};

export function labelDe(map: Record<string, string>, value: string | null | undefined): string {
  if (!value) return "—";
  return map[value] ?? value;
}

/** `R$ 7,00 por mês` / `Gratuito` — the price line under a tier name. */
export function precoPorCiclo(precoCentavos: number, ciclo: Ciclo): string {
  if (precoCentavos === 0) return "Gratuito";
  return `${formatBRLFromCents(precoCentavos)} por ${ciclo === "anual" ? "ano" : "mês"}`;
}
