/**
 * pt-BR vocabulary + pure helpers for the Estruturas library UI (contract §2, §3.1, §11.3).
 * Pure on purpose: the list, the detail, the editor and the tests all read the same words.
 */
import type {
  Bloco,
  EstruturaDetalhe,
  EstruturaFormato,
  EstruturaObjetivo,
  EstruturaStatus,
  OrigemCampo,
} from "@/types/estruturas";

export const FORMATOS: readonly EstruturaFormato[] = ["reels", "carrossel", "stories", "post"];
export const OBJETIVOS: readonly EstruturaObjetivo[] = ["alcance", "autoridade", "conexao", "venda"];
export const STATUS_ADMIN: readonly EstruturaStatus[] = ["ativa", "rascunho", "arquivada"];

export const ROTULO_FORMATO: Record<EstruturaFormato, string> = {
  reels: "Reels",
  carrossel: "Carrossel",
  stories: "Stories",
  post: "Post",
};

export const ROTULO_OBJETIVO: Record<EstruturaObjetivo, string> = {
  alcance: "Alcance",
  autoridade: "Autoridade",
  conexao: "Conexão",
  venda: "Venda",
};

export const ROTULO_STATUS: Record<EstruturaStatus, string> = {
  ativa: "Ativa",
  rascunho: "Rascunho",
  arquivada: "Arquivada",
};

/** The only two provenance values that mean "somebody still has to look at this" (DC2). */
export const ORIGENS_PENDENTES: readonly OrigemCampo[] = ["referencia", "ia_sugerido"];

export const ROTULO_PROVENIENCIA: Record<"referencia" | "ia_sugerido", string> = {
  referencia: "Preenchido por referência",
  ia_sugerido: "Sugerido pela IA",
};

export const ehPendente = (o: OrigemCampo | undefined): o is "referencia" | "ia_sugerido" =>
  o === "referencia" || o === "ia_sugerido";

/** Field grammar of `POST /estruturas/{id}/confirmar` (contract §3.1 `cs_estrutura_eventos.campo`). */
export const campoBloco = (blocoId: string, campo: "nome" | "tipo" | "tempo" | "instrucao") =>
  `bloco.${blocoId}.${campo}`;

export const ROTULO_CAMPO_BLOCO: Record<"nome" | "tipo" | "tempo" | "instrucao", string> = {
  nome: "nome",
  tipo: "tipo",
  tempo: "tempo",
  instrucao: "instrução",
};

/** Every field of a detail still awaiting an admin's confirmation, in the confirm grammar. */
export function camposPendentes(d: EstruturaDetalhe): string[] {
  const out: string[] = [];
  const p = d.proveniencia;
  if (p) {
    if (ehPendente(p.formula_headline)) out.push("formula_headline");
    if (ehPendente(p.formato)) out.push("formato");
    if (ehPendente(p.objetivos)) out.push("objetivos");
  }
  for (const b of d.blocos) {
    const bp = b.proveniencia;
    if (!bp) continue;
    (["nome", "tipo", "tempo", "instrucao"] as const).forEach((c) => {
      if (ehPendente(bp[c])) out.push(campoBloco(b.id, c));
    });
  }
  return out;
}

/** The `[placeholders]` of a formula, so the UI can show what an org's brain will fill in. */
export function placeholdersDaFormula(formula: string): string[] {
  return [...formula.matchAll(/\[([^\]]+)\]/g)].map((m) => m[1] ?? "").filter(Boolean);
}

/** "estrutura #123" — the human id used in chat citations and deep links. */
export const rotuloCodigo = (codigo: number) => `#${codigo}`;

export type BlocoRascunho = {
  /** Stable React/dnd key: the server id for a saved block, `novo-N` for a new one. */
  chave: string;
  /** Server id; absent for a block added in this draft. */
  id?: string;
  nome: string;
  tipo_id: string;
  tempo: string;
  instrucao: string;
  nota: string;
  repeticoes: number;
};

export type EstruturaRascunho = {
  formula_headline: string;
  formato: EstruturaFormato | "";
  objetivos: EstruturaObjetivo[];
  blocos: BlocoRascunho[];
};

export const blocoParaRascunho = (b: Bloco): BlocoRascunho => ({
  chave: b.id,
  id: b.id,
  nome: b.nome,
  tipo_id: b.tipo.id,
  tempo: b.tempo ?? "",
  instrucao: b.instrucao ?? "",
  nota: b.nota ?? "",
  repeticoes: b.repeticoes,
});

/** The persisted value in the draft's own shape — what `useUnsavedChanges` compares against. */
export const detalheParaRascunho = (d: EstruturaDetalhe): EstruturaRascunho => ({
  formula_headline: d.formula_headline,
  formato: d.formato ?? "",
  objetivos: [...d.objetivos],
  blocos: d.blocos.map(blocoParaRascunho),
});

/** Body item of `PUT /estruturas/{id}/blocos` (empty text → omitted; position = `ordem`). */
export function blocoParaCorpo(b: BlocoRascunho) {
  return {
    ...(b.id ? { id: b.id } : {}),
    nome: b.nome.trim(),
    tipo_id: b.tipo_id,
    ...(b.tempo.trim() ? { tempo: b.tempo.trim() } : {}),
    ...(b.instrucao.trim() ? { instrucao: b.instrucao.trim() } : {}),
    ...(b.nota.trim() ? { nota: b.nota.trim() } : {}),
    repeticoes: b.repeticoes,
  };
}

/** Client-side mirror of the server's publish rule (§3.1 `status <> 'ativa' OR …`), for inline hints. */
export function faltandoParaPublicar(d: Pick<EstruturaDetalhe, "formato" | "objetivos" | "blocos">): string[] {
  const f: string[] = [];
  if (!d.formato) f.push("formato");
  if (d.objetivos.length < 1) f.push("objetivos");
  if (d.blocos.length < 1) f.push("blocos");
  return f;
}

export const ROTULO_FALTANDO: Record<string, string> = {
  formato: "o formato",
  objetivos: "ao menos um objetivo",
  blocos: "ao menos um bloco",
};

/** "3–7s ×2" — the line under a block's name. */
export function resumoBloco(b: Pick<Bloco, "tempo" | "repeticoes">): string {
  return [b.tempo, b.repeticoes > 1 ? `×${b.repeticoes}` : null].filter(Boolean).join(" · ");
}

/** Where an Estrutura came from (admin-only detail). */
export const ROTULO_ORIGEM_ESTRUTURA = {
  manual: "Criada manualmente",
  import_corestudio: "Importada (referência CoreStudio)",
  import_maquina: "Importada (Máquina de Roteiros)",
  viral_auto: "Rascunho automático a partir de um vídeo",
} as const;

/** Profile ingestion status (same words as Minha Biblioteca; kept here so the platform pages do not import a page). */
export const ROTULO_PERFIL_STATUS: Record<string, string> = {
  aguardando: "Aguardando",
  ativo: "Ativo",
  pausado: "Pausado",
  nao_encontrado: "Não encontrado",
  sem_conta: "Sem conta",
  sem_credencial: "Sem credencial",
  sem_orcamento: "Sem orçamento",
  erro: "Erro",
};
