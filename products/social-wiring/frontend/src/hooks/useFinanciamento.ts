/**
 * Financiamento / Escritura — the deal's closing paperwork (migration 078).
 *
 * 🔴 THESE DOCUMENTS ARE ACCESS-LOGGED SERVER-SIDE.
 * Opening one mints a signed URL, and that call appends to
 * `atendimento_documento_acessos` naming the user. So the UI must never
 * pre-fetch a URL "just in case" or refresh one on a timer: every fetch is a
 * recorded access to somebody's income tax return, and a log full of accesses
 * nobody made is worse than no log.
 *
 * `useDocumentoAcessos` is therefore lazy — enabled only when a viewer
 * actually opens the log.
 */
import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, supabase } from "@noctusai/seed/infra";

import { apiUrl } from "@/lib/apiBase";

// ─── Types ──────────────────────────────────────────────────────────────────

export type SituacaoFinanciamento = "pendente" | "aprovado" | "recusado";

/** Migration 171 (`sw-negociacao-extracao-contract.md` §C.1) — the SAME
 *  five-state machine every extraction surface in this product uses
 *  (`EmpresaDocumentoExtracaoStatus`, `Documento.extracao_status`). `null`
 *  means this `tipo_documento` has no registered extractor
 *  (`fontes.FONTES[tipo]` absent — e.g. `certidao_casamento`), so no
 *  extraction chrome renders for it at all. */
export type FinanciamentoDocumentoExtracaoStatus =
  | "pendente"
  | "processando"
  | "ok"
  | "sem_dados"
  | "erro";

/** The reading, kept loose rather than typed field-by-field — same
 *  rationale `EmpresaDocumentoExtracaoDados` gives: this UI never composes
 *  from it, only displays the handful of avisos the server already names. */
export type FinanciamentoDocumentoExtracaoDados = Record<string, unknown>;

export interface FinanciamentoDocumento {
  id: string;
  nome_original: string;
  mime_type: string;
  tamanho_bytes: number;
  tipo_documento: string;
  /** `"escritura"` | `"fgts"` | `"financiamento"` — the section this
   *  belongs in, server-decided (derived from `tipos.STORE` membership,
   *  never from a name pattern — contract §A). */
  grupo: string;
  categoria_lgpd: string | null;
  retencao_ate: string | null;
  enviado_por: { id: string; nome: string | null } | null;
  created_at: string;
  extracao_status: FinanciamentoDocumentoExtracaoStatus | null;
  extracao_erro: string | null;
  extracao_dados: FinanciamentoDocumentoExtracaoDados | null;
  /** e.g. `"documento_de_outro_negocio"`, `"quadro_resumo_soma_divergente"`,
   *  `"agente_financeiro_nao_cadastrado"`, `"varias_parcelas_financiamento"`,
   *  `"quadro_resumo_nao_encontrado"` (contract §D.5/§E.2). `null` = no
   *  warning attached to this reading. */
  extracao_aviso: string | null;
  extracao_descartada_em: string | null;
}

/** A terminal status is anything other than the two in-flight values —
 *  including `null` (no extractor for this type). Shared by the query's own
 *  `refetchInterval` and the polling-invalidation hook below, mirroring
 *  `useEmpresas.extracaoEmAndamento`. */
function extracaoEmAndamento(status: FinanciamentoDocumentoExtracaoStatus | null): boolean {
  return status === "pendente" || status === "processando";
}

export { extracaoEmAndamento as financiamentoExtracaoEmAndamento };

/** pt-BR for an `extracao_aviso` value — falls back to the raw key, same
 *  never-blank posture every other label map in this product takes. */
export const AVISO_LABEL: Record<string, string> = {
  documento_de_outro_negocio: "Este documento parece ser de outro negócio — nada foi aplicado.",
  quadro_resumo_soma_divergente:
    "A soma do Quadro Resumo não bate com o valor de compra e venda — confira os valores.",
  agente_financeiro_nao_cadastrado:
    "O banco lido não está cadastrado como agente financeiro.",
  varias_parcelas_financiamento:
    "Há mais de uma parcela de financiamento — nenhuma foi preenchida automaticamente.",
  quadro_resumo_nao_encontrado:
    "O Quadro Resumo não foi encontrado nas páginas lidas.",
};

export function rotuloAviso(aviso: string | null | undefined): string {
  if (!aviso) return "";
  return AVISO_LABEL[aviso] ?? aviso;
}

/** The agent as the card renders it — a subset of the registry's own row.
 *  `ativo` is present so the panel can MARK a retired bank rather than
 *  pretend it is still selectable. */
export interface AgenteFinanceiroResumo {
  id: string;
  nome: string;
  codigo_banco: string | null;
  agencia: string | null;
  ativo: boolean;
  /** H7 (owner, 2026-09-25) — `"auto_criado"` when the registry row was
   *  created BY an extraction landing (bank read off a contract/proposta,
   *  no matching `agentes_financeiros` row) rather than typed by a person.
   *  `null`/`"manual"` for every hand-registered bank — the ordinary case
   *  today. Field name picked (not pinned by §E5); flag for reconciliation. */
  origem?: "manual" | "auto_criado" | null;
}

export interface Financiamento {
  atendimento_id: string;
  situacao: SituacaoFinanciamento;
  situacao_em: string | null;
  situacao_motivo: string | null;
  /** H6 (owner, 2026-09-25) — `"extraido"` when a SIGNED contrato de
   *  financiamento auto-set `situacao='aprovado'`; `null`/`"manual"` for a
   *  human's own choice via the pendente/aprovado/recusado buttons. Field
   *  name picked (not pinned by §E5, which lists only the fgts/
   *  numero_proposta/agente_financeiro quintets in §C.5 — H6 postdates that
   *  draft); flag for reconciliation with S2. */
  situacao_origem?: "manual" | "extraido" | null;
  fgts: boolean;
  observacoes: string | null;
  agente_financeiro_id: string | null;
  /**
   * 🔴 Resolved WITHOUT the `ativo` filter the dropdown uses. A bank retired
   * after it financed this deal keeps rendering here — otherwise the panel
   * would blank the institution named on a signed contract because somebody
   * tidied a settings list.
   */
  agente_financeiro: AgenteFinanceiroResumo | null;
  numero_proposta: string | null;
  created_at: string | null;
  updated_at: string | null;
  existe: boolean;
  /** The document types each section offers, in order. Server-owned. */
  tipos_escritura: string[];
  tipos_fgts: string[];
  /** New "Financiamento" doc group (contract §A/§F) —
   *  `["proposta_financiamento", "contrato_financiamento"]` today. Field
   *  name picked (not pinned by §E5); flag for reconciliation with S2. */
  tipos_financiamento_docs: string[];
  /** ITBI doc group (`guia_itbi`, `comprovante_itbi`), server-provided. */
  tipos_itbi: string[];
  /** Gates the new "Financiamento" section's visibility (contract §A: "shown
   *  when the deal has a financiamento parcela or `financiamento.situacao`
   *  is set"). Server-computed — this panel has no access to parcela data
   *  of its own. Field name picked (not pinned by §E5); flag for
   *  reconciliation with S2. */
  tem_parcela_financiamento: boolean;
  documentos: FinanciamentoDocumento[];
}

export interface FinanciamentoPatch {
  situacao?: SituacaoFinanciamento;
  situacao_motivo?: string | null;
  fgts?: boolean;
  observacoes?: string | null;
  /** An explicit null clears the selection — "not decided yet" is a real
   *  state and must stay reachable after one has been chosen. */
  agente_financeiro_id?: string | null;
  numero_proposta?: string | null;
}

export interface Acesso {
  id: string;
  acao: string;
  usuario: { id: string; nome: string | null } | null;
  created_at: string;
}

/** Human labels for the document types. The KEYS are the server's contract.
 *  Defined in `@/lib/documentoTipos` and re-exported here so this hook's
 *  existing consumers keep their import — one definition, two surfaces, no
 *  second copy to drift out of step (the retention screen reads the same map).
 */
export { TIPO_LABEL } from "@/lib/documentoTipos";

export const SITUACAO_LABEL: Record<SituacaoFinanciamento, string> = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  recusado: "Recusado",
};

// ─── Keys ───────────────────────────────────────────────────────────────────

const KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "financiamento"] as const;
const ACESSOS_KEY = (clienteId: string, docId: string) =>
  [...KEY(clienteId), "acessos", docId] as const;

const base = (clienteId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/financiamento`;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useFinanciamento(clienteId: string | null) {
  return useQuery({
    queryKey: KEY(clienteId ?? "__none__"),
    queryFn: async () => api.get<Financiamento>(base(clienteId as string)),
    enabled: !!clienteId,
    // Poll until every document's OWN extraction lands (P1/883 pattern,
    // `useEmpresaDocumentos`/`useCardHub.useExtracaoPollingInvalidation`) —
    // extraction runs server-side and asynchronously, so refetching is the
    // only way this panel learns a read landed. Stops the instant nothing
    // is in flight; never polls a card with no pending document.
    refetchInterval: (q) => {
      const docs = (q.state.data as Financiamento | undefined)?.documentos ?? [];
      return docs.some((d) => extracaoEmAndamento(d.extracao_status)) ? 2500 : false;
    },
  });
}

export function useFinanciamentoAcessos(
  clienteId: string | null,
  documentoId: string | null,
) {
  return useQuery({
    queryKey: ACESSOS_KEY(clienteId ?? "__none__", documentoId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<{ items: Acesso[]; total: number }>(
        `${base(clienteId as string)}/documentos/${encodeURIComponent(
          documentoId as string,
        )}/acessos`,
      );
      return res?.items ?? [];
    },
    // Lazy on purpose — the log is opened, not polled. Reading it is itself
    // free (metadata, not content), but fetching it unasked is noise.
    enabled: !!clienteId && !!documentoId,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function useFinanciamentoMutation(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: FinanciamentoPatch) =>
      api.patch<Financiamento>(base(clienteId), patch),
    onSuccess: (data) => qc.setQueryData(KEY(clienteId), data),
  });
}

export function useFinanciamentoDocumentoMutations(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: KEY(clienteId) });

  // Multipart bypasses the JSON-only seed `api` client — raw fetch with the
  // auth header pulled from supabase.
  const upload = useMutation({
    mutationFn: async ({
      file,
      tipoDocumento,
    }: {
      file: File;
      tipoDocumento: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("tipo_documento", tipoDocumento);
      const headers = await getAuthHeader();
      const response = await fetch(apiUrl(`${base(clienteId)}/documentos`), {
        method: "POST",
        headers, // no content-type — the browser sets the multipart boundary
        body: formData,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        const message = detail?.error?.message ?? `Erro HTTP ${response.status}`;
        throw new Error(message);
      }
      return (await response.json()) as FinanciamentoDocumento;
    },
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: ({
      documentoId,
      motivo,
    }: {
      documentoId: string;
      motivo: string;
    }) =>
      api.delete(
        `${base(clienteId)}/documentos/${encodeURIComponent(documentoId)}?motivo=${encodeURIComponent(motivo)}`,
      ),
    onSuccess: invalidate,
  });

  /** 🔴 Each call is a RECORDED access. Never call this speculatively. */
  const getUrl = useMutation({
    mutationFn: ({
      documentoId,
      intent = "view",
    }: {
      documentoId: string;
      intent?: "view" | "download";
    }) =>
      api.get<{ url: string; expires_at: string }>(
        `${base(clienteId)}/documentos/${encodeURIComponent(documentoId)}/url?intent=${intent}`,
      ),
  });

  return { upload, remove, getUrl };
}

/**
 * The three extraction actions the negociação/financiamento contract adds
 * (contract §E.5): `reextrair` (re-run a stuck/never-run read, refused
 * server-side while pendente/processando), `confirmar` (D2 — stamps
 * `confirmado_por`/`confirmado_em` on every still-pending value THIS
 * document proposed) and `descartar` (marks `extracao_descartada_*`; the
 * file and its reading are both kept). Mirrors
 * `useEmpresas.useEmpresaExtracao`'s three-mutation bundle — same shape,
 * financiamento-scoped routes.
 */
export function useFinanciamentoDocumentoExtracao(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: KEY(clienteId) });

  const reextrair = useMutation({
    mutationFn: (documentoId: string) =>
      api.post<FinanciamentoDocumento>(
        `${base(clienteId)}/documentos/${encodeURIComponent(documentoId)}/extrair`,
        {},
      ),
    onSuccess: invalidate,
  });

  const confirmar = useMutation({
    mutationFn: (documentoId: string) =>
      api.post<FinanciamentoDocumento>(
        `${base(clienteId)}/documentos/${encodeURIComponent(documentoId)}/extracao/confirmar`,
        {},
      ),
    onSuccess: invalidate,
  });

  const descartar = useMutation({
    mutationFn: (documentoId: string) =>
      api.post<FinanciamentoDocumento>(
        `${base(clienteId)}/documentos/${encodeURIComponent(documentoId)}/extracao/descartar`,
        {},
      ),
    onSuccess: invalidate,
  });

  return { reextrair, confirmar, descartar };
}

/**
 * P1/883 pattern (`useEmpresas.useEmpresaExtracaoPollingInvalidation`,
 * `useCardHub.useExtracaoPollingInvalidation`) — mount alongside
 * `useFinanciamento(clienteId)` purely for the side effect. That query
 * already polls (and re-renders) this document's OWN `extracao_status`, but
 * a landed reading also fills surfaces NO financiamento query owns: the
 * negociação valor/parcelas (H2/H4), the favorecidos list (H5) and the
 * agentes financeiros registry (H7, a NEW row may have been auto-created).
 * Left unwired, those panels would keep showing the pre-extraction state
 * until a hard reload — the exact shape the imóvel G2 bug had.
 */
export function useFinanciamentoExtracaoPollingInvalidation(clienteId: string | null): void {
  const qc = useQueryClient();
  const prevStatusRef = useRef<Map<string, FinanciamentoDocumentoExtracaoStatus | null>>(
    new Map(),
  );
  const query = useFinanciamento(clienteId);

  useEffect(() => {
    if (!clienteId || !query.data) return;
    const prev = prevStatusRef.current;
    const docs = query.data.documentos;
    const proximo = new Map(docs.map((d) => [d.id, d.extracao_status] as const));
    const transicionou = docs.some((d) => {
      const antes = prev.get(d.id);
      // `undefined` = first appearance (mount, or just uploaded) — never
      // itself a transition; only a PREVIOUSLY-seen pending status turning
      // terminal counts.
      return antes !== undefined && extracaoEmAndamento(antes) && !extracaoEmAndamento(d.extracao_status);
    });
    prevStatusRef.current = proximo;
    if (transicionou) {
      void qc.invalidateQueries({ queryKey: KEY(clienteId) });
      void qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId, "negociacao"] });
      void qc.invalidateQueries({
        queryKey: ["sw", "clientes", clienteId, "negociacao", "estruturada"],
      });
      void qc.invalidateQueries({
        queryKey: ["sw", "clientes", clienteId, "negociacao", "conflitos"],
      });
      void qc.invalidateQueries({ queryKey: ["sw", "agentes-financeiros"] });
    }
  }, [clienteId, query.data, qc]);
}

export function formatBytes(n: number): string {
  const mb = n / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${Math.round(n / 1024)} KB`;
}
