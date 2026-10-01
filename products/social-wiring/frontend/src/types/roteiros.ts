import type { Roteiro, RoteiroCreateBody } from "@/types/cardHub";

/** CONTRACT §5.1 — a roteiro now carries `data_visita` (`null` on legacy rows).
 *  Optional so a plain `Roteiro` (the frozen `cardHub` type) stays assignable. */
export type RoteiroComData = Roteiro & { data_visita?: string | null };

/** CONTRACT §5.1 `RoteiroCreateBodyV2` — `data_visita` is REQUIRED, DATE only. */
export interface RoteiroCriarBody extends RoteiroCreateBody {
  /** `YYYY-MM-DD`, no time. */
  data_visita: string;
}
