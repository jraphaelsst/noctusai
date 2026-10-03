/**
 * Aditivos de contrato — amendments to ONE signed contract
 * (`products/social-wiring/projects/contrato-aditivos-CONTRACT.md`, backend
 * migration 190, `card_hub/contrato_aditivo/`).
 *
 * An aditivo carries STRUCTURED amendments (pagamento → a restated parcela
 * schedule, posse, comissão, outro = free text) and goes through the same
 * lifecycle as a generated contract: readiness (`GET …/geracao`) → `POST
 * …/gerar` → a version (PDF + .docx) that ALWAYS awaits the final legal
 * review → admin approval. The version shape IS the contract's
 * (`VersaoOut`), and every readiness / error shape is the contract
 * generator's — so this module reuses `useContratos`' types and its one
 * error translation (`postGeracao`) instead of re-declaring them.
 *
 * Keys nest under the contratos family (`contratosQueryKey`), so any
 * contract-level invalidation (status, new version, review) also refreshes
 * the aditivos it amends.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import {
  contratosQueryKey,
  postGeracao,
  type ContratoActor,
  type ContratoStatus,
  type GeracaoAviso,
  type GeracaoBloqueio,
  type GeracaoFaltando,
  type ModalidadeAssinatura,
  type VersaoOut,
} from "@/hooks/useContratos";
import type { ParcelaTipo } from "@/types/negociacaoEstruturada";

// ─── Types (contract §1) ────────────────────────────────────────────────────

export type AditivoEstilo = "house" | "formal";

export const ADITIVO_ESTILO_LABEL: Record<AditivoEstilo, string> = {
  house: "Padrão do escritório",
  formal: "Termo aditivo formal",
};

export const ADITIVO_ESTILO_OPTIONS: AditivoEstilo[] = ["house", "formal"];

export type AlteracaoTipo = "pagamento" | "posse" | "comissao" | "outro";

export const ALTERACAO_TIPO_LABEL: Record<AlteracaoTipo, string> = {
  pagamento: "Pagamento",
  posse: "Posse",
  comissao: "Comissão",
  outro: "Outra alteração",
};

/** Print order is fixed server-side (pagamento → posse → comissão → outro);
 *  the editor offers them in the same order. */
export const ALTERACAO_TIPO_OPTIONS: AlteracaoTipo[] = ["pagamento", "posse", "comissao", "outro"];

/** At most ONE of each per aditivo (422 otherwise). */
export const ALTERACAO_TIPOS_UNICOS: AlteracaoTipo[] = ["pagamento", "posse"];

/** `clausula_alvo` = the NUMBER of the original's clause (1 = Primeira). */
export interface AlteracaoPagamento {
  tipo: "pagamento";
  clausula_alvo: number;
  /** Decimal string; set only when the price itself changes. */
  novo_valor?: string | null;
}

export interface AlteracaoPosse {
  tipo: "posse";
  clausula_alvo: number;
  data: string;
  precaria: boolean;
  /** Required when `precaria`. */
  finalidade?: string | null;
}

export type ComissaoMarco = "parcela" | "data" | "financiamento";

export const COMISSAO_MARCO_LABEL: Record<ComissaoMarco, string> = {
  parcela: "No pagamento de uma parcela",
  data: "Em uma data",
  financiamento: "Na assinatura do financiamento",
};

export interface AlteracaoComissao {
  tipo: "comissao";
  clausula_alvo: number;
  parcela_corretagem: number;
  marco: ComissaoMarco;
  parcela_numero?: number | null;
  data?: string | null;
}

export interface AlteracaoOutro {
  tipo: "outro";
  clausula_alvo?: number | null;
  titulo: string;
  texto: string;
}

export type Alteracao = AlteracaoPagamento | AlteracaoPosse | AlteracaoComissao | AlteracaoOutro;

/** A negociação parcela tipo minus `permuta` (422 — amending a permuta is an
 *  `outro`). */
export type ParcelaAditivoTipo = Exclude<ParcelaTipo, "permuta">;

export interface ParcelaAditivoIn {
  tipo: ParcelaAditivoTipo;
  /** Decimal string, `> 0`. */
  valor: string;
  vencimento: string | null;
  evento: string | null;
  forma_pagamento: string | null;
  favorecido_id: string | null;
  confissao_divida: boolean;
}

export interface ParcelaAditivo extends ParcelaAditivoIn {
  id: string;
  ordem: number;
}

export interface AditivoOut {
  id: string;
  contrato_id: string;
  /** 1 = PRIMEIRO … auto, never reused. */
  ordinal: number;
  estilo: AditivoEstilo;
  status: ContratoStatus;
  status_em: string | null;
  status_por: ContratoActor | null;
  alteracoes: Alteracao[];
  parcelas: ParcelaAditivo[];
  assinatura_data: string | null;
  modalidade_assinatura: ModalidadeAssinatura;
  created_at: string;
  updated_at: string | null;
  versao_atual: VersaoOut | null;
  /** `numero` DESC. */
  versoes: VersaoOut[];
}

export interface AditivoCreateBody {
  estilo: AditivoEstilo;
  alteracoes?: Alteracao[];
  parcelas?: ParcelaAditivoIn[];
  assinatura_data?: string | null;
  modalidade_assinatura?: ModalidadeAssinatura;
}

/** Every field optional; a PRESENT `alteracoes`/`parcelas` REPLACES the list. */
export interface AditivoPatchBody {
  estilo?: AditivoEstilo;
  alteracoes?: Alteracao[];
  parcelas?: ParcelaAditivoIn[];
  assinatura_data?: string | null;
  modalidade_assinatura?: ModalidadeAssinatura;
  status?: ContratoStatus;
}

/** `GET …/geracao` — the `POST …/gerar` precondition, same item shapes as
 *  the contract's readiness (a falta about the aditivo itself points at the
 *  DOM id `aditivo-<id>`, see `aditivoDomId`). */
export interface AditivoGeracao {
  aditivo_id: string;
  contrato_id: string;
  ordinal: number;
  estilo: AditivoEstilo;
  /** The date `gerar` uses without a body date. */
  assinatura_data: string | null;
  pronto: boolean;
  faltando: GeracaoFaltando[];
  bloqueios: GeracaoBloqueio[];
  avisos: GeracaoAviso[];
  revisao_juridica_exigida: boolean;
}

export interface GerarAditivoResult {
  versao: VersaoOut;
  avisos: GeracaoAviso[];
}

/** The DOM id the backend's `destino.alvo` names for a falta about the
 *  aditivo itself (`contrato_aditivo.avaliacao.alvo`) — the editor renders
 *  it so the readiness list's "Resolver" lands on it. */
export function aditivoDomId(aditivoId: string): string {
  return `aditivo-${aditivoId}`;
}

const ORDINAIS = [
  "Primeiro",
  "Segundo",
  "Terceiro",
  "Quarto",
  "Quinto",
  "Sexto",
  "Sétimo",
  "Oitavo",
  "Nono",
  "Décimo",
];

/** "Primeiro aditivo", "Segundo aditivo", … then "11º aditivo". */
export function rotuloAditivo(ordinal: number): string {
  const nome = ORDINAIS[ordinal - 1];
  return nome ? `${nome} aditivo` : `${ordinal}º aditivo`;
}

/** Content is frozen server-side once signed/cancelled (409
 *  `ADITIVO_CONGELADO`) — the editor turns read-only. */
export function aditivoCongelado(aditivo: Pick<AditivoOut, "status">): boolean {
  return aditivo.status === "assinado" || aditivo.status === "cancelado";
}

// ─── Keys ───────────────────────────────────────────────────────────────────

const ADITIVOS_KEY = (clienteId: string, contratoId: string) =>
  [...contratosQueryKey(clienteId), contratoId, "aditivos"] as const;

const GERACAO_KEY = (clienteId: string, contratoId: string, aditivoId: string) =>
  [...ADITIVOS_KEY(clienteId, contratoId), aditivoId, "geracao"] as const;

const base = (clienteId: string, contratoId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/contratos/${encodeURIComponent(contratoId)}/aditivos`;

const itemUrl = (clienteId: string, contratoId: string, aditivoId: string) =>
  `${base(clienteId, contratoId)}/${encodeURIComponent(aditivoId)}`;

// ─── Queries ────────────────────────────────────────────────────────────────

/**
 * `GET …/aditivos` (ordinal ASC). 🔴 `aberto` is the lazy gate — the
 * "Aditivos" collapsible of a signed contract — same discipline as
 * `useContratoGeracao`: nothing is fetched for a contract nobody looked at.
 */
export function useAditivos(clienteId: string | null, contratoId: string | null, aberto: boolean) {
  return useQuery({
    queryKey: ADITIVOS_KEY(clienteId ?? "__none__", contratoId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<{ aditivos: AditivoOut[] }>(
        base(clienteId as string, contratoId as string),
      );
      return res?.aditivos ?? [];
    },
    enabled: aberto && !!clienteId && !!contratoId,
  });
}

/** `GET …/aditivos/{id}/geracao` — readiness; lazy on the "Gerar aditivo"
 *  collapsible. */
export function useAditivoGeracao(
  clienteId: string | null,
  contratoId: string | null,
  aditivoId: string | null,
  aberto: boolean,
) {
  return useQuery({
    queryKey: GERACAO_KEY(clienteId ?? "__none__", contratoId ?? "__none__", aditivoId ?? "__none__"),
    queryFn: () =>
      api.get<AditivoGeracao>(
        `${itemUrl(clienteId as string, contratoId as string, aditivoId as string)}/geracao`,
      ),
    enabled: aberto && !!clienteId && !!contratoId && !!aditivoId,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

export function useAditivoMutations(clienteId: string, contratoId: string) {
  const qc = useQueryClient();
  /** The list AND every aditivo's readiness (nested under the list key) — a
   *  saved amendment / a new version moves what `geracao` reports. */
  const invalidarLista = () => qc.invalidateQueries({ queryKey: ADITIVOS_KEY(clienteId, contratoId) });

  const criar = useMutation({
    mutationFn: (body: AditivoCreateBody) =>
      api.post<AditivoOut>(base(clienteId, contratoId), body),
    onSuccess: invalidarLista,
  });

  const atualizar = useMutation({
    mutationFn: ({ aditivoId, patch }: { aditivoId: string; patch: AditivoPatchBody }) =>
      api.patch<AditivoOut>(itemUrl(clienteId, contratoId, aditivoId), patch),
    onSuccess: invalidarLista,
  });

  /** `POST …/gerar` — a new version, always `revisao_juridica: aguardando`.
   *  Errors come back as `ContratoGeracaoError` (400 `ADITIVO_INCOMPLETO`,
   *  422 `CONTRATO_LINT` / `CONTRATO_PDF_NAO_GERADO`). */
  const gerar = useMutation({
    mutationFn: ({ aditivoId, assinaturaData }: { aditivoId: string; assinaturaData?: string }) =>
      postGeracao<GerarAditivoResult>(
        `${itemUrl(clienteId, contratoId, aditivoId)}/gerar`,
        assinaturaData ? { assinatura_data: assinaturaData } : {},
      ),
    onSuccess: invalidarLista,
  });

  /** 🔴 Only on an explicit "Abrir"/"Baixar" click — the URL is short-lived
   *  and its minting is LGPD-logged. `impressao` = the FINAL copy, refused
   *  (409) while the legal review waits. */
  const getUrl = useMutation({
    mutationFn: ({
      aditivoId,
      versaoId,
      intent = "view",
      formato,
      impressao = false,
    }: {
      aditivoId: string;
      versaoId: string;
      intent?: "view" | "download";
      formato?: "pdf" | "docx";
      impressao?: boolean;
    }) =>
      api.get<{ url: string; expires_at: string }>(
        `${itemUrl(clienteId, contratoId, aditivoId)}/versoes/${encodeURIComponent(versaoId)}/url?intent=${intent}${formato === "docx" ? "&formato=docx" : ""}${impressao ? "&impressao=true" : ""}`,
      ),
  });

  /** Admin/owner only server-side (403 otherwise). Returns the aditivo. */
  const aprovarRevisaoJuridica = useMutation({
    mutationFn: ({ aditivoId, versaoId }: { aditivoId: string; versaoId: string }) =>
      api.post<AditivoOut>(
        `${itemUrl(clienteId, contratoId, aditivoId)}/versoes/${encodeURIComponent(versaoId)}/revisao-juridica`,
        {},
      ),
    onSuccess: invalidarLista,
  });

  return { criar, atualizar, gerar, getUrl, aprovarRevisaoJuridica };
}
