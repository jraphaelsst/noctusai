/**
 * Proveniência — per-contract data lineage: for every field the "Gerar
 * contrato" readiness check cares about, WHERE the value came from (which
 * document, which upload channel, when) and what state it is in (still
 * empty, machine-read but unconfirmed, confirmed, typed by hand, or
 * conflicting between two sources).
 *
 * `sw-extraction-contract` — FROZEN API, built in a parallel worktree; this
 * slice mocks the endpoint in tests rather than wait on it (contract-first).
 * `GET /api/clientes/{cliente_id}/contratos/{contrato_id}/proveniencia`.
 *
 * Same S3/container split as `useContratoGeracao`: this hook is the only
 * thing that talks to the network; `ProvenienciaPanel` (`components/card/`)
 * stays presentational.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types ──────────────────────────────────────────────────────────────────

/**
 * Where a document-bearing value entered the platform. `manual` and
 * `derivado` can appear on a NULL `documento` too (nothing was uploaded —
 * a person typed the value, or it was computed from other fields), but the
 * contract lists them alongside the document-bearing entradas because a
 * hand-attached file can also carry one of them.
 */
export type ProvenienciaEntrada =
  | "lead_form"
  | "cliente_card_upload"
  | "parte_painel_upload"
  | "imovel_page_upload"
  | "matriculas"
  | "vista_mirror"
  | "certidao_robo"
  | "manual"
  | "derivado";

/** pt-BR labels for every `entrada` value — the one place this mapping is
 *  written, reused by `ProvenienciaPanel` and (once it needs it) any other
 *  surface that reads a `documento.entrada`. Falls back to the raw value for
 *  an entrada this list doesn't know about yet, never a blank string. */
export const ENTRADA_LABEL: Record<ProvenienciaEntrada, string> = {
  lead_form: "Formulário de lead",
  cliente_card_upload: "Upload no card do cliente",
  parte_painel_upload: "Upload no painel da parte",
  imovel_page_upload: "Upload na página do imóvel",
  matriculas: "Extrator de matrículas",
  vista_mirror: "Espelho do Vista",
  certidao_robo: "Robô de certidões",
  manual: "Digitado manualmente",
  derivado: "Calculado a partir de outros dados",
};

export function rotuloDaEntrada(entrada: string | null | undefined): string {
  if (!entrada) return "—";
  return ENTRADA_LABEL[entrada as ProvenienciaEntrada] ?? entrada;
}

/**
 * Where "abrir" a confirmed source document sends the operator — an FE-side
 * heuristic, NOT part of the frozen contract (the contract gives no
 * `destino` on `documento` itself, only on `fontes_possiveis` for the
 * `vazio` case). Fed through `cardSubpages.resolverDestino`, same as any
 * other plain-string destino: a route (`lead_form`/`imovel_page_upload`/
 * `matriculas`/`certidao_robo`) or a `CardSubpageKey` (`cliente_card_upload`/
 * `parte_painel_upload` both landed on `"geral"` when the standalone
 * `documentos` subpage was retired — `cardSubpages.ts`'s header note).
 * `vista_mirror`/`manual`/`derivado` have no place a person visits, so they
 * resolve to no link — the label alone (tipo + nome + entrada) still shows.
 */
const ENTRADA_DESTINO: Partial<Record<ProvenienciaEntrada, string>> = {
  lead_form: "/leads",
  cliente_card_upload: "geral",
  parte_painel_upload: "geral",
  imovel_page_upload: "/imoveis",
  matriculas: "/matriculas",
  certidao_robo: "/certidoes",
};

export function destinoDoDocumento(entrada: string | null | undefined): string | null {
  if (!entrada) return null;
  return ENTRADA_DESTINO[entrada as ProvenienciaEntrada] ?? null;
}

/**
 * A field's lineage state. `maquina_pendente` mirrors the same "extraído,
 * ainda não confirmado" state `ExtracaoSugestao`/`useValidacaoExtracao` model
 * elsewhere on the card — proveniência is a READ-ONLY report of it here, not
 * a second write path.
 */
export type ProvenienciaEstado =
  | "vazio"
  | "maquina_pendente"
  | "confirmado"
  | "manual"
  | "conflito";

export const ESTADO_LABEL: Record<ProvenienciaEstado, string> = {
  vazio: "Vazio",
  maquina_pendente: "Extraído (pendente)",
  confirmado: "Confirmado",
  manual: "Manual",
  conflito: "Conflito",
};

export interface ProvenienciaDocumento {
  id: string;
  tipo: string;
  nome: string | null;
  entrada: ProvenienciaEntrada | string;
}

/**
 * A place the field COULD be filled from, offered only while `estado` is
 * `"vazio"`. `destino` is a plain string, not the richer `GeracaoDestino`
 * object `GeracaoFaltando.destino` carries (`GeradorContratoSection.tsx`) —
 * either a real SPA route (`"/matriculas"`) or a card subpage key
 * (`cardSubpages.CardSubpageKey`, e.g. `"contratos"`). `null` = no known
 * place to send the operator yet.
 */
export interface ProvenienciaFontePossivel {
  tipo_documento: string | null;
  rotulo: string;
  entradas: string[];
  destino: string | null;
}

export interface ProvenienciaItem {
  entidade: string;
  campo: string;
  rotulo: string;
  valor: unknown;
  estado: ProvenienciaEstado;
  origem: string | null;
  documento: ProvenienciaDocumento | null;
  em: string | null;
  fontes_possiveis: ProvenienciaFontePossivel[];
}

export interface ProvenienciaResponse {
  items: ProvenienciaItem[];
}

// ─── Query ──────────────────────────────────────────────────────────────────

const KEY = (clienteId: string, contratoId: string) =>
  ["sw", "clientes", clienteId, "contratos", contratoId, "proveniencia"] as const;

/**
 * 🔴 `aberto` IS THE LAZY GATE, same discipline as `useContratoGeracao` — the
 * caller passes whether the "Proveniência" collapsible is open so the fetch
 * only fires once a corretor actually looks.
 */
export function useProveniencia(
  clienteId: string | null,
  contratoId: string | null,
  aberto: boolean,
) {
  return useQuery({
    queryKey: KEY(clienteId ?? "__none__", contratoId ?? "__none__"),
    queryFn: () =>
      api.get<ProvenienciaResponse>(
        `/api/clientes/${encodeURIComponent(clienteId as string)}/contratos/${encodeURIComponent(
          contratoId as string,
        )}/proveniencia`,
      ),
    enabled: aberto && !!clienteId && !!contratoId,
  });
}
