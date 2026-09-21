/**
 * Contract-shaped fixtures for Agent Studio tests (CONTRACT §C, §D1, §D2).
 * Typed against `../types` so a drift between the fixtures and the TS mirror
 * fails the type-check, and the compiled fixture is assembled with the §C
 * output layout (blocks joined by `\n\n`, offsets measured on the result) so
 * the manifest offsets are real, not hand-typed guesses.
 *
 * §H5: no person/company names — generic placeholders only.
 */
import type {
  AgentDetail,
  AgentSummary,
  Client,
  ClientSummary,
  CompiledOut,
  ManifestSection,
  StoredPrompt,
  VersionDetail,
  VersionDiff,
} from "../types";

export const AGENT_ID = "0b6f0000-0000-4000-8000-000000000001";
export const V1_ID = "0b6f0000-0000-4000-8000-0000000000a1";
export const V2_ID = "0b6f0000-0000-4000-8000-0000000000a2";
export const SEC_ID = "0b6f0000-0000-4000-8000-0000000000c1";
export const SEC2_ID = "0b6f0000-0000-4000-8000-0000000000c2";
export const SKILL_ID = "0b6f0000-0000-4000-8000-0000000000d1";
export const FILE_ID = "0b6f0000-0000-4000-8000-0000000000e1";
export const CLIENT_ID = "0b6f0000-0000-4000-8000-0000000000f1";
export const ENTRY_ID = "0b6f0000-0000-4000-8000-0000000000f2";

export const AGENT_SUMMARY: AgentSummary = {
  id: AGENT_ID,
  key: "estrategista",
  nome: "Estrategista",
  descricao: "Agente de estratégia de conteúdo.",
  definition_mode: "studio",
  ativo: true,
  publicacao_limiar: 0.8,
  versao_ativa: 1,
  tem_rascunho: true,
};

export const LEGACY_SUMMARY: AgentSummary = {
  id: "0b6f0000-0000-4000-8000-000000000002",
  key: "julia",
  nome: "Julia",
  descricao: null,
  definition_mode: "legacy",
  ativo: true,
  publicacao_limiar: 0.8,
  versao_ativa: null,
  tem_rascunho: false,
};

export const AGENT_DETAIL: AgentDetail = {
  ...AGENT_SUMMARY,
  versoes: [
    {
      id: V2_ID,
      versao: 2,
      status: "rascunho",
      notas: "Ajustes de tom",
      model: "claude-opus-5",
      created_at: "2026-09-20T10:00:00Z",
      published_at: null,
      compiled_hash: "sha256:" + "b".repeat(64),
      eval_score: null,
    },
    {
      id: V1_ID,
      versao: 1,
      status: "ativa",
      notas: "Primeira versão",
      model: "claude-opus-5",
      created_at: "2026-09-10T10:00:00Z",
      published_at: "2026-09-11T10:00:00Z",
      compiled_hash: "sha256:" + "a".repeat(64),
      eval_score: 0.9,
    },
  ],
};

export const DRAFT_DETAIL: VersionDetail = {
  ...AGENT_DETAIL.versoes[0],
  effort: "high",
  max_turns: 40,
  idioma: "pt-BR",
  tool_policy: { web_search: true, knowledge: true },
  based_on_version_id: V1_ID,
  published_by: null,
  publish_override_reason: null,
  eval_run_id: null,
  secoes: [
    { id: SEC_ID, chave: "identidade", titulo: "Identidade", ordem: 10, conteudo: "Você é uma estrategista de conteúdo.", ativo: true },
    { id: SEC2_ID, chave: "metodo", titulo: "Método", ordem: 20, conteudo: "Pesquise antes de propor.", ativo: true },
  ],
  skills: [
    {
      id: SKILL_ID,
      nome: "roteiro-reels",
      descricao: "Escreve roteiros de vídeos curtos.",
      corpo: "Passo 1: gancho.",
      ordem: 10,
      ativo: true,
      arquivos: [{ id: FILE_ID, caminho: "references/arquiteturas.md", titulo: "Arquiteturas", chars: 1200 }],
    },
  ],
};

// ── Compiled output, assembled with the §C layout ─────────────────────────────

interface Block {
  chave: string;
  titulo: string;
  origem: ManifestSection["origem"];
  body: string;
}

const BLOCKS: Block[] = [
  { chave: "identidade", titulo: "Identidade", origem: { tipo: "secao", id: SEC_ID, campo: null }, body: "Você é uma estrategista de conteúdo." },
  { chave: "metodo", titulo: "Método", origem: { tipo: "secao", id: SEC2_ID, campo: null }, body: "Pesquise antes de propor." },
  {
    chave: "skills",
    titulo: "Skills",
    origem: { tipo: "auto", id: null, campo: "skills" },
    body:
      "Skills são procedimentos especializados. Quando o pedido corresponder à descrição de uma skill,\n" +
      "chame `abrir_skill` com o nome dela ANTES de responder e siga as instruções que ela devolver.\n" +
      "Arquivos de referência de uma skill são lidos com `ler_arquivo_skill`.\n\n" +
      "- `roteiro-reels` — Escreve roteiros de vídeos curtos.",
  },
  {
    chave: "ferramentas",
    titulo: "Ferramentas",
    origem: { tipo: "auto", id: null, campo: "tool_policy" },
    body: "- Busca na web: ligada\n- Base de conhecimento: ligada\n- Skills: 1",
  },
];

export function assembleCompiled(blocks: Block[]): { texto: string; manifest: ManifestSection[] } {
  let texto = "";
  const manifest: ManifestSection[] = [];
  blocks.forEach((b, i) => {
    if (i > 0) texto += "\n\n";
    const inicio = texto.length;
    texto += `# ${b.titulo}\n\n${b.body}`;
    const fim = texto.length;
    manifest.push({
      chave: b.chave,
      titulo: b.titulo,
      origem: b.origem,
      inicio,
      fim,
      chars: fim - inicio,
      tokens: Math.ceil((fim - inicio) / 4),
    });
  });
  return { texto, manifest };
}

const ASSEMBLED = assembleCompiled(BLOCKS);

export const COMPILED_DRAFT: CompiledOut = {
  texto: ASSEMBLED.texto,
  hash: "sha256:" + "b".repeat(64),
  tokens_estimados: Math.ceil(ASSEMBLED.texto.length / 4),
  manifest: ASSEMBLED.manifest,
  sob_demanda: [
    { tipo: "skill", nome: "roteiro-reels", caminho: null, chars: 16, tokens: 4, gatilho: "abrir_skill" },
    {
      tipo: "arquivo_skill",
      nome: "roteiro-reels",
      caminho: "references/arquiteturas.md",
      chars: 1200,
      tokens: 300,
      gatilho: "ler_arquivo_skill",
    },
  ],
  avisos: [{ codigo: "titulo_duplica_auto", mensagem: "Uma seção repete um título automático.", bloqueante: false }],
  version_id: V2_ID,
  client_id: null,
};

export const COMPILED_WITH_CLIENT: CompiledOut = (() => {
  const a = assembleCompiled([
    ...BLOCKS,
    {
      chave: "cliente",
      titulo: "Cliente em foco: Cliente Exemplo",
      origem: { tipo: "auto", id: null, campo: "cliente" },
      body: "Marca de exemplo.\n\n## Marca\n- **Voz** — próxima",
    },
  ]);
  return {
    ...COMPILED_DRAFT,
    texto: a.texto,
    manifest: a.manifest,
    tokens_estimados: Math.ceil(a.texto.length / 4),
    hash: "sha256:" + "c".repeat(64),
    client_id: CLIENT_ID,
  };
})();

export const STORED_PROMPT: StoredPrompt = {
  hash: COMPILED_DRAFT.hash,
  texto: COMPILED_DRAFT.texto,
  manifest: COMPILED_DRAFT.manifest,
  version_id: V2_ID,
  client_id: null,
  created_at: "2026-09-20T12:00:00Z",
};

export const DIFF_V1_V2: VersionDiff = {
  a: { version_id: V1_ID, hash: "sha256:" + "a".repeat(64) },
  b: { version_id: V2_ID, hash: COMPILED_DRAFT.hash },
  texto_a: "# Identidade\n\nVocê é uma estrategista.\n\n# Método\n\nPesquise antes de propor.",
  texto_b: COMPILED_DRAFT.texto,
  secoes: [
    { chave: "identidade", estado: "alterada" },
    { chave: "metodo", estado: "igual" },
  ],
  skills: [{ nome: "roteiro-reels", estado: "nova" }],
  configuracoes: [{ campo: "effort", a: "medium", b: "high" }],
};

export const CLIENT_SUMMARY: ClientSummary = {
  id: CLIENT_ID,
  slug: "cliente-exemplo",
  nome: "Cliente Exemplo",
  resumo: "Marca de exemplo.",
  ativo: true,
  total_entradas: 1,
};

export const CLIENT: Client = {
  id: CLIENT_ID,
  slug: "cliente-exemplo",
  nome: "Cliente Exemplo",
  resumo: "Marca de exemplo.",
  ativo: true,
  entradas: [
    { id: ENTRY_ID, tipo: "marca", titulo: "Voz", conteudo: "próxima", status: "ativo", created_at: "2026-09-15T00:00:00Z" },
  ],
};
