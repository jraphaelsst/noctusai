/**
 * SYNTHETIC fixtures for the Julia v2 Studio tab tests — shapes follow the routers
 * (`studio_conteudo_router.py`, `qualificacao_router.py`, `channel_threads_router.py`,
 * `skills_biblioteca_router.py`); every string is a neutral placeholder, never real prompt, rule or
 * tool content (CONTRACT §0.4). Lives under `__tests__` so no production path can import it.
 */
import type {
  CanalConversa,
  Controle,
  PadraoVersao,
  TextoRow,
} from "@/api/studio/types-julia";
import type { AgentDetail, VersionSummary } from "@/api/studio/types";

export const KEY = "agente-x";
export const DRAFT_ID = "00000000-0000-4000-8000-0000000000d1";
export const ACTIVE_ID = "00000000-0000-4000-8000-0000000000a1";

const version = (over: Partial<VersionSummary>): VersionSummary => ({
  id: ACTIVE_ID,
  versao: 1,
  status: "ativa",
  notas: null,
  model: "claude-opus-5",
  created_at: "2026-10-01T10:00:00Z",
  published_at: "2026-10-01T10:00:00Z",
  compiled_hash: "sha256:aaaaaaaaaaaaaaaa",
  eval_score: null,
  ...over,
} as VersionSummary);

export function agentDetail(over: Partial<AgentDetail> = {}, draft = true): AgentDetail {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    key: KEY,
    nome: "Agente X",
    descricao: null,
    definition_mode: "studio",
    ativo: true,
    publicacao_limiar: 0.8,
    versao_ativa: 1,
    tem_rascunho: draft,
    kind: "runtime",
    definition_scope: "plataforma",
    conteudo_modo: "linhas",
    versoes: [
      ...(draft ? [version({ id: DRAFT_ID, versao: 2, status: "rascunho", published_at: null })] : []),
      version({}),
    ],
    ...over,
  };
}

export const TEXTOS: TextoRow[] = [
  { id: "t1", chave: "grupo.um", conteudo: "texto sintético um" },
  { id: "t2", chave: "grupo.dois", conteudo: "" },
  { id: "t3", chave: "outro.tres", conteudo: "texto sintético três" },
];

export const CONTROLE: Controle = {
  agent_key: KEY,
  modo: "ligado",
  aceita_novos_leads: true,
  dreno_inatividade_dias: 7,
  threads_abertas: 4,
  drenagem: { abertas: 4, ociosas: 1, efetivas: 3, concluida: false, idade_max_dias: 9, idades_dias: [9, 2, 1, 0] },
};

export const CONVERSA: CanalConversa = {
  id: "00000000-0000-4000-8000-0000000000c1",
  agent_key: KEY,
  titulo: null,
  status: "ativa",
  last_message_at: "2026-10-10T10:00:00Z",
  created_at: "2026-10-10T09:00:00Z",
  channel: "whatsapp",
  contact: { nome: "Contato Sintético" },
  resultado: { estagio: "estagio_a", score: 42, violacoes: 2 },
};

export const PADRAO_VERSAO: PadraoVersao = {
  id: "00000000-0000-4000-8000-0000000000f1",
  padrao: "padrao-x",
  versao: 3,
  status: "rascunho",
  notas: null,
  publicada_em: null,
  criterios: [
    {
      chave: "crit_a", grupo: "prontidao", rotulo: "Critério A", descricao_modelo: "descrição sintética", tipo: "enum",
      opcoes: [{ valor: "op1", rotulo: "Opção 1", descricao_modelo: "", sinonimos: ["sin1"] }],
      unidade: null, sensivel: null, pontuacao: { op1: 10 }, ordem: 1, ativo: true, eixo: "eixo_1", escopo: "sdr", validade_dias: null,
    },
    {
      chave: "crit_b", grupo: "contato", rotulo: "Critério B", descricao_modelo: "", tipo: "texto",
      opcoes: [], unidade: null, sensivel: null, pontuacao: {}, ordem: 2, ativo: true, eixo: null, escopo: "financeiro", validade_dias: null,
    },
  ],
  estagios: [
    { chave: "est_a", rotulo: "Estágio A", descricao: "", ordem: 1, regra: { tipo: "sempre" }, conclusivo: false, terminal: false },
  ],
  parametros: {
    minimo_para_ofertar: { tipo: "sempre" },
    lote_ofertas: 3,
    score_max: 100,
    eixos: {},
    pedir_identificacao_quando: null,
  },
};
