/** pt-BR words for the "Headlines e Roteiros" page (estruturas-contract §6.9, §11.3). */
import { ESTRUTURA_ROTULO } from "@/components/geracao/labels";
import type { RoteiroEstrutura } from "@/types/geracao";
import type { HeadlineRoteiroItem } from "@/types/estruturas";

export type RoteiroDoItem = NonNullable<HeadlineRoteiroItem["roteiro"]>;

export const ROTULO_APROVACAO: Record<"pendente" | "aprovado" | "rejeitado", string> = {
  pendente: "Aguardando aprovação",
  aprovado: "Aprovado",
  rejeitado: "Rejeitado",
};

export const FILTRO_STATUS: { valor: string; rotulo: string }[] = [
  { valor: "", rotulo: "Todos os status" },
  { valor: "criando", rotulo: "Criando" },
  { valor: "processando", rotulo: "Processando" },
  { valor: "completo", rotulo: "Completo" },
  { valor: "falha", rotulo: "Falha" },
  { valor: "sem_roteiro", rotulo: "Sem roteiro" },
];

export function rotuloDuracao(d: RoteiroDoItem["duracao"]): string {
  return d === "auto" ? "Duração automática" : `${d} min`;
}

export function rotuloOrdemCta(o: RoteiroEstrutura): string {
  return ESTRUTURA_ROTULO[o] ?? o;
}

/** The text a row leads with: the saved headline, else the free `headline_texto` of a roteiro without headline. */
export function textoDoItem(i: HeadlineRoteiroItem): string {
  return i.headline?.texto ?? i.headline_texto;
}

/** Stable React key (HR-1): one item per roteiro plus one per headline without a roteiro — a headline with 2 roteiros appears twice. */
export function chaveDoItem(i: HeadlineRoteiroItem): string {
  return i.roteiro?.id ?? i.headline?.id ?? i.created_at;
}
