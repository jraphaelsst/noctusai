/**
 * The new-agent wizard's pure logic (agents-unified CONTRACT §6). Everything structural comes from the model the
 * server serves (`GET /api/studio/modelo` -> `assistente.passos`): the steps, their order and category, each step's
 * fields, every field's type / required flag / limits / options / default. Nothing here lists the steps or the
 * fields — only pt-BR presentation (labels, hints, option names), keyed by `<modelo>.<chave>` and falling back to
 * the server's `rotulo`, plus the three create-body facts the field model cannot express (named below).
 */
import type { CampoModelo, PassoAssistente } from "@/api/agentes/types";
import type { Briefing } from "@/api/studio/types-geracao";

export type ModoInicio = "vazio" | "gerar";
export type ValorCampo = string | number | boolean;
export type Valores = Record<string, ValorCampo>;
export type ErrosCampos = Record<string, string>;

export const MODOS_INICIO: { id: ModoInicio; titulo: string; descricao: string }[] = [
  { id: "vazio", titulo: "Começar vazio", descricao: "Cria a definição; o conteúdo é escrito na página do agente." },
  { id: "gerar", titulo: "Gerar com IA", descricao: "Um briefing faz a IA escrever o primeiro rascunho do conteúdo." },
];

/** Category ids of `assistente.passos` -> rail headings. Unknown ids fall back to the id itself. */
export const CATEGORIA_TITULO: Record<string, string> = {
  quem: "Quem é",
  o_que: "O que sabe",
  como: "Como atua",
  fechamento: "Fechamento",
};

/** Field groups inside a step (one subtab each when a step mixes them). */
export const GRUPO_TITULO: Record<string, string> = {
  plataforma: "Definição",
  briefing: "Briefing para a IA",
};

interface Apresentacao {
  rotulo: string;
  dica?: string;
  placeholder?: string;
  /** Long free text renders as a textarea. */
  longo?: boolean;
  opcoes?: Record<string, string>;
}

/** pt-BR presentation only. A field missing here still renders, with the server's `rotulo`. */
export const APRESENTACAO: Record<string, Apresentacao> = {
  "plataforma.key": { rotulo: "Chave", dica: "Identificador permanente, usado nas URLs.", placeholder: "ex.: estrategista-conteudo" },
  "plataforma.nome": { rotulo: "Nome", placeholder: "ex.: Estrategista de conteúdo" },
  "plataforma.descricao": { rotulo: "Descrição", dica: "Uma linha sobre o agente, mostrada no card da listagem.", longo: true },
  "briefing.objetivo": { rotulo: "Objetivo", dica: "Para que o agente existe, em poucas frases.", longo: true },
  "briefing.publico": { rotulo: "Público atendido", placeholder: "ex.: corretores e clientes de imobiliárias", longo: true },
  "plataforma.padrao_qualificacao": { rotulo: "Padrão de qualificação", dica: "Chave do padrão de qualificação, se houver.", placeholder: "ex.: bant" },
  "plataforma.escopo_qualificacao": { rotulo: "Escopo de qualificação", dica: "Atributo que delimita a qualificação, se houver.", placeholder: "ex.: imovel" },
  "briefing.tom_de_voz": { rotulo: "Tom de voz", placeholder: "ex.: cordial, direto, sem jargão", longo: true },
  "briefing.idioma": { rotulo: "Idioma", placeholder: "pt-BR" },
  "briefing.exemplos": { rotulo: "Exemplos", dica: "Trechos de conversa ou respostas que mostrem o jeito certo.", longo: true },
  "briefing.canal": {
    rotulo: "Canal principal",
    opcoes: { whatsapp: "WhatsApp", web: "Web", interno: "Interno" },
  },
  "plataforma.runtime": {
    rotulo: "Motor de execução",
    opcoes: { llm: "LLM (padrão)", claude_sdk: "Claude SDK" },
  },
  "plataforma.owner_product": { rotulo: "Produto dono", dica: "Produto da plataforma ao qual o agente pertence, se houver.", placeholder: "ex.: social-wiring" },
  "briefing.limites": { rotulo: "Limites", dica: "O que o agente nunca faz e quando passa para um humano.", longo: true },
  "plataforma.instanciavel": { rotulo: "Disponível para as organizações", dica: "Quando publicado, cada organização recebe uma instância." },
  "plataforma.limite_usd": { rotulo: "Limite de custo da geração (US$)", dica: "Teto do que a geração por IA pode gastar." },
};

/**
 * Create-body facts the field model cannot express:
 * - a NEW key needs a name (`422 nome_obrigatorio`), although `nome` is optional on the schema (idempotent create);
 * - the generation cost cap only means something when a briefing is sent;
 * - `briefing.nome` is not a wizard field: it is the agent's name.
 */
const OBRIGATORIO_NA_CRIACAO = new Set(["plataforma.nome"]);
const SO_COM_BRIEFING = new Set(["plataforma.limite_usd"]);

export const id = (c: CampoModelo): string => `${c.modelo ?? "plataforma"}.${c.chave}`;

export function apresentacao(c: CampoModelo): Apresentacao {
  return APRESENTACAO[id(c)] ?? { rotulo: c.rotulo };
}

export function opcaoRotulo(c: CampoModelo, opcao: string): string {
  return apresentacao(c).opcoes?.[opcao] ?? opcao;
}

export function obrigatorio(c: CampoModelo): boolean {
  return c.obrigatorio || OBRIGATORIO_NA_CRIACAO.has(id(c));
}

/** The fields of a step that apply to the chosen start mode (no briefing in `vazio` mode). */
export function camposVisiveis(passo: PassoAssistente, modo: ModoInicio): CampoModelo[] {
  return passo.campos.filter((c) =>
    modo === "gerar" ? true : c.modelo !== "briefing" && !SO_COM_BRIEFING.has(id(c)),
  );
}

/** The step's visible fields grouped by `modelo`, in first-seen order (two or more groups => subtabs). */
export function gruposDoPasso(passo: PassoAssistente, modo: ModoInicio): { grupo: string; campos: CampoModelo[] }[] {
  const out: { grupo: string; campos: CampoModelo[] }[] = [];
  for (const c of camposVisiveis(passo, modo)) {
    const g = c.modelo ?? "plataforma";
    const atual = out.find((x) => x.grupo === g);
    if (atual) atual.campos.push(c);
    else out.push({ grupo: g, campos: [c] });
  }
  return out;
}

/** Starting values: each field's server default; empty otherwise. */
export function valoresIniciais(passos: PassoAssistente[]): Valores {
  const v: Valores = {};
  for (const p of passos) {
    for (const c of p.campos) {
      if (c.padrao !== null && c.padrao !== undefined) v[id(c)] = c.padrao;
      else if (c.tipo === "booleano") v[id(c)] = false;
      else v[id(c)] = "";
    }
  }
  return v;
}

function vazio(v: ValorCampo | undefined): boolean {
  return v === undefined || (typeof v === "string" && v.trim() === "");
}

/** One field's error message, or null. Reads ONLY the field model (required / length / pattern / range / options). */
export function validarCampo(c: CampoModelo, valor: ValorCampo | undefined): string | null {
  const { rotulo } = apresentacao(c);
  if (vazio(valor)) return obrigatorio(c) ? `${rotulo} é obrigatório.` : null;
  if (c.tipo === "texto") {
    const s = String(valor).trim();
    if (c.min_length && s.length < c.min_length) return `${rotulo}: mínimo de ${c.min_length} caracteres.`;
    if (c.max_length && s.length > c.max_length) return `${rotulo}: máximo de ${c.max_length} caracteres.`;
    if (c.pattern && !new RegExp(c.pattern).test(s)) {
      return `${rotulo}: use letras minúsculas, números e hífens, começando por letra ou número.`;
    }
  }
  if (c.tipo === "numero") {
    const n = typeof valor === "number" ? valor : Number(String(valor).replace(",", "."));
    if (!Number.isFinite(n)) return `${rotulo}: informe um número.`;
    if (c.minimo_exclusivo != null && n <= c.minimo_exclusivo) return `${rotulo}: deve ser maior que ${c.minimo_exclusivo}.`;
    if (c.minimo != null && n < c.minimo) return `${rotulo}: mínimo de ${c.minimo}.`;
    if (c.maximo != null && n > c.maximo) return `${rotulo}: máximo de ${c.maximo}.`;
  }
  if (c.tipo === "escolha" && c.opcoes && !c.opcoes.includes(String(valor))) return `${rotulo}: escolha uma opção.`;
  return null;
}

export interface ContextoValidacao {
  /** Keys the org already has: a create with one of them would silently reuse it (idempotent route). */
  chavesExistentes?: ReadonlySet<string>;
}

export function validarPasso(
  passo: PassoAssistente,
  modo: ModoInicio,
  valores: Valores,
  ctx: ContextoValidacao = {},
): ErrosCampos {
  const erros: ErrosCampos = {};
  for (const c of camposVisiveis(passo, modo)) {
    const e = validarCampo(c, valores[id(c)]);
    if (e) erros[id(c)] = e;
    else if (id(c) === "plataforma.key" && ctx.chavesExistentes?.has(String(valores[id(c)]).trim())) {
      erros[id(c)] = "Já existe um agente com essa chave nesta organização.";
    }
  }
  return erros;
}

/** The first step (by model order) with an error, and its errors — the publish-time full check. */
export function primeiroPassoInvalido(
  passos: PassoAssistente[],
  modo: ModoInicio,
  valores: Valores,
  ctx: ContextoValidacao = {},
): { passo: PassoAssistente; erros: ErrosCampos } | null {
  for (const p of passos) {
    const erros = validarPasso(p, modo, valores, ctx);
    if (Object.keys(erros).length > 0) return { passo: p, erros };
  }
  return null;
}

export interface CorpoCriacao {
  key: string;
  nome?: string;
  descricao?: string;
  runtime?: string;
  owner_product?: string;
  escopo_qualificacao?: string;
  padrao_qualificacao?: string;
  instanciavel?: boolean;
  limite_usd?: number;
  briefing?: Briefing;
}

function normalizar(c: CampoModelo, v: ValorCampo | undefined): ValorCampo | undefined {
  if (vazio(v)) return undefined;
  if (c.tipo === "numero") return typeof v === "number" ? v : Number(String(v).replace(",", "."));
  if (c.tipo === "booleano") return Boolean(v);
  return typeof v === "string" ? v.trim() : v;
}

/**
 * CONTRACT §6 submit body for `POST /api/studio/plataforma/agents`: `plataforma` fields top-level, `briefing`
 * fields under `briefing` (+ `briefing.nome` = the agent's name) — only in `gerar` mode. Empty optional values are
 * omitted (an empty string would break a pattern-checked field).
 */
export function montarCorpo(passos: PassoAssistente[], modo: ModoInicio, valores: Valores): CorpoCriacao {
  const topo: Record<string, ValorCampo> = {};
  const briefing: Record<string, ValorCampo> = {};
  for (const p of passos) {
    for (const c of camposVisiveis(p, modo)) {
      const v = normalizar(c, valores[id(c)]);
      if (v === undefined) continue;
      if (c.modelo === "briefing") briefing[c.chave] = v;
      else topo[c.chave] = v;
    }
  }
  const corpo = { ...topo } as unknown as CorpoCriacao;
  if (modo === "gerar") corpo.briefing = { nome: String(topo.nome ?? ""), ...briefing } as unknown as Briefing;
  return corpo;
}

/** How many visible fields have a value — the "answers" counter of the journey header. */
export function contarRespostas(passos: PassoAssistente[], modo: ModoInicio, valores: Valores): { feitas: number; total: number } {
  let feitas = 0;
  let total = 0;
  for (const p of passos) {
    for (const c of camposVisiveis(p, modo)) {
      if (c.tipo === "booleano") continue;
      total += 1;
      if (!vazio(valores[id(c)])) feitas += 1;
    }
  }
  return { feitas, total };
}

/** The cap the model declares for the generation (the `limite_usd` field's `maximo`). */
export function limiteGeracao(passos: PassoAssistente[]): number | null {
  for (const p of passos) {
    const c = p.campos.find((x) => x.chave === "limite_usd");
    if (c?.maximo != null) return c.maximo;
  }
  return null;
}

// ── local draft (this browser only — never on the server until "Publicar") ──

export const RASCUNHO_STORAGE_KEY = "agents:novo-agente:rascunho:v1";

export interface RascunhoLocal {
  modo: ModoInicio;
  valores: Valores;
  passo: string | null;
  chaveTocada: boolean;
  salvoEm: string;
}

/** Storage can be unavailable (private mode, quota) or hold a stale shape: both mean "no draft", reported. */
export function lerRascunho(): RascunhoLocal | null {
  try {
    const raw = window.localStorage.getItem(RASCUNHO_STORAGE_KEY);
    if (!raw) return null;
    const r = JSON.parse(raw) as Partial<RascunhoLocal>;
    if ((r.modo !== "vazio" && r.modo !== "gerar") || typeof r.valores !== "object" || r.valores === null) return null;
    return {
      modo: r.modo,
      valores: r.valores as Valores,
      passo: typeof r.passo === "string" ? r.passo : null,
      chaveTocada: Boolean(r.chaveTocada),
      salvoEm: typeof r.salvoEm === "string" ? r.salvoEm : new Date().toISOString(),
    };
  } catch (err) {
    console.warn("[novo-agente] rascunho local ilegível; começando do zero", err);
    return null;
  }
}

/** true when written; false when the browser refused (the page then says the draft is not kept). */
export function gravarRascunho(r: RascunhoLocal): boolean {
  try {
    window.localStorage.setItem(RASCUNHO_STORAGE_KEY, JSON.stringify(r));
    return true;
  } catch (err) {
    console.warn("[novo-agente] não foi possível guardar o rascunho local", err);
    return false;
  }
}

export function apagarRascunho(): void {
  try {
    window.localStorage.removeItem(RASCUNHO_STORAGE_KEY);
  } catch (err) {
    console.warn("[novo-agente] não foi possível apagar o rascunho local", err);
  }
}
