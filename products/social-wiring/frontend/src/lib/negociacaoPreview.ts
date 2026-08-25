/**
 * Live preview of the commission split, mirroring
 * `card_hub/negociacao_service.py::calcular`.
 *
 * 🔴 WHY A SECOND IMPLEMENTATION EXISTS, AND WHAT KEEPS IT HONEST
 * ----------------------------------------------------------------
 * The split used to appear only AFTER saving: the panel read `calculo` off the
 * server response, so the screen whose entire purpose is "how much goes to
 * whom" stayed blank while the person was deciding. That is the moment the
 * number matters.
 *
 * Two implementations of money arithmetic is a real risk, and the mitigations
 * are deliberate rather than assumed:
 *
 *   1. This is a PREVIEW. The panel labels it as one and shows the SERVER's
 *      figures the moment the draft matches what was saved. The stored value
 *      is never this file's output.
 *   2. `negociacaoPreview.test.ts` pins every case against values produced by
 *      running the Python itself, so a drift fails a test rather than a payout.
 *   3. The algorithm is transcribed, not reinvented — largest-remainder in
 *      integer centavos, same tie-break, same order.
 *
 * Everything is computed in integer centavos. Floating-point reais is exactly
 * the representation error `Decimal` was chosen to avoid on the other side.
 */

export interface PreviewEntrada {
  valor_negociado: string;
  pct_comissao: string;
  tem_parceria: boolean;
  pct_parceria: string;
  pct_agencia: string;
  pct_agentes: string;
  pct_captador: string;
}

export interface PreviewCalculo {
  calculavel: boolean;
  motivo: string | null;
  comissao_total: string | null;
  parceria: string | null;
  nossa_parte: string | null;
  agencia: string | null;
  agentes_total: string | null;
  captador_total: string | null;
}

const NAO_CALCULAVEL: PreviewCalculo = {
  calculavel: false,
  motivo: "informe valor negociado e % de comissão",
  comissao_total: null,
  parceria: null,
  nossa_parte: null,
  agencia: null,
  agentes_total: null,
  captador_total: null,
};

function num(v: string | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const t = String(v).trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** Python's `Decimal` default context rounds half-to-even; so does this. */
function arredondaMeioPar(x: number): number {
  const piso = Math.floor(x);
  const resto = x - piso;
  if (Math.abs(resto - 0.5) < 1e-9) return piso % 2 === 0 ? piso : piso + 1;
  return Math.round(x);
}

/**
 * Split `totalCents` across `pesos` so the parts sum EXACTLY to the total.
 *
 * Largest-remainder: floor each share, then hand the leftover centavos out one
 * at a time, biggest remainder first, index breaking ties. Rounding each share
 * independently instead leaves the total and the sum of its parts disagreeing
 * by a few centavos — the kind of discrepancy someone finds at payout time and
 * cannot reconstruct.
 */
export function ratear(totalCents: number, pesos: number[]): number[] {
  const somaPesos = pesos.reduce((a, b) => a + b, 0);
  if (totalCents <= 0 || somaPesos <= 0) return pesos.map(() => 0);

  const exatos = pesos.map((p) => (totalCents * p) / somaPesos);
  const pisos = exatos.map((e) => Math.floor(e));
  const restante = totalCents - pisos.reduce((a, b) => a + b, 0);

  // Biggest fractional remainder first; lower index wins a tie, matching the
  // Python's `key=(remainder, -i), reverse=True`.
  const ordem = pisos
    .map((_, i) => i)
    .sort((a, b) => {
      const ra = exatos[a] - pisos[a];
      const rb = exatos[b] - pisos[b];
      if (Math.abs(ra - rb) > 1e-9) return rb - ra;
      return a - b;
    });

  for (let k = 0; k < restante; k += 1) {
    pisos[ordem[k % pisos.length]] += 1;
  }
  return pisos;
}

function brl(cents: number): string {
  const sinal = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sinal}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

/** The split as the server would compute it, for preview only. */
export function preverCalculo(entrada: PreviewEntrada): PreviewCalculo {
  const valor = num(entrada.valor_negociado);
  const pctComissao = num(entrada.pct_comissao);

  // Not an error — terms are routinely drafted before a price is agreed.
  // Zeroes here would claim a split had been computed.
  if (pctComissao === null || valor === null || valor <= 0) return NAO_CALCULAVEL;

  const valorCents = arredondaMeioPar(valor * 100);
  const comissaoCents = arredondaMeioPar((valorCents * pctComissao) / 100);

  let parceriaCents = 0;
  let nossaParteCents = comissaoCents;
  if (entrada.tem_parceria) {
    const pctParceria = num(entrada.pct_parceria) ?? 0;
    [parceriaCents, nossaParteCents] = ratear(comissaoCents, [
      pctParceria,
      100 - pctParceria,
    ]);
  }

  const [agenciaCents, agentesCents, captadorCents] = ratear(nossaParteCents, [
    num(entrada.pct_agencia) ?? 0,
    num(entrada.pct_agentes) ?? 0,
    num(entrada.pct_captador) ?? 0,
  ]);

  return {
    calculavel: true,
    motivo: null,
    comissao_total: brl(comissaoCents),
    parceria: brl(parceriaCents),
    nossa_parte: brl(nossaParteCents),
    agencia: brl(agenciaCents),
    agentes_total: brl(agentesCents),
    captador_total: brl(captadorCents),
  };
}
