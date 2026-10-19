/**
 * Maya scorecard metrics — labels, formats and the pt-BR definitions shown in
 * tooltips (maya-blocks CONTRACT §3.2 rubric `sdr.v1` + the human-block
 * handoff metrics of §3.2's last paragraph).
 *
 * Missing data: a metric that is `null` (e.g. a ratio with denominator 0, a
 * percentile with no episodes, `handoffs_humanos_por_motivo` before S2) or
 * absent from `metricas` renders "sem dados" — NEVER 0 (contract §3.1).
 */
import type { ValorMetrica } from "@/hooks/useSupervisao";

export type FormatoMetrica = "contagem" | "fracao" | "segundos" | "mapa" | "horas";

export interface DefinicaoMetrica {
  rotulo: string;
  formato: FormatoMetrica;
  definicao: string;
  /** For a ratio: the stored numerator/denominator keys shown beside it. */
  razao?: { numerador: string; denominador: string };
}

export const SEM_DADOS = "sem dados";

export const DEFINICOES: Record<string, DefinicaoMetrica> = {
  leads_entrada: {
    rotulo: "Leads de entrada",
    formato: "contagem",
    definicao: "Contatos novos que chegaram à Julia no dia.",
  },
  tpr_n: {
    rotulo: "Conversas respondidas",
    formato: "contagem",
    definicao: "Conversas iniciadas no dia que já receberam a primeira resposta (da Julia ou de alguém da equipe).",
  },
  tpr_p50_s: {
    rotulo: "Tempo de 1ª resposta (mediana)",
    formato: "segundos",
    definicao: "Metade das conversas respondidas recebeu a primeira resposta em até este tempo.",
  },
  tpr_p90_s: {
    rotulo: "Tempo de 1ª resposta (p90)",
    formato: "segundos",
    definicao: "90% das conversas respondidas recebeu a primeira resposta em até este tempo.",
  },
  tpr_sem_resposta: {
    rotulo: "Conversas sem resposta",
    formato: "contagem",
    definicao: "Conversas iniciadas no dia que ainda não tinham nenhuma resposta quando o scorecard foi calculado.",
  },
  qualificados: {
    rotulo: "Qualificados",
    formato: "contagem",
    definicao: "Contatos distintos entregues à equipe como qualificado, visita ou captação no dia.",
  },
  qualificacao_taxa: {
    rotulo: "Taxa de qualificação",
    formato: "fracao",
    definicao: "Qualificados ÷ leads de entrada do dia.",
    razao: { numerador: "qualificados", denominador: "leads_entrada" },
  },
  frios: {
    rotulo: "Frios",
    formato: "contagem",
    definicao: "Contatos distintos entregues como lead frio no dia.",
  },
  frio_taxa: {
    rotulo: "Taxa de frios",
    formato: "fracao",
    definicao: "Frios ÷ leads de entrada do dia.",
    razao: { numerador: "frios", denominador: "leads_entrada" },
  },
  invalidos: {
    rotulo: "Inválidos",
    formato: "contagem",
    definicao: "Contatos distintos marcados como inválidos no dia.",
  },
  invalido_taxa: {
    rotulo: "Taxa de inválidos",
    formato: "fracao",
    definicao: "Inválidos ÷ leads de entrada do dia.",
    razao: { numerador: "invalidos", denominador: "leads_entrada" },
  },
  entregas_manuais: {
    rotulo: "Entregas manuais",
    formato: "contagem",
    definicao: "Leads enviados à equipe manualmente por uma pessoa — não contam a favor da Julia.",
  },
  envios_bloqueados: {
    rotulo: "Envios bloqueados",
    formato: "contagem",
    definicao: "Mensagens que a trava de envio impediu no dia (ex.: fora da janela de atendimento).",
  },
  envios_bloqueados_por_motivo: {
    rotulo: "Envios bloqueados por motivo",
    formato: "mapa",
    definicao: "Os envios bloqueados do dia agrupados pelo motivo do bloqueio.",
  },
  handoffs_humanos: {
    rotulo: "Passagens para humano",
    formato: "contagem",
    definicao: "Vezes em que a Julia passou a conversa para uma pessoa da equipe no dia.",
  },
  handoffs_humanos_por_motivo: {
    rotulo: "Passagens para humano por motivo",
    formato: "mapa",
    definicao: "As passagens para humano agrupadas por motivo (pedido do lead, fora do escopo, reclamação, outro).",
  },
  handoffs_emitidos: {
    rotulo: "Handoffs emitidos",
    formato: "contagem",
    definicao: "Leads que a Julia passou para o próximo bloco no dia.",
  },
  handoffs_nao_assumidos: {
    rotulo: "Handoffs não assumidos",
    formato: "contagem",
    definicao: "Handoffs do dia que ninguém assumiu dentro do prazo (expirados, ou ainda pendentes além do prazo).",
  },
  horas_para_assumir: {
    rotulo: "Prazo para assumir",
    formato: "horas",
    definicao: "O prazo usado neste cálculo para considerar um handoff não assumido.",
  },
  handoffs_recebidos: {
    rotulo: "Handoffs recebidos",
    formato: "contagem",
    definicao: "Leads que chegaram a este bloco vindos do bloco anterior no dia.",
  },
  handoffs_assumidos: {
    rotulo: "Handoffs assumidos",
    formato: "contagem",
    definicao: "Handoffs recebidos no dia que alguém do bloco assumiu (moveu o card ou registrou uma nota).",
  },
  assumir_p50_s: {
    rotulo: "Tempo para assumir (mediana)",
    formato: "segundos",
    definicao: "Metade dos handoffs assumidos foi assumida em até este tempo.",
  },
  assumir_p90_s: {
    rotulo: "Tempo para assumir (p90)",
    formato: "segundos",
    definicao: "90% dos handoffs assumidos foi assumida em até este tempo.",
  },
};

/** Display order per rubric family (`sdr.v1`, or any human block `<bloco>.v1`). */
const ORDEM_SDR = [
  "leads_entrada", "qualificados", "qualificacao_taxa", "frios", "frio_taxa", "invalidos",
  "invalido_taxa", "tpr_n", "tpr_p50_s", "tpr_p90_s", "tpr_sem_resposta", "entregas_manuais",
  "envios_bloqueados", "envios_bloqueados_por_motivo", "handoffs_humanos",
  "handoffs_humanos_por_motivo", "handoffs_emitidos", "handoffs_nao_assumidos", "horas_para_assumir",
];
const ORDEM_HUMANO = [
  "handoffs_recebidos", "handoffs_assumidos", "assumir_p50_s", "assumir_p90_s",
  "handoffs_nao_assumidos", "horas_para_assumir",
];

/** The keys to show for a scorecard: the rubric's expected keys (so a missing
 * one shows "sem dados") followed by any extra key the server sent. */
export function chavesDaRubrica(rubrica: string, metricas: Record<string, ValorMetrica>): string[] {
  const base = rubrica.startsWith("sdr.") ? ORDEM_SDR : ORDEM_HUMANO;
  const extras = Object.keys(metricas).filter((k) => !base.includes(k));
  return [...base, ...extras];
}

const nf = new Intl.NumberFormat("pt-BR");

function duracao(s: number): string {
  if (s < 60) return `${Math.round(s)} s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} h`;
}

/** The display value of one metric — `SEM_DADOS` for null/absent/ill-typed. */
export function formatarMetrica(chave: string, valor: ValorMetrica | undefined): string {
  if (valor === null || valor === undefined) return SEM_DADOS;
  const formato = DEFINICOES[chave]?.formato ?? (typeof valor === "number" ? "contagem" : "mapa");
  if (formato === "mapa") {
    if (typeof valor !== "object") return SEM_DADOS;
    const itens = Object.entries(valor);
    return itens.length ? itens.map(([k, n]) => `${k.replace(/_/g, " ")}: ${nf.format(n)}`).join(" · ") : "nenhum";
  }
  if (typeof valor !== "number" || !Number.isFinite(valor)) return SEM_DADOS;
  switch (formato) {
    case "fracao":
      return `${(valor * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
    case "segundos":
      return duracao(valor);
    case "horas":
      return `${nf.format(valor)} h`;
    default:
      return nf.format(valor);
  }
}

/** "9 de 31" beside a ratio, when both stored counts are present. */
export function detalheRazao(chave: string, metricas: Record<string, ValorMetrica>): string | null {
  const r = DEFINICOES[chave]?.razao;
  if (!r) return null;
  const n = metricas[r.numerador];
  const d = metricas[r.denominador];
  return typeof n === "number" && typeof d === "number" ? `${nf.format(n)} de ${nf.format(d)}` : null;
}
