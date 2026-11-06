import type { MetricasResumo, MetricasResumoOut, MetricasThreadOut, MetricasTurno, MetricasTurnosOut } from "@/api/studio/types-metricas";

const ORG = "11111111-2222-3333-4444-555555555555";
const THREAD = "aaaaaaaa-0000-0000-0000-000000000001";

export const RESUMO: MetricasResumo = {
  turnos: 40, turnos_erro: 1, handoffs: 2, llm_calls: 45, custo_usd: 0.1824, custo_por_turno_usd: 0.00456,
  tokens_entrada: 80000, tokens_saida: 8000, tokens_cache_leitura: 60000, tokens_cache_escrita: 0, cache_leitura_share: 0.75,
  turno_ms_p50: 2100, turno_ms_p95: 6400, llm_ms_p50: 1700, llm_ms_p95: 4200, tool_ms_p50: null, tool_ms_p95: null,
  inbound_bytes: 2000, reply_bytes: 8000, prompt_bytes: 90000, db_bytes: 10000, armazenamento_bytes: 10000,
};

const CAB = { agent_key: "julia", janela: { desde: "2026-10-30T00:00:00Z", ate: "2026-11-06T00:00:00Z" }, origem: "canal" as const, org_id: null };

export const METRICAS_RESUMO: MetricasResumoOut = {
  ...CAB, truncado: false, resumo: RESUMO,
  serie_diaria: [{ dia: "2026-11-05", ...RESUMO }, { dia: "2026-11-06", ...RESUMO }],
  por_versao: [{ compiled_hash: "abcdef0123456789", ...RESUMO }, { compiled_hash: null, ...RESUMO }],
  por_org: [{ org_id: ORG, ...RESUMO }],
};

export const TURNO_FRIO: MetricasTurno = {
  id: "t-cold", criado_em: "2026-11-06T12:00:00Z", org_id: ORG, agent_key: "julia", version_id: null, compiled_hash: "abc", thread_id: THREAD,
  mensagem_entrada_id: null, mensagem_resposta_id: null, origem: "canal", gatilho: null, status: "ok", erro_classe: null, turno_status: "respondido",
  handoff: false, ferramentas: ["buscar_imovel"],
  llm: { chamadas: 1, tokens_entrada: 22200, tokens_saida: 300, tokens_cache_leitura: 0, tokens_cache_escrita: 20000, cache_leitura_share: 0, custo_usd: 0.028, modelos: ["m"], price_versions: [] },
  velocidade: { turno_ms: 9000, llm_ms: 7000, tool_ms: 400, ferramentas_ms: {}, intake_ms: 1200 },
  tamanho: { inbound_bytes: 30, reply_bytes: 200, prompt_bytes: 90000, db_bytes: 230, media_bytes: null },
};
export const TURNO_QUENTE: MetricasTurno = {
  ...TURNO_FRIO, id: "t-warm", ferramentas: [],
  llm: { ...TURNO_FRIO.llm, tokens_entrada: 23000, tokens_cache_leitura: 22300, tokens_cache_escrita: 0, cache_leitura_share: 0.97, custo_usd: 0.0031 },
  velocidade: { turno_ms: 1900, llm_ms: 1700, tool_ms: 0, ferramentas_ms: {}, intake_ms: null },
  tamanho: { ...TURNO_FRIO.tamanho, inbound_bytes: 70 },
};

export const METRICAS_TURNOS: MetricasTurnosOut = { ...CAB, truncado: false, total: 40, pagina: 1, limite: 25, itens: [TURNO_FRIO, TURNO_QUENTE] };
export const METRICAS_THREAD: MetricasThreadOut = { agent_key: "julia", thread_id: THREAD, origem: "todos", truncado: false, resumo: { ...RESUMO, turnos: 2 }, turnos: [TURNO_FRIO, TURNO_QUENTE] };
export const THREADS = { ...CAB, truncado: false, total: 1, itens: [{ thread_id: THREAD, ...RESUMO }] };
export const IDS = { ORG, THREAD };
