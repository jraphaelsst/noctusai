import type { JuliaNotificacao } from "@/hooks/useJuliaNotificacoes";

export interface GrupoDia { chave: string; rotulo: string; itens: JuliaNotificacao[] }

const diaChave = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Groups the feed by local day, newest first: Hoje / Ontem / dd/mm/aaaa. */
export function agruparPorDia(itens: JuliaNotificacao[], agora: Date = new Date()): GrupoDia[] {
  const hoje = diaChave(agora);
  const ontem = diaChave(new Date(agora.getFullYear(), agora.getMonth(), agora.getDate() - 1));
  const mapa = new Map<string, GrupoDia>();
  for (const n of itens) {
    const d = new Date(n.created_at);
    const chave = diaChave(d);
    let g = mapa.get(chave);
    if (!g) {
      g = { chave, rotulo: chave === hoje ? "Hoje" : chave === ontem ? "Ontem" : d.toLocaleDateString("pt-BR"), itens: [] };
      mapa.set(chave, g);
    }
    g.itens.push(n);
  }
  return [...mapa.values()].sort((a, b) => (a.chave < b.chave ? 1 : -1));
}
