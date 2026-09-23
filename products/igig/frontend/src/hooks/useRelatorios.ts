/**
 * Relatórios comercial / financeiro (wave-2 contract, Slice E1). Backend
 * mirror: `app/routers/relatorio_router.py` → `app/services/relatorios.py`.
 *
 *   GET /api/relatorios/{tipo}?inicio=&fim=&formato=json|pdf|csv
 *
 * `json` is the on-screen preview (a query — same period ⇒ cache hit);
 * `pdf` / `csv` are downloads (a mutation — the file is saved, not cached),
 * fetched with the session token through `api.download`, never a bare
 * `window.open` (the route is authenticated).
 *
 * The service serialises dataclasses, so its `@property` fields
 * (`EtapaFunil.taxa_conversao`, `ClienteFinanceiro.margem`) are NOT on the
 * wire — `taxaConversao` / `margemCliente` below recompute them with the
 * SAME formulas as the service.
 */
import { useMutation, useQuery } from "@tanstack/react-query";

import { api, unwrapData } from "@/lib/api";
import { salvarBlob } from "@/lib/download";

export type TipoRelatorio = "comercial" | "financeiro";
export type FormatoArquivo = "pdf" | "csv";

export interface PeriodoRelatorio {
  inicio: string;
  fim: string;
}

export interface EtapaFunil {
  etapa_id: string;
  etapa_label: string;
  entradas: number;
  saidas: number;
}

export interface MotivoPerda {
  motivo: string;
  etapa_label: string;
  quantidade: number;
  valor_total: number;
}

export interface RelatorioComercial {
  periodo: PeriodoRelatorio;
  funil: EtapaFunil[];
  negocios_ganhos: number;
  negocios_ganhos_valor: number;
  negocios_perdidos: number;
  negocios_perdidos_valor: number;
  motivos_perda: MotivoPerda[];
  dwell_time_medio_dias: number;
  orcamentos_enviados: number;
  orcamentos_aceitos: number;
  orcamentos_recusados: number;
  ticket_medio: number;
  alertas: string[];
}

export interface ClienteFinanceiroRel {
  cliente_id: string;
  cliente_nome: string;
  faturamento: number;
  recebido: number;
  a_receber: number;
  custo: number;
}

export interface RelatorioFinanceiro {
  periodo: PeriodoRelatorio;
  faturamento: number;
  recebido: number;
  a_receber: number;
  inadimplencia_valor: number;
  inadimplencia_qtd: number;
  clientes: ClienteFinanceiroRel[];
  alertas: string[];
}

export interface Relatorio {
  tipo: TipoRelatorio;
  periodo: PeriodoRelatorio;
  comercial: RelatorioComercial | null;
  financeiro: RelatorioFinanceiro | null;
}

/** `EtapaFunil.taxa_conversao` — saídas/entradas in %, 0 when nothing entered. */
export function taxaConversao(e: EtapaFunil): number {
  return e.entradas ? Math.round((e.saidas / e.entradas) * 1000) / 10 : 0;
}

/** `ClienteFinanceiro.margem` / `margem_percentual`. */
export function margemCliente(c: ClienteFinanceiroRel): { margem: number; percentual: number } {
  const margem = Math.round((c.faturamento - c.custo) * 100) / 100;
  const percentual = c.faturamento ? Math.round((margem / c.faturamento) * 1000) / 10 : 0;
  return { margem, percentual };
}

export interface RelatorioFiltro {
  tipo: TipoRelatorio;
  inicio: string;
  fim: string;
}

function valido(f: RelatorioFiltro | null): f is RelatorioFiltro {
  return !!f && /^\d{4}-\d{2}-\d{2}$/.test(f.inicio) && /^\d{4}-\d{2}-\d{2}$/.test(f.fim) && f.inicio <= f.fim;
}

export function useRelatorioPreview(filtro: RelatorioFiltro | null) {
  const query = useQuery({
    queryKey: ["igig", "relatorios", filtro],
    queryFn: () =>
      api
        .get(`/api/relatorios/${(filtro as RelatorioFiltro).tipo}`, {
          inicio: (filtro as RelatorioFiltro).inicio,
          fim: (filtro as RelatorioFiltro).fim,
          formato: "json",
        })
        .then(unwrapData<Relatorio>),
    enabled: valido(filtro),
    placeholderData: (prev) => prev,
  });
  const data = query.data;
  return {
    ...query,
    relatorio: data ?? null,
    showSkeleton: valido(filtro) && query.isPending && !data,
    isRefreshing: query.isFetching && !!data,
  };
}

export function useBaixarRelatorio() {
  return useMutation({
    mutationFn: async ({ tipo, inicio, fim, formato }: RelatorioFiltro & { formato: FormatoArquivo }) => {
      const qs = new URLSearchParams({ inicio, fim, formato }).toString();
      const blob = await api.download(`/api/relatorios/${tipo}?${qs}`);
      salvarBlob(blob, `relatorio-${tipo}-${inicio}-${fim}.${formato}`);
      return { formato };
    },
  });
}
