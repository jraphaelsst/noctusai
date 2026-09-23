/**
 * SW's card subpage REGISTRY metadata — which rail entries the lead card has,
 * in what order, with which label and glyph.
 *
 * The rail itself (`CardSidebarNav`) and the dialog chrome moved to the seed
 * card hub (`@noctusai/lib/components` — `project-history/roadmaps/
 * cardhub-igig-crm-2026-09.wave-a-design.md`, Slice F). The seed ships no
 * fixed list: a product declares its subpages. This file is that declaration
 * for social-wiring — `ClienteCardDialog` pairs each entry with its `render`,
 * and `GeradorContratoSection` reads the labels from here so there is never a
 * second hand-written copy of them.
 */
import type { LucideIcon } from "lucide-react";
import {
  CalendarClock,
  ClipboardList,
  FileSignature,
  Handshake,
  Landmark,
  Megaphone,
  Route,
  Store,
  User,
} from "lucide-react";

/** Which subpage the card is showing. `geral` is the default on open. */
export type CardSubpageKey =
  | "geral"
  | "cliente"
  | "vendedor"
  | "agendamentos"
  | "roteiros"
  | "financiamento"
  | "negociacao"
  | "contratos"
  | "campanha";

export interface SubpageDef {
  key: CardSubpageKey;
  label: string;
  icon: LucideIcon;
}

/**
 * Order is the reading order of the card: what you DO with this person, then
 * who they are, then what is booked with them, then how the deal closes, then
 * where they came from.
 *
 * `roteiros` sits IMMEDIATELY under `agendamentos` because that is the funnel
 * order the user named — qualificação leads to a VISIT, and a roteiro is the
 * planned visit. It is also the tab you reach for right after failing to find
 * "Visita" in the Agendar button, which no longer offers it (migration 082).
 *
 * 🔴 `documentos` IS GONE, and its absence is the point. Everything it held —
 * the required-data checklist, each party's panel, the anexos — moved onto
 * Geral, because collecting a document is not a separate errand from working
 * the card: it is the work. A tab for it meant the operator read "RG pendente"
 * on one screen and supplied it on another. `financiamento` inherits the slot
 * it used to sit above, and keeps it: it is another pile of paperwork to
 * collect, just one belonging to the bank rather than to the person.
 */
export const CARD_SUBPAGES: readonly SubpageDef[] = [
  { key: "geral", label: "Geral", icon: ClipboardList },
  { key: "cliente", label: "Dados do cliente", icon: User },
  // Migration 098. Sits DIRECTLY under "Dados do cliente" because it is the
  // same job for the other side of the table — who the counterparty is —
  // rather than a step in the funnel. Reading the rail top-to-bottom now gives
  // both parties to the deal before anything about the deal itself.
  { key: "vendedor", label: "Vendedor", icon: Store },
  { key: "agendamentos", label: "Agendamentos", icon: CalendarClock },
  { key: "roteiros", label: "Roteiros", icon: Route },
  { key: "financiamento", label: "Financiamento/Escritura", icon: Landmark },
  { key: "negociacao", label: "Negociação", icon: Handshake },
  // Sits at the end of the deal group, after Negociação: the contract is the
  // paperwork that CLOSES the deal the two subpages above it decide the
  // terms of — uploaded today, and where an auto-generated one will land
  // later (marked, never a second surface).
  { key: "contratos", label: "Contratos", icon: FileSignature },
  { key: "campanha", label: "Campanha e imóvel", icon: Megaphone },
] as const;

/**
 * What a plain-string `destino` (`fontes_possiveis[].destino`,
 * `GeracaoFaltando.sugestoes[].destino`) resolves to: a real SPA route to
 * link to, or — when it names a `CardSubpageKey` instead — the subpage's
 * pt-BR label for guidance text (there is no URL into a subpage the dialog
 * owns in local state; see `GeradorContratoSection.FaltandoLinha`'s
 * `destino.tela.startsWith("card_")` split, which this generalizes for the
 * narrower plain-string shape). `null`/unrecognized destino → both null, so
 * the caller renders the bare label with no action.
 */
export function resolverDestino(destino: string | null | undefined): {
  rota: string | null;
  subpageLabel: string | null;
} {
  if (!destino) return { rota: null, subpageLabel: null };
  if (destino.startsWith("/")) return { rota: destino, subpageLabel: null };
  const subpage = CARD_SUBPAGES.find((s) => s.key === destino);
  return { rota: null, subpageLabel: subpage?.label ?? null };
}
