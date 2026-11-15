/**
 * Pure helpers over the `GET /api/guia-documentos` payload — lookups for the
 * "i" popovers, the anchors the page and the popovers share, the certidão
 * requirement sentence, and the "busca por dado" filter. No React here, so
 * the mapping is unit-tested without rendering.
 */
import type {
  GuiaCertidao,
  GuiaCampoIndice,
  GuiaDadoObrigatorio,
  GuiaDocumento,
  GuiaDocumentos,
} from "@/types/guiaDocumentos";

export const GUIA_ROTA = "/guia-documentos";

/** Anchor ids — the contract's deep links (`#documento-<tipo>`,
 *  `#certidao-<tipo>`, `#etapa-<chave>`, `#campo-<campo>`) plus the page's own
 *  `#dado-<chave>` for a mandatory-data row. */
export const ancora = {
  documento: (tipo: string) => `documento-${tipo}`,
  certidao: (tipo: string) => `certidao-${tipo}`,
  etapa: (chave: string) => `etapa-${chave}`,
  campo: (campo: string) => `campo-${campo}`,
  dado: (chave: string) => `dado-${chave}`,
} as const;

/** The page sections, in display order — the in-page index and its anchors. */
export const SECOES_GUIA = [
  { id: "fluxo-do-lead", titulo: "Fluxo do lead" },
  { id: "dados-obrigatorios", titulo: "Dados obrigatórios" },
  { id: "documentos", titulo: "Documentos" },
  { id: "certidoes", titulo: "Certidões" },
  { id: "busca-por-dado", titulo: "Busca por dado" },
] as const;

export const linkGuia = (id: string) => `${GUIA_ROTA}#${id}`;

export function documentoPorTipo(guia: GuiaDocumentos | undefined, tipo: string): GuiaDocumento | undefined {
  return guia?.documentos.find((d) => d.tipo_documento === tipo);
}

export function certidaoPorTipo(guia: GuiaDocumentos | undefined, tipo: string): GuiaCertidao | undefined {
  return guia?.certidoes.find((c) => c.tipo === tipo);
}

export function dadoObrigatorioPorChave(
  guia: GuiaDocumentos | undefined,
  chave: string,
): GuiaDadoObrigatorio | undefined {
  return guia?.dados_obrigatorios.find((d) => d.chave === chave);
}

/** `tipo_documento` → its label; an unknown tipo shows itself rather than
 *  vanishing. */
export function rotuloDocumento(guia: GuiaDocumentos | undefined, tipo: string): string {
  return documentoPorTipo(guia, tipo)?.rotulo ?? tipo;
}

const ROTULO_DOCUMENTO_REQUISITO: Record<string, string> = { cpf: "CPF", cnpj: "CNPJ" };

/**
 * The requirement sentences for a certidão row, in order:
 *   "Precisa de: CPF + data de nascimento"
 *   "Requer login GOV.BR do escritório"
 *   "Emissão manual (sem consulta automática)"
 */
export function requisitosCertidao(c: GuiaCertidao): string[] {
  const linhas: string[] = [];
  for (const r of c.requisitos) {
    const partes = [
      ROTULO_DOCUMENTO_REQUISITO[r.documento] ?? r.documento.toUpperCase(),
      ...r.campos.map((f) => f.rotulo.toLocaleLowerCase("pt-BR")),
    ];
    linhas.push(`Precisa de: ${partes.join(" + ")}`);
  }
  if (c.credencial === "govbr") linhas.push("Requer login GOV.BR do escritório");
  if (c.fonte === "manual") linhas.push("Emissão manual (sem consulta automática)");
  return linhas;
}

export const ROTULO_FONTE_CERTIDAO: Record<GuiaCertidao["fonte"], string> = {
  infosimples: "Automática (InfoSimples)",
  manual: "Manual",
};

/** Accent- and case-insensitive form for matching pt-BR text. */
export function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLocaleLowerCase("pt-BR")
    .trim();
}

/**
 * "Busca por dado": the reverse-index entries whose label (or key) contains
 * every word typed — "data nascimento" finds "Data de nascimento". An empty
 * term returns the full index.
 */
export function buscarCampos(guia: GuiaDocumentos | undefined, termo: string): GuiaCampoIndice[] {
  const campos = guia?.campos ?? [];
  const palavras = normalizar(termo).split(/\s+/).filter(Boolean);
  if (palavras.length === 0) return campos;
  return campos.filter((c) => {
    const alvo = `${normalizar(c.rotulo)} ${normalizar(c.campo.replace(/_/g, " "))}`;
    return palavras.every((p) => alvo.includes(p));
  });
}
