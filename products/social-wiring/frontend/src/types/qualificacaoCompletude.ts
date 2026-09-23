/**
 * Contract automation F3 — qualificação civil completeness (migration 110).
 *
 * `GET /api/clientes/{id}/qualificacao-completude`
 * (`documento_checklist_service.completude_contratual`). A STRICTER,
 * SEPARATE question from the Documentos-tab checklist (`DocumentoChecklist`
 * in `cardHub.ts`): that one asks "has something plausible been collected",
 * this one asks "is this party ready to be NAMED on a signed Promessa de
 * Venda e Compra" — the legal name, nacionalidade, profissão, estado civil
 * (with regime de bens and a qualified cônjuge when married), CPF and RG
 * (with issuing body), and a complete endereço.
 */

/**
 * The closed snake_case vocabulary the extractor and this endpoint share
 * (`noctusai_lib.integrations.documents.civil_status.ESTADO_CIVIL_VALORES`).
 * `null` means the record's `estado_civil` is empty OR holds a value neither
 * this vocabulary nor the server's legacy-spelling table recognises — treated
 * as "not stated", never guessed at.
 */
export type EstadoCivil =
  | "solteiro"
  | "casado"
  | "divorciado"
  | "separado_judicialmente"
  | "viuvo"
  | "uniao_estavel";

/** pt-BR display label for each canonical `estado_civil` token. */
export const ESTADO_CIVIL_LABELS: Record<EstadoCivil, string> = {
  solteiro: "Solteiro(a)",
  casado: "Casado(a)",
  divorciado: "Divorciado(a)",
  separado_judicialmente: "Separado(a) judicialmente",
  viuvo: "Viúvo(a)",
  uniao_estavel: "União estável",
};

/** The regime-de-bens vocabulary the extractor shares with this endpoint
 *  (`REGIME_BENS_VALORES`) — used only to LABEL a suggested value; the
 *  completude response itself never echoes `regime_bens`, only whether it is
 *  missing (`faltando` includes `"regime_bens"`). */
export const REGIME_BENS_LABELS: Record<string, string> = {
  comunhao_parcial: "Comunhão parcial de bens",
  comunhao_universal: "Comunhão universal de bens",
  separacao_total: "Separação total de bens",
  separacao_obrigatoria: "Separação obrigatória de bens",
  participacao_final_aquestos: "Participação final nos aquestos",
};

/** pt-BR label for the display of an already-known `estado_civil`, falling
 *  back to the raw token so an unrecognised (legacy-spelling) value is still
 *  visible rather than blank. */
export function rotuloEstadoCivil(valor: string | null | undefined): string {
  if (!valor) return "Não informado";
  return ESTADO_CIVIL_LABELS[valor as EstadoCivil] ?? valor;
}

/** pt-BR label for a suggested `regime_bens` value, same fallback shape. */
export function rotuloRegimeBens(valor: string | null | undefined): string {
  if (!valor) return "Não informado";
  return REGIME_BENS_LABELS[valor] ?? valor;
}

/**
 * `clientes.estado_civil` values that name a MARRIED state under CC art.
 * 1.647 — the same closed pair the backend gates a spouse's outorga on
 * (`documento_checklist_service._ESTADOS_QUE_EXIGEM_CONJUGE`).
 *
 * Two spellings per state, not a generic legacy-parsing table: this column
 * only ever arrives here in one of two shapes — the canonical snake_case
 * token an extraction CONFIRMATION writes (`"casado"`), or the pt-BR string
 * `DadosPessoaisForm`'s own `<Select>` writes (`"Casado(a)"`). The server's
 * `_ESTADO_CIVIL_LEGADO` table normalises a much wider set of historical
 * spellings on READ; duplicating that whole table client-side would be a
 * second copy of a rule this file does not own — these two forms are the
 * only ones any write path in THIS product ever produces.
 */
const ESTADOS_QUE_EXIGEM_CONJUGE: ReadonlySet<string> = new Set([
  "casado",
  "uniao_estavel",
  "Casado(a)",
  "União estável",
]);

/**
 * Does this `estado_civil` value put a spouse's consent on the table (CC
 * art. 1.647)? Gates every marriage-only block on a party's panel: the
 * "Casado(a)" toggle, the cônjuge qualification, the certidão-de-casamento
 * slot, and the `regime_bens` field/suggestion. `uniao_estavel` is included
 * — it needs a regime and a cônjuge exactly like `casado` does — but see
 * `estadoCivilExigeDataCasamento` below for the ONE thing it does NOT need.
 */
export function estadoCivilExigeConjuge(valor: string | null | undefined): boolean {
  return !!valor && ESTADOS_QUE_EXIGEM_CONJUGE.has(valor);
}

/**
 * Narrower than `estadoCivilExigeConjuge` — mirrors
 * `documento_checklist_service._ESTADO_QUE_EXIGE_DATA_CASAMENTO`. A
 * `uniao_estavel` party has no "casamento" to date, so `data_casamento` is
 * asked only of a LEGALLY married one.
 */
export function estadoCivilExigeDataCasamento(valor: string | null | undefined): boolean {
  return valor === "casado" || valor === "Casado(a)";
}

/**
 * Display form of a `nacionalidade` value (migration 146) — a suggested
 * value arrives lower-case (the extractor's canonical gentílico, e.g.
 * "brasileiro"); this only capitalises it for display, same fallback shape
 * as `rotuloEstadoCivil`/`rotuloRegimeBens`. Free text a human typed
 * (`"Brasileiro(a)"`) is not re-mapped — capitalising an already-cased
 * string is a no-op on its first letter.
 */
export function rotuloNacionalidade(valor: string | null | undefined): string {
  if (!valor) return "Não informado";
  return valor.charAt(0).toUpperCase() + valor.slice(1);
}

/**
 * Every key `completude_contratual`'s `faltando` can name — the ONE party's
 * own fields (`_CAMPOS_QUALIFICACAO_CONTRATO` + `"endereco"` +
 * `"regime_bens"`), plus the two PAIR-level facts (`"conjuge"` — no linked
 * cônjuge at all; `"conjuge_qualificacao"` — a linked cônjuge who is not
 * themselves qualified).
 */
export const FALTANDO_LABELS: Record<string, string> = {
  nome_oficial: "Nome oficial (do documento)",
  nacionalidade: "Nacionalidade",
  profissao: "Profissão",
  estado_civil: "Estado civil",
  rg: "RG",
  rg_orgao_expedidor: "Órgão expedidor do RG",
  cpf: "CPF",
  endereco: "Endereço completo",
  regime_bens: "Regime de bens",
  conjuge: "Cônjuge vinculado",
  conjuge_qualificacao: "Qualificação do cônjuge",
};

/** pt-BR label for one `faltando` entry, falling back to the raw key. */
export function rotuloFaltando(chave: string): string {
  return FALTANDO_LABELS[chave] ?? chave;
}

/** The linked spouse's own qualification, embedded only when `estado_civil`
 *  names a married state (CC art. 1.647). `null` = not married, or married
 *  with no cônjuge linked yet (that absence is `faltando: ["conjuge"]` on the
 *  PARENT object instead). */
export interface ConjugeCompletude {
  cliente_id: string;
  /** `null` when the spouse's own record has no usable name yet. */
  nome: string | null;
  completo: boolean;
  faltando: string[];
}

/** `GET /api/clientes/{id}/qualificacao-completude` — one party's contract
 *  readiness. Recurses exactly one level into a linked cônjuge; never two. */
export interface QualificacaoCompletude {
  cliente_id: string;
  estado_civil: EstadoCivil | null;
  completo: boolean;
  faltando: string[];
  conjuge: ConjugeCompletude | null;
}

/**
 * Does this RG collapse onto this CPF once punctuation is dropped?
 *
 * Client-side mirror of `noctusai_lib.integrations.documents.rg.is_same_as_cpf`
 * — an INFORMATIONAL flag shown while typing. The coincidence is EXPECTED and
 * correct for the Carteira de Identidade Nacional (CIN), which prints the CPF
 * number as the RG — the server does not refuse the write for it (see
 * `DadosPessoaisForm`'s amber notice, not an error). Same normalisation: the
 * RG's own comparison form keeps digits AND letters (a check-digit RG like
 * "52.179.965-X"), a CPF's only punctuation is dots and a dash so stripping
 * to digits reduces it the same way.
 */
/**
 * Is this identity a CIN (Carteira de Identidade Nacional)? Its RG IS the CPF
 * by design (órgão "IIGDR", contract 08: "RG 448.864.938-66-IIGDR-SP"), so an
 * RG equal to the CPF must never be flagged for one (owner directive,
 * 2026-09-23). True when a CIN file is on record, or the órgão reads IIGDR —
 * the same two signals the server's `identidade_extracao_service._e_cin`
 * reads.
 */
export function ehCin(
  orgaoExpedidor: string | null | undefined,
  temArquivoCin = false,
): boolean {
  return temArquivoCin || (orgaoExpedidor ?? "").toUpperCase().includes("IIGDR");
}

/** Does this person's checklist hold a CIN file (the identity item's `cin`
 *  slot)? Read off the checklist response the card already has — never a
 *  second fetch. */
export function temArquivoCin(
  itens: { documentos?: { tipo_documento: string; documento: unknown }[] }[] | undefined,
): boolean {
  return (itens ?? []).some((item) =>
    (item.documentos ?? []).some((s) => s.tipo_documento === "cin" && !!s.documento),
  );
}

export function rgIgualAoCpf(
  rg: string | null | undefined,
  cpf: string | null | undefined,
): boolean {
  const rgNormalizado = (rg ?? "").toUpperCase().replace(/[^0-9A-Z]/g, "");
  const cpfNormalizado = (cpf ?? "").replace(/\D/g, "");
  if (!rgNormalizado || !cpfNormalizado) return false;
  return rgNormalizado === cpfNormalizado;
}
