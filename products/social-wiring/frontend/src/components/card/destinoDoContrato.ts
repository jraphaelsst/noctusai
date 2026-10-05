/**
 * Where "Resolver" lands for a contract readiness line — the control, not
 * just the screen.
 *
 * The backend names the screen (`destino.tela/rota/ancora`) and, for a few
 * lines, the control (`destino.alvo`, `derivacao.ALVO_*`). Two gaps remain on
 * its side, and both are closed HERE, additively, so the human who is
 * working the card by hand can reach every control the generator reads:
 *
 *  1. Most `faltando` lines carry no `alvo`. {@link destinoEfetivo} adds the
 *     DOM id of the control that answers the `campo` (ids this product's own
 *     screens render). A backend-supplied `alvo` always wins.
 *  2. A `matricula.*` falta is routed to the `/matriculas` LIST, but the
 *     controls that answer it live elsewhere: the contract's act selection
 *     on the card's Contratos tab, the título/endereço/ônus confirmations on
 *     the imóvel page. Re-pointed only while the destino still names the
 *     list and no `alvo` — the day the backend emits the right destino this
 *     stops firing.
 *  3. `bloqueios[]` carry NO `destino` at all (`derivacao.Avaliacao.bloqueia`
 *     takes only code + message), so a blocker such as
 *     `FGTS_NAO_MARCADO_NO_FINANCIAMENTO` named a problem and no place to fix
 *     it. {@link destinoDoBloqueio} maps the code families that are fixed on
 *     the card (card-scoped, so no ids are needed). A `destino` the backend
 *     does send always wins.
 *
 * NOC-REMEDIATE[contrato-bloqueio-destino]: move (2) and (3) into
 * `contrato_gerador/derivacao.py` (`DESTINOS` + `bloqueia(..., onde)`), where
 * the codes are born, then delete the tables below. — 2026-10-05
 */
import type { GeracaoDestino } from "./GeradorContratoSection";

/** campo (exact, or `^` regex) -> the DOM id of its control, per card subpage. */
const ALVO_POR_CAMPO: ReadonlyArray<readonly [RegExp, string]> = [
  [/^negociacao\.valor_negociado$/, "valor-negociado"],
  [/^negociacao\.(parcelas$|parcela_sinal$|parcela\.)/, "negest-parcelas"],
  [/^negociacao\.confissao_juros_am$/, "termos-confissao-juros"],
  [/^negociacao\.posse_prazo_dias$/, "termos-posse-prazo"],
  [/^negociacao\.posse_marco$/, "termos-posse-marco"],
  [/^negociacao\.permuta_posse_prazo_dias$/, "termos-permuta-prazo"],
  [/^negociacao\.permuta_posse_marco$/, "termos-permuta-marco"],
  [/^negociacao\.onus_quitacao$/, "termos-onus-quitacao"],
  [/^negociacao\.onus_prazo_dias$/, "termos-onus-prazo"],
  [/^negociacao\.onus_baixa_protocolo_em$/, "termos-onus-baixa-protocolo"],
  [/^financiamento(\.situacao)?$/, "financiamento-situacao"],
];

/** `matricula.*` / `imovel.*` campo -> the imóvel-page section that answers it. */
const ALVO_IMOVEL_POR_CAMPO: Readonly<Record<string, string>> = {
  "matricula.titulo_aquisitivo": "imovel-titulo-aquisitivo",
  "matricula.titulo_aquisitivo_texto": "imovel-titulo-aquisitivo",
  "matricula.onus_credor": "imovel-onus-credor",
  "imovel.endereco_registro_texto": "imovel-endereco-registro",
};

/** The Contratos tab control that holds the contract's act selection. */
export const ALVO_ATOS_DO_CONTRATO = "contrato-matricula-atos";

/**
 * The Certidões tab's subtabs (one per `grupo` of `GET …/certidoes/partes`).
 * The backend names the subtab through `destino.alvo = "certidoes-subtab-<grupo>"`
 * (antigos-proprietarios-CONTRACT §6); each subtab trigger renders that SAME
 * string as its DOM id, so the existing `rolarAteAlvo` poll finds it and its
 * `focus()` activates the tab (Radix "automatic" activation) — no second
 * navigation mechanism.
 */
export const GRUPOS_CERTIDOES = ["comprador", "vendedor", "antigo_proprietario"] as const;
export type GrupoCertidoes = (typeof GRUPOS_CERTIDOES)[number];
const PREFIXO_SUBTAB_CERTIDOES = "certidoes-subtab-";

export const alvoSubtabCertidoes = (grupo: GrupoCertidoes): string => `${PREFIXO_SUBTAB_CERTIDOES}${grupo}`;

/** The subtab a destino alvo names, or `null` when it names none. */
export function grupoDoAlvoCertidoes(alvo: string | null | undefined): GrupoCertidoes | null {
  if (!alvo || !alvo.startsWith(PREFIXO_SUBTAB_CERTIDOES)) return null;
  const grupo = alvo.slice(PREFIXO_SUBTAB_CERTIDOES.length);
  return (GRUPOS_CERTIDOES as readonly string[]).includes(grupo) ? (grupo as GrupoCertidoes) : null;
}

export function destinoEfetivo(destino: GeracaoDestino, campo: string): GeracaoDestino {
  if (destino.alvo) return destino;

  // (2) a matrícula falta still pointing at the /matriculas list.
  if (destino.tela === "matriculas") {
    if (campo === "matricula.atos") {
      return { ...destino, tela: "card_contratos", rota: "/clientes", ancora: "contratos", alvo: ALVO_ATOS_DO_CONTRATO };
    }
    const alvoImovel = ALVO_IMOVEL_POR_CAMPO[campo];
    const codigo = destino.ids.imovel_codigo;
    if (alvoImovel && codigo) {
      return { ...destino, tela: "imovel", rota: `/imoveis/${encodeURIComponent(codigo)}`, ancora: null, alvo: alvoImovel };
    }
    return destino;
  }

  // The imóvel's own endereço confirmation sits on the imóvel page already.
  if (destino.tela === "imovel") {
    const alvoImovel = ALVO_IMOVEL_POR_CAMPO[campo];
    return alvoImovel ? { ...destino, alvo: alvoImovel } : destino;
  }

  // (1) a card-scoped destino with no control named.
  if (destino.tela.startsWith("card_")) {
    const achado = ALVO_POR_CAMPO.find(([re]) => re.test(campo));
    if (achado) return { ...destino, alvo: achado[1] };
  }
  return destino;
}

interface BloqueioRegra {
  re: RegExp;
  ancora: "negociacao" | "financiamento";
  alvo: string | null;
}

/** Order matters: the first match wins (FGTS-not-marked before the FGTS family). */
const BLOQUEIO_REGRAS: readonly BloqueioRegra[] = [
  { re: /^FGTS_NAO_MARCADO_NO_FINANCIAMENTO$/, ancora: "financiamento", alvo: "fgts-financiamento" },
  { re: /^FINANCIAMENTO_/, ancora: "financiamento", alvo: "financiamento-situacao" },
  { re: /^POSSE_MARCO_/, ancora: "negociacao", alvo: "termos-posse-marco" },
  { re: /^ONUS_BAIXA_PROTOCOLO/, ancora: "negociacao", alvo: "termos-onus-baixa-protocolo" },
  { re: /^(ONUS_QUITACAO_|SALDO_SEM_ONUS)/, ancora: "negociacao", alvo: "termos-onus-quitacao" },
  {
    re: /^(VALOR_FGTS_|FGTS_|MAIS_DE_UMA_PARCELA_FGTS|PARCELA_FGTS_|SOMA_PARCELAS_|SINAIS_|SINAL_|MAIS_DE_UM_SINAL|VENCIMENTOS_|CONFISSAO_|DIVISAO_|FAVORECIDO_|EVENTO_CITA_|PERMUTA_IMOVEL_SEM_PARCELA|PERMUTA_IMOVEL_EM_DUAS)/,
    ancora: "negociacao",
    alvo: "negest-parcelas",
  },
  { re: /^(CORRETAGEM_|INTERMEDIARIO_)/, ancora: "negociacao", alvo: null },
];

/** A card-scoped destino for a blocker code, or `null` when no card control
 *  answers it (the blocker keeps rendering as plain text, as before). */
export function destinoDoBloqueio(codigo: string): GeracaoDestino | null {
  const regra = BLOQUEIO_REGRAS.find((r) => r.re.test(codigo));
  if (!regra) return null;
  return {
    tela: `card_${regra.ancora}`,
    rota: "/clientes",
    ancora: regra.ancora,
    alvo: regra.alvo,
    ids: {},
  };
}
