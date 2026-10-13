/**
 * `<input type="datetime-local">` → the ISO the Esteira's TIMESTAMPTZ columns (`cs_posts.data_inicio`
 * / `data_entrega`) accept: the seed's `dataHoraLocalParaIsoSP` plus São Paulo's explicit offset.
 *
 * The offset is REQUIRED: the esteira schemas refuse a naive or bare-date value (422), because the
 * server would otherwise read it as UTC midnight — "27/10" became 26/10 on the card (prod 2026-10-13).
 * The seed's own lembretes do not need it (their backend reads a naive `dispara_em` as SP wall-clock).
 * Brazil has carried no DST since 2019, so São Paulo is a fixed `-03:00`.
 */
import { dataHoraLocalParaIsoSP } from "@noctusai/lib/components";

export const OFFSET_SAO_PAULO = "-03:00";

export function dataHoraLocalParaIsoComOffsetSP(valor: string): string {
  return `${dataHoraLocalParaIsoSP(valor)}${OFFSET_SAO_PAULO}`;
}
