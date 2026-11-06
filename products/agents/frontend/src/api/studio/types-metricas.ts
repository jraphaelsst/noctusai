/**
 * Per-turn metrics (cost / speed / size) -- platform-admin ONLY, shown ONLY in the agents app.
 * Contract: projects/julia-v2/CONTRACT.md section 14. Backend: app/routers/studio_metricas_router.py.
 * Money is USD (priced central-ledger events, never re-priced); bytes are UTF-8 payload bytes, not on-disk size.
 */

export type MetricasOrigem = "canal" | "eval" | "todos";

export interface MetricasCabecalho {
  agent_key: string;
  janela: { desde: string; ate: string };
  origem: MetricasOrigem;
  org_id: string | null;
  /** True when the window held more rows than the read cap (aggregates then cover the newest rows only). */
  truncado: boolean;
}

export interface MetricasResumo {
  turnos: number;
  turnos_erro: number;
  handoffs: number;
  llm_calls: number;
  custo_usd: number;
  custo_por_turno_usd: number;
  /** prompt + cache read + cache write */
  tokens_entrada: number;
  tokens_saida: number;
  tokens_cache_leitura: number;
  tokens_cache_escrita: number;
  /** tokens_cache_leitura / tokens_entrada, 0..1 */
  cache_leitura_share: number;
  turno_ms_p50: number | null;
  turno_ms_p95: number | null;
  llm_ms_p50: number | null;
  llm_ms_p95: number | null;
  tool_ms_p50: number | null;
  tool_ms_p95: number | null;
  inbound_bytes: number;
  reply_bytes: number;
  prompt_bytes: number;
  db_bytes: number;
  /** Sum of db_bytes (message payload bytes persisted for the turns). */
  armazenamento_bytes: number;
}

export type MetricasGrupoDia = { dia: string } & MetricasResumo;
export type MetricasGrupoVersao = { compiled_hash: string | null } & MetricasResumo;
export type MetricasGrupoOrg = { org_id: string } & MetricasResumo;
export type MetricasGrupoThread = { thread_id: string } & MetricasResumo;

export interface MetricasResumoOut extends MetricasCabecalho {
  resumo: MetricasResumo;
  serie_diaria: MetricasGrupoDia[];
  por_versao: MetricasGrupoVersao[];
  por_org: MetricasGrupoOrg[];
}

export interface MetricasTurno {
  id: string;
  criado_em: string;
  org_id: string;
  agent_key: string;
  version_id: string | null;
  compiled_hash: string | null;
  thread_id: string | null;
  mensagem_entrada_id: string | null;
  mensagem_resposta_id: string | null;
  origem: "canal" | "eval";
  gatilho: string | null;
  status: "ok" | "erro";
  erro_classe: string | null;
  /** respondido | silencio | handoff | concluido | encerrado (null on an error turn) */
  turno_status: string | null;
  handoff: boolean;
  ferramentas: string[];
  llm: {
    chamadas: number;
    tokens_entrada: number;
    tokens_saida: number;
    tokens_cache_leitura: number;
    tokens_cache_escrita: number;
    cache_leitura_share: number;
    custo_usd: number;
    modelos: string[];
    price_versions: string[];
  };
  velocidade: {
    turno_ms: number;
    llm_ms: number;
    tool_ms: number;
    ferramentas_ms: Record<string, number>;
    /** Oldest inbound of the batch -> turn start; null when not measurable (eval). */
    intake_ms: number | null;
  };
  tamanho: {
    inbound_bytes: number;
    reply_bytes: number;
    prompt_bytes: number;
    db_bytes: number;
    /** null = not measured (the agents app does not persist media). */
    media_bytes: number | null;
  };
}

export interface MetricasTurnosOut extends MetricasCabecalho {
  total: number;
  pagina: number;
  limite: number;
  itens: MetricasTurno[];
}

export interface MetricasThreadsOut extends MetricasCabecalho {
  total: number;
  itens: MetricasGrupoThread[];
}

export interface MetricasThreadOut {
  agent_key: string;
  thread_id: string;
  origem: MetricasOrigem;
  truncado: boolean;
  resumo: MetricasResumo;
  /** Oldest first. */
  turnos: MetricasTurno[];
}
