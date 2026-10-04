/**
 * Certidões per party — the card's "Certidões" tab read + every write it
 * fires (`atendimento-partes-imoveis-CONTRACT.md` §1). `useCardHub.ts` and
 * `useCertidoesMatriz.ts` stay untouched; every mutation here invalidates
 * THIS tab's own key.
 *
 * Polling: the read refetches every `POLL_MS` while any cell is still being
 * produced (`certidaoEmAndamento`) and stops by itself once all settle.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@noctusai/seed/infra";

import type { CertidaoMatrizLinhaCustomizada } from "@/types/certidoesMatriz";
import type {
  CelulaEnsureResponse,
  CertidaoDivergencia,
  CienciaPcenResult,
  CertidaoParteCelula,
  CertidoesPartesResponse,
  EmissaoResponse,
  RelerCertidoesResponse,
  SolicitarEmissaoInput,
  UploadCelulaInput,
} from "@/types/certidoesPartes";

export const POLL_MS = 4000;

export const certidoesPartesKey = (clienteId: string, atendimentoId?: string | null) =>
  ["sw", "clientes", clienteId, "certidoes", "partes", atendimentoId ?? null] as const;

const clienteBase = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}`;

/** A cell the backend is still producing. A manual-origin `pendente` is an
 *  empty upload placeholder (§1.4) that nothing will ever finish on its own,
 *  so it must NOT keep the poll alive forever. */
export function certidaoEmAndamento(c: CertidaoParteCelula): boolean {
  const s = c.status_processamento;
  if (s === "processando" || s === "na_fila") return true;
  // A live emission's re-read keeps `sucesso`; its own marker says "running".
  if (c.releitura?.em_andamento) return true;
  return s === "pendente" && c.origem !== "manual";
}

export function partesTemEmAndamento(data: CertidoesPartesResponse | undefined): boolean {
  if (!data) return false;
  return data.partes.some((p) => Object.values(p.celulas).some(certidaoEmAndamento));
}

export function useCertidoesPartes(clienteId: string | null, atendimentoId?: string | null) {
  return useQuery({
    queryKey: certidoesPartesKey(clienteId ?? "__none__", atendimentoId),
    queryFn: () =>
      api.get<CertidoesPartesResponse>(`${clienteBase(clienteId as string)}/certidoes/partes`, {
        ...(atendimentoId ? { atendimento_id: atendimentoId } : {}),
      }),
    enabled: !!clienteId,
    // Keep the previous party list mounted while the key changes / refetches.
    placeholderData: (prev) => prev,
    refetchInterval: (query) => (partesTemEmAndamento(query.state.data) ? POLL_MS : false),
  });
}

function useInvalidatePartes(clienteId: string) {
  const qc = useQueryClient();
  return () =>
    qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId, "certidoes", "partes"] });
}

const erroMsg = (e: unknown) => (e instanceof Error ? e.message : "Tente novamente.");

/** `POST …/certidoes/partes/{kind}/{alvo_id}/emissao` — all (`tipos:null`) or selected. */
export function useSolicitarEmissao(clienteId: string, atendimentoId?: string | null) {
  const invalidate = useInvalidatePartes(clienteId);
  return useMutation({
    mutationFn: ({ kind, alvoId, tipos }: SolicitarEmissaoInput) =>
      api.post<EmissaoResponse>(
        `${clienteBase(clienteId)}/certidoes/partes/${kind}/${encodeURIComponent(alvoId)}/emissao`,
        { tipos, atendimento_id: atendimentoId ?? null },
      ),
    onSuccess: () => {
      toast.success("Emissão solicitada. As certidões aparecem aqui assim que ficarem prontas.");
      void invalidate();
    },
    onError: (e) => toast.error("Erro ao solicitar emissão", { description: erroMsg(e) }),
  });
}

/** `POST …/certidoes/resultados/{resultado_id}/reemitir` — one cell, body `{}`. */
export function useReemitirResultado(clienteId: string) {
  const invalidate = useInvalidatePartes(clienteId);
  return useMutation({
    mutationFn: (resultadoId: string) =>
      api.post<EmissaoResponse>(
        `${clienteBase(clienteId)}/certidoes/resultados/${encodeURIComponent(resultadoId)}/reemitir`,
        {},
      ),
    onSuccess: () => {
      toast.success("Re-emissão solicitada.");
      void invalidate();
    },
    onError: (e) => toast.error("Erro ao re-emitir certidão", { description: erroMsg(e) }),
  });
}

/** `POST …/certidoes/resultados/{resultado_id}/ciencia-pcen` — the operator's
 *  acknowledgment (`entendi`) of a Receita PCEN 2ª via, or a support question
 *  (`duvida`). Invalidates this tab AND every contract readiness of the card
 *  (the gate there flips from "aguardando ciência" to "pronto"). */
export function useCienciaPcen(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ resultadoId, acao }: { resultadoId: string; acao: "entendi" | "duvida" }) =>
      api.post<CienciaPcenResult>(
        `${clienteBase(clienteId)}/certidoes/resultados/${encodeURIComponent(resultadoId)}/ciencia-pcen`,
        { acao },
      ),
    onSuccess: (r) => {
      if (r.acao === "entendi") toast.success("Ciência registrada.");
      void qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId, "certidoes", "partes"] });
      void qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId, "contratos"] });
    },
    onError: (e) => toast.error("Não foi possível registrar", { description: erroMsg(e) }),
  });
}

/** Every certidões read a re-read can change: this tab, the per-party /
 *  per-cliente / per-empresa panels and the consulta screens. */
function useInvalidateCertidoes(clienteId: string) {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId, "certidoes", "partes"] }),
      qc.invalidateQueries({ queryKey: ["certidao-resultados-parte"] }),
      qc.invalidateQueries({ queryKey: ["certidao-resultados-cliente"] }),
      qc.invalidateQueries({ queryKey: ["certidao-resultados-empresa"] }),
      qc.invalidateQueries({ queryKey: ["certidao-consulta"] }),
    ]);
}

/** `POST /api/certidoes/resultados/{id}/reler` — re-read the PDF already
 *  stored for one certidão (no new file, no new live query; a value a
 *  person confirmed or the registry returned is kept — differences come
 *  back as `releitura.divergencias`). */
export function useRelerResultado(clienteId: string) {
  const invalidate = useInvalidateCertidoes(clienteId);
  return useMutation({
    mutationFn: (resultadoId: string) =>
      api.post(`/api/certidoes/resultados/${encodeURIComponent(resultadoId)}/reler`, {}),
    onSuccess: () => {
      toast.success("Lendo o documento novamente…");
      void invalidate();
    },
    onError: (e) => toast.error("Não foi possível ler o documento novamente", { description: erroMsg(e) }),
  });
}

/** "Reler todas" for ONE party: `POST /api/certidoes/resultados/{id}/reler`
 *  for each of its re-readable cells, one after the other (each call only
 *  schedules the read). Resolves with how many were accepted / refused. */
export function useRelerResultados(clienteId: string) {
  const invalidate = useInvalidateCertidoes(clienteId);
  return useMutation({
    mutationFn: async (resultadoIds: string[]) => {
      let relidos = 0;
      let recusados = 0;
      for (const id of resultadoIds) {
        try {
          await api.post(`/api/certidoes/resultados/${encodeURIComponent(id)}/reler`, {});
          relidos += 1;
        } catch {
          recusados += 1;
        }
      }
      return { relidos, recusados };
    },
    onSuccess: ({ relidos, recusados }) => {
      if (relidos > 0) {
        toast.success(relidos === 1 ? "Lendo 1 certidão novamente…" : `Lendo ${relidos} certidões novamente…`);
      }
      if (recusados > 0) {
        toast.error(
          recusados === 1
            ? "1 certidão não pôde ser lida novamente (já em leitura ou PDF ausente)."
            : `${recusados} certidões não puderam ser lidas novamente (já em leitura ou PDF ausente).`,
        );
      }
      void invalidate();
    },
    onError: (e) => toast.error("Não foi possível reler as certidões", { description: erroMsg(e) }),
  });
}

/** Apply what a re-read found (its divergences) — the human's decision, via
 *  the EXISTING confirm/correct route (`PATCH /api/certidoes/resultados/{id}`),
 *  which also locks the row and clears the aviso. */
export function useAplicarValoresLidos(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = useInvalidateCertidoes(clienteId);
  return useMutation({
    mutationFn: ({ resultadoId, divergencias }: { resultadoId: string; divergencias: CertidaoDivergencia[] }) =>
      api.patch(
        `/api/certidoes/resultados/${encodeURIComponent(resultadoId)}`,
        Object.fromEntries(divergencias.map((d) => [d.campo, d.valor_lido])),
      ),
    onSuccess: () => {
      toast.success("Valores lidos aplicados.");
      void invalidate();
      void qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId, "contratos"] });
    },
    onError: (e) => toast.error("Não foi possível aplicar os valores lidos", { description: erroMsg(e) }),
  });
}

/** `POST /api/clientes/{id}/certidoes/reler` — every stored certidão PDF of
 *  the card's parties (uploads and live receipts), re-read on the files
 *  already stored. */
export function useRelerCertidoesCard(clienteId: string, atendimentoId?: string | null) {
  const invalidate = useInvalidateCertidoes(clienteId);
  return useMutation({
    mutationFn: () =>
      api.post<RelerCertidoesResponse>(`${clienteBase(clienteId)}/certidoes/reler`, {
        atendimento_id: atendimentoId ?? null,
      }),
    onSuccess: (r) => {
      if (r.relidos === 0) {
        toast.info("Nenhuma certidão com PDF armazenado para ler novamente.");
      } else {
        toast.success(
          r.relidos === 1 ? "Lendo 1 certidão novamente…" : `Lendo ${r.relidos} certidões novamente…`,
        );
      }
      if (r.erros > 0) {
        toast.error(
          r.erros === 1
            ? "1 certidão não pôde ser lida novamente — envie o PDF de novo se o problema continuar."
            : `${r.erros} certidões não puderam ser lidas novamente — envie os PDFs de novo se o problema continuar.`,
        );
      }
      void invalidate();
    },
    onError: (e) => toast.error("Não foi possível reler as certidões", { description: erroMsg(e) }),
  });
}

/** Upload into a cell: §1.4 ensure-cell, then the EXISTING §1.5 upload route. */
export function useUploadNaCelula(clienteId: string, atendimentoId?: string | null) {
  const invalidate = useInvalidatePartes(clienteId);
  return useMutation({
    mutationFn: async ({ kind, alvoId, linhaChave, file }: UploadCelulaInput) => {
      if (file.type !== "application/pdf") throw new Error("Apenas arquivos PDF são aceitos.");
      const cel = await api.post<CelulaEnsureResponse>(`${clienteBase(clienteId)}/certidoes/celulas`, {
        kind,
        alvo_id: alvoId,
        linha_chave: linhaChave,
        atendimento_id: atendimentoId ?? null,
      });
      const form = new FormData();
      form.append("file", file);
      await api.upload(`/api/certidoes/resultados/${cel.resultado_id}/upload`, form);
      return cel;
    },
    onSuccess: () => {
      toast.success("Certidão enviada. Lendo o PDF…");
      void invalidate();
    },
    onError: (e) => {
      toast.error("Erro ao enviar certidão", { description: erroMsg(e) });
      void invalidate();
    },
  });
}

/** Custom-row CRUD (§1.6, EXISTING routes) — invalidates THIS tab's key. */
export function useCriarLinhaPartes(clienteId: string) {
  const invalidate = useInvalidatePartes(clienteId);
  return useMutation({
    mutationFn: (nome: string) =>
      api.post<CertidaoMatrizLinhaCustomizada>(`${clienteBase(clienteId)}/certidoes/matriz/linhas`, {
        nome,
      }),
    onSuccess: () => void invalidate(),
    onError: (e) => toast.error("Erro ao adicionar certidão", { description: erroMsg(e) }),
  });
}

export function useRenomearLinhaPartes(clienteId: string) {
  const invalidate = useInvalidatePartes(clienteId);
  return useMutation({
    mutationFn: ({ linhaId, nome }: { linhaId: string; nome: string }) =>
      api.patch<CertidaoMatrizLinhaCustomizada>(
        `${clienteBase(clienteId)}/certidoes/matriz/linhas/${linhaId}`,
        { nome },
      ),
    onSuccess: () => void invalidate(),
    onError: (e) => toast.error("Erro ao renomear certidão", { description: erroMsg(e) }),
  });
}

export function useRemoverLinhaPartes(clienteId: string) {
  const invalidate = useInvalidatePartes(clienteId);
  return useMutation({
    mutationFn: (linhaId: string) =>
      api.delete(`${clienteBase(clienteId)}/certidoes/matriz/linhas/${linhaId}`),
    onSuccess: () => void invalidate(),
    onError: (e) => toast.error("Erro ao remover certidão", { description: erroMsg(e) }),
  });
}

export { useInvalidatePartes };
