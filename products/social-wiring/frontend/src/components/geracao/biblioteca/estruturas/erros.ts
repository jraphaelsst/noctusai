/**
 * Every refusal of the Estruturas / library routes, in pt-BR (contract §5 error catalogue).
 * A refusal is never silent (KB § PATTERNS/frontend/silent-refusal.md): the caller gets a sentence
 * (`mensagemEstruturas`) and, where the server attached data, the data (`dadoDoErro`).
 *
 * Duck-typed on the seed `ApiError` (`code`, `status`, `field()`) so it reads the error whichever
 * module instance built it.
 */
type ErroApi = {
  code?: unknown;
  status?: unknown;
  message?: unknown;
  field?: (k: string) => unknown;
  body?: unknown;
};

const MENSAGENS: Record<string, string> = {
  versao_desatualizada: "Esta estrutura foi alterada por outra pessoa. Recarregue e tente de novo.",
  estrutura_em_uso: "Esta estrutura já foi usada em headlines ou roteiros. Arquive-a em vez de excluir.",
  estrutura_inativa: "Esta estrutura não está ativa.",
  perfil_com_estruturas: "Este perfil tem estruturas. Confirme para apagá-las também.",
  perfil_optout: "Este criador pediu para não ser monitorado.",
  perfil_ja_existe: "Este perfil já está na biblioteca.",
  limite_perfis: "A biblioteca atingiu o limite de perfis.",
  simulacao_obrigatoria: "Rode a simulação deste arquivo antes de aplicar.",
  importacao_em_andamento: "Já existe uma importação em andamento.",
  arquivo_invalido: "O arquivo de importação não tem o formato esperado.",
  link_invalido: "Cole o link de um post do Instagram (instagram.com/p/…, /reel/… ou /tv/…).",
  post_nao_encontrado: "Não encontramos este post (privado ou removido).",
  fonte_nao_suporta_link: "A fonte de ingestão atual não consegue buscar um post avulso.",
  tipo_em_uso: "Este tipo de bloco está em uso. Desative-o em vez de excluir.",
  tipo_protegido: 'O tipo "Outro" é do sistema e não pode ser alterado.',
  rascunho_incompleto: "Para publicar, informe formato, ao menos um objetivo e ao menos um bloco.",
  ingestao_sem_org_plataforma: "A organização de ingestão da biblioteca não está configurada.",
  viral_sem_conteudo: "Este vídeo ainda não tem conteúdo para gerar uma estrutura.",
  ia_nao_configurada: "A IA ainda não está configurada para esta organização.",
  orcamento_ia_excedido: "O orçamento de IA do período acabou. Tente novamente mais tarde.",
  geracao_indisponivel: "A geração está indisponível no momento. Tente novamente em instantes.",
};

/** The server's `code`, wherever the envelope put it (nested, flat or `{detail:{code}}`). */
export function codigoDoErro(e: unknown): string | null {
  if (!e || typeof e !== "object") return null;
  const code = (e as ErroApi).code;
  return typeof code === "string" && code ? code : null;
}

export function statusDoErro(e: unknown): number | null {
  const s = e && typeof e === "object" ? (e as ErroApi).status : null;
  return typeof s === "number" ? s : null;
}

/** An extra field next to the code (`faltando`, `estruturas_total`, `candidatos`…). */
export function dadoDoErro(e: unknown, chave: string): unknown {
  if (!e || typeof e !== "object") return undefined;
  const x = e as ErroApi;
  if (typeof x.field === "function") return x.field(chave);
  const body = x.body as { detail?: unknown } | undefined;
  const det = body && typeof body === "object" ? body.detail : undefined;
  if (det && typeof det === "object" && chave in (det as object)) return (det as Record<string, unknown>)[chave];
  return undefined;
}

export const ehConflitoDeVersao = (e: unknown) => codigoDoErro(e) === "versao_desatualizada";

/** The sentence to show: the catalogue's pt-BR text by code, then the server's own, then `fallback`. */
export function mensagemEstruturas(e: unknown, fallback: string): string {
  const code = codigoDoErro(e);
  if (code && MENSAGENS[code]) return MENSAGENS[code];
  if (statusDoErro(e) === 403) return "Somente administradores da plataforma podem fazer isso.";
  if (statusDoErro(e) === 404) return "Não encontramos este item. Ele pode ter sido removido.";
  const proprio = (e as ErroApi | null)?.message;
  return typeof proprio === "string" && proprio ? proprio : fallback;
}
