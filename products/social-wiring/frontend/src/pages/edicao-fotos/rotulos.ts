/**
 * pt-BR labels for the Edição de Fotos fixed vocabularies. The VALUES are the
 * backend's literals (`noctusai_lib.domain.photo_editing.types.EditType` /
 * `Room`, mirrored by the SQL CHECKs in migrations 123/124); the server's
 * `GET /referencias` `opcoes` is the source of which values exist — these maps
 * only translate them, and fall back to the raw value for an unknown one.
 */
export const TIPO_EDICAO_ROTULOS: Record<string, string> = {
  cor_luz: "Cor e luz",
  ceu: "Substituição de céu",
  declutter: "Declutter",
  staging_virtual: "Virtual staging",
};

export const COMODO_ROTULOS: Record<string, string> = {
  sala: "Sala",
  quarto: "Quarto",
  cozinha: "Cozinha",
  banheiro: "Banheiro",
  area_externa: "Área externa",
  fachada: "Fachada",
  varanda: "Varanda",
  escritorio: "Escritório",
  outro: "Outro",
};

export function rotuloTipoEdicao(value: string): string {
  return TIPO_EDICAO_ROTULOS[value] ?? value;
}

export function rotuloComodo(value: string): string {
  return COMODO_ROTULOS[value] ?? value;
}

/** Ordered `{value,label}` list of every edit type (org settings form). */
export const TIPOS_EDICAO = Object.entries(TIPO_EDICAO_ROTULOS).map(([value, label]) => ({
  value,
  label,
}));
