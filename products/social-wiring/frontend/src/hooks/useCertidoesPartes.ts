/**
 * Certidões per party — the card's "Certidões" tab read + every write it
 * fires (`atendimento-partes-imoveis-CONTRACT.md` §1). `useCardHub.ts` and
 * `useCertidoesMatriz.ts` stay untouched; every mutation here invalidates
 * THIS tab's own key.
 *
 * Polling: the read refetches every `POLL_MS` while any cell is still being
 * produced (`certidaoEmAndamento`) and stops by itself once all settle.
 */
import { tipoArquivoAceito } from "@noctusai/lib";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@noctusai/seed/infra";
import { jobPolling } from "@noctusai/lib";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import {
  celulaComResultado,
  comCelulaDoResultado,
  comParteSubstituida,
  comCelulaEditada,
  linhaDigitada,
  type ResultadoServidor,
} from "@/components/card/certidoes/certidoesCache";
import type { ResultadoPatchInput } from "@/types/certidoesEstruturadas";
import type { CertidaoMatrizLinhaCustomizada } from "@/types/certidoesMatriz";
import { authenticatedFetch, triggerBlobDownload } from "@/lib/file-download";
import { apiUrl } from "@/lib/apiBase";
import type {
  AntigoCriarInput,
  AntigoCriarResponse,
  AntigosEstado,
  AntigosSincronizacao,
  CancelarEmissaoInput,
  CelulaEnsureResponse,
  CertidaoDivergencia,
  CienciaPcenResult,
  CertidaoParteCelula,
  CertidoesPartesResponse,
  ExigenciasCertidoes,
  EmissaoResponse,
  ParteAtualizadaResponse,
  RelerCertidoesResponse,
  DigitarCelulaInput,
  SolicitarEmissaoInput,
  UploadCelulaInput,
} from "@/types/certidoesPartes";

export const POLL_MS = 4000;

export const certidoesPartesKey = (clienteId: string, atendimentoId?: string | null) =>
  ["sw", "clientes", clienteId, "certidoes", "partes", atendimentoId ?? null] as const;

const clienteBase = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}`;

/** A cell the backend is still producing. An `aguarda_humano` `pendente` is an
 *  empty upload placeholder (§1.4) that nothing will ever finish on its own,
 *  so it must NOT keep the poll alive forever. (`origem` is who produced the
 *  VALUES — never a polling signal.) */
export function certidaoEmAndamento(c: CertidaoParteCelula): boolean {
  const s = c.status_processamento;
  if (s === "processando" || s === "na_fila") return true;
  // A re-emission in flight behind older valid evidence (the winner keeps the cell).
  const t = c.ultima_tentativa?.status;
  if (t === "processando" || t === "na_fila" || t === "pendente") return true;
  // A live emission's re-read keeps `sucesso`; its own marker says "running".
  if (c.releitura?.em_andamento) return true;
  // An untouched manual placeholder (`aguarda_humano`) is waiting on a person.
  return s === "pendente" && !c.aguarda_humano;
}

export function partesTemEmAndamento(data: CertidoesPartesResponse | undefined): boolean {
  if (!data) return false;
  return data.partes.some((p) => Object.values(p.celulas).some(certidaoEmAndamento));
}

/** Emission just requested for a cliente: the consulta rows may not exist yet
 *  (async InfoSimples job), so the first re-reads can still show NO cell in
 *  flight. Keep polling through this window; it ends as soon as a cell was seen
 *  in flight and has settled again, or at the deadline. */
export const EMISSAO_GRACE_MS = 90_000;
const emissaoSolicitada = new Map<string, { ate: number; viuAndamento: boolean }>();

export function marcarEmissaoSolicitada(clienteId: string, agora = Date.now()) {
  emissaoSolicitada.set(clienteId, { ate: agora + EMISSAO_GRACE_MS, viuAndamento: false });
}

export function emissaoAguardandoAssentar(
  clienteId: string,
  data: CertidoesPartesResponse | undefined,
  agora = Date.now(),
): boolean {
  const g = emissaoSolicitada.get(clienteId);
  const andamento = partesTemEmAndamento(data);
  if (!g) return andamento;
  if (andamento) {
    g.viuAndamento = true;
    return true;
  }
  if (g.viuAndamento || agora >= g.ate) {
    emissaoSolicitada.delete(clienteId);
    return false;
  }
  return true;
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
    ...jobPolling<CertidoesPartesResponse>(
      (d) => emissaoAguardandoAssentar(clienteId ?? "__none__", d),
      POLL_MS,
    ),
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
  return useMutation({ // noc-allow: invalidate-only — queues emissions that finish asynchronously; the response is only the consulta ids, the cells arrive via the polled partes read
    mutationFn: ({ kind, alvoId, tipos }: SolicitarEmissaoInput) =>
      api.post<EmissaoResponse>(
        `${clienteBase(clienteId)}/certidoes/partes/${kind}/${encodeURIComponent(alvoId)}/emissao`,
        { tipos, atendimento_id: atendimentoId ?? null },
      ),
    onSuccess: (r) => {
      toast.success("Emissão solicitada. As certidões aparecem aqui assim que ficarem prontas.");
      if (r.ignoradas?.length) {
        toast.info(
          r.ignoradas.length === 1
            ? "1 certidão já válida ou em emissão não foi comprada de novo."
            : `${r.ignoradas.length} certidões já válidas ou em emissão não foram compradas de novo.`,
        );
      }
      marcarEmissaoSolicitada(clienteId);
      void invalidate();
    },
    onError: (e) => toast.error("Erro ao solicitar emissão", { description: erroMsg(e) }),
  });
}

/** What every card-scoped emission control invalidates besides the grid it writes. */
const leiturasDoResultado = (clienteId: string) => [
  ["sw", "clientes", clienteId, "contratos"],
  ["certidao-resultados-parte"],
  ["certidao-resultados-cliente"],
  ["certidao-resultados-empresa"],
];

/** "Cancelar emissão": stop ONE running cell (`{resultadoId}`) or every running
 *  cell of a party (`{kind, alvoId}`). Automatic emissions only (the server
 *  refuses a manual cell). The answer is the party as it reads afterwards. */
export function useCancelarEmissao(clienteId: string, atendimentoId?: string | null) {
  return useCacheWriteMutation<ParteAtualizadaResponse, CancelarEmissaoInput>({
    mutationFn: (input) =>
      "resultadoId" in input
        ? api.post<ParteAtualizadaResponse>(
            `${clienteBase(clienteId)}/certidoes/resultados/${encodeURIComponent(input.resultadoId)}/cancelar`,
            {},
          )
        : api.post<ParteAtualizadaResponse>(
            `${clienteBase(clienteId)}/certidoes/partes/${input.kind}/${encodeURIComponent(input.alvoId)}/cancelar`,
            { atendimento_id: atendimentoId ?? null },
          ),
    targets: [
      {
        queryKey: certidoesPartesKey(clienteId, atendimentoId),
        commit: (old: CertidoesPartesResponse | undefined, saved: ParteAtualizadaResponse) =>
          comParteSubstituida(old, saved.parte),
      },
    ],
    invalidate: leiturasDoResultado(clienteId),
    onSuccess: (r) =>
      toast.success(r.cancelados === 1 ? "Emissão cancelada." : `${r.cancelados} emissões canceladas.`),
    onError: (e) => toast.error("Não foi possível cancelar a emissão", { description: erroMsg(e) }),
  });
}

/** "Reemitir com erro": retry ONLY the party's failed automatic cells, in place
 *  (same consulta, `erro` -> `pendente`) — a cell that succeeded is never bought twice. */
export function useReemitirComErro(clienteId: string, atendimentoId?: string | null) {
  return useCacheWriteMutation<ParteAtualizadaResponse, { kind: "pessoa" | "empresa"; alvoId: string }>({
    mutationFn: ({ kind, alvoId }) =>
      api.post<ParteAtualizadaResponse>(
        `${clienteBase(clienteId)}/certidoes/partes/${kind}/${encodeURIComponent(alvoId)}/reemitir-erros`,
        { atendimento_id: atendimentoId ?? null },
      ),
    targets: [
      {
        queryKey: certidoesPartesKey(clienteId, atendimentoId),
        commit: (old: CertidoesPartesResponse | undefined, saved: ParteAtualizadaResponse) =>
          comParteSubstituida(old, saved.parte),
      },
    ],
    invalidate: leiturasDoResultado(clienteId),
    onSuccess: (r) =>
      r.reemitidos
        ? toast.success(r.reemitidos === 1 ? "Reemitindo 1 certidão com erro…" : `Reemitindo ${r.reemitidos} certidões com erro…`)
        : toast.info("Nenhuma certidão com erro para reemitir."),
    onError: (e) => toast.error("Erro ao reemitir certidões", { description: erroMsg(e) }),
  });
}

/** "Descartar emissão": throw away a wrong emission (soft-delete, restorable) so
 *  the cell's previous evidence — or an empty cell — wins again. */
export function useDescartarEmissao(clienteId: string, atendimentoId?: string | null) {
  return useCacheWriteMutation<ParteAtualizadaResponse, string>({
    mutationFn: (resultadoId) =>
      api.delete<ParteAtualizadaResponse>(
        `${clienteBase(clienteId)}/certidoes/resultados/${encodeURIComponent(resultadoId)}`,
      ),
    targets: [
      {
        queryKey: certidoesPartesKey(clienteId, atendimentoId),
        commit: (old: CertidoesPartesResponse | undefined, saved: ParteAtualizadaResponse) =>
          comParteSubstituida(old, saved.parte),
      },
    ],
    invalidate: leiturasDoResultado(clienteId),
    onSuccess: () => toast.success("Emissão descartada."),
    onError: (e) => toast.error("Não foi possível descartar a emissão", { description: erroMsg(e) }),
  });
}

/** "Baixar todas (.zip)": every PDF on the party's grid, one file. Raw fetch
 *  (binary), like the transcription PDF download. */
export function useBaixarZipDaParte(clienteId: string, atendimentoId?: string | null) {
  return useMutation({ // noc-allow: invalidate-only — a file download, writes nothing and caches nothing
    mutationFn: async ({ kind, alvoId, nome }: { kind: "pessoa" | "empresa"; alvoId: string; nome: string }) => {
      const qs = atendimentoId ? `?atendimento_id=${encodeURIComponent(atendimentoId)}` : "";
      const resp = await authenticatedFetch(
        apiUrl(`${clienteBase(clienteId)}/certidoes/partes/${kind}/${encodeURIComponent(alvoId)}/download-zip${qs}`),
      );
      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        throw new Error(body?.error?.message || body?.detail || "Erro ao baixar as certidões");
      }
      const disposition = resp.headers.get("Content-Disposition") || "";
      const match = /filename="?([^";]+)"?/.exec(disposition);
      triggerBlobDownload(await resp.blob(), match?.[1] || `certidoes_${nome.replace(/\s+/g, "_")}.zip`);
    },
    onError: (e) => toast.error("Não foi possível baixar as certidões", { description: erroMsg(e) }),
  });
}

/** `POST …/certidoes/resultados/{resultado_id}/reemitir` — one cell, body `{}`. */
export function useReemitirResultado(clienteId: string) {
  const invalidate = useInvalidatePartes(clienteId);
  return useMutation({ // noc-allow: invalidate-only — queues a re-emission; the cell changes via the polled partes read
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
  return useMutation({ // noc-allow: invalidate-only — the response is the acknowledgment, not the cell, and the contract readiness gate it flips is server-derived
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
  return useMutation({ // noc-allow: invalidate-only — schedules a background re-read; the response carries nothing to write, the polled read shows the result
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
  return useMutation({ // noc-allow: invalidate-only — schedules background re-reads, one call per cell; nothing in the responses is a cell
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
  return useMutation({ // noc-allow: invalidate-only — the PATCH re-derives the cell (lock, aviso, divergences) and contract readiness server-side; the response is not the cell
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
  return useMutation({ // noc-allow: invalidate-only — schedules background re-reads for the whole card; the response is counts only
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
  return useMutation({ // noc-allow: invalidate-only — the server reads the PDF asynchronously; the response is the ensured cell ids, not the filled cell
    mutationFn: async ({ kind, alvoId, linhaChave, file }: UploadCelulaInput) => {
      if (!tipoArquivoAceito(file, ["application/pdf"])) throw new Error("Apenas arquivos PDF são aceitos.");
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

/**
 * Type a cell by hand (owner 2026-10-21: whatever a document carries can be
 * typed). Ensure the cell's resultado through the EXISTING §1.4 ensure-cell
 * route when the cell has none yet (idempotent: an existing winner comes
 * back, never a second consulta), then `PATCH /api/certidoes/resultados/{id}`
 * — the same confirm route the "Detalhes" form uses, which stamps
 * `resultado_origem='manual'` and answers with the resultado row.
 *
 * The typed values are drawn in the grid at once (optimistic) and the
 * server's row replaces them on the answer — the row never keeps showing the
 * old value until a reload (KB § PATTERNS/frontend/mutation-cache-writes.md).
 */
export function useDigitarNaCelula(clienteId: string, atendimentoId?: string | null) {
  type Saida = { id: string; row: ResultadoServidor };
  return useCacheWriteMutation<Saida, DigitarCelulaInput>({
    mutationFn: async ({ kind, alvoId, linhaChave, resultadoId, patch }) => {
      let id = resultadoId;
      if (!id) {
        const cel = await api.post<CelulaEnsureResponse>(`${clienteBase(clienteId)}/certidoes/celulas`, {
          kind,
          alvo_id: alvoId,
          linha_chave: linhaChave,
          atendimento_id: atendimentoId ?? null,
        });
        id = cel.resultado_id;
      }
      const row = await api.patch<ResultadoServidor>(`/api/certidoes/resultados/${id}`, patch satisfies ResultadoPatchInput);
      return { id, row: { ...row, id } };
    },
    targets: (input) => [
      {
        queryKey: certidoesPartesKey(clienteId, atendimentoId),
        optimistic: (old: CertidoesPartesResponse | undefined) =>
          comCelulaEditada(old, input, (c) => celulaComResultado(c, linhaDigitada(input.patch, c))),
        commit: (old: CertidoesPartesResponse | undefined, saved: Saida) =>
          comCelulaEditada(old, input, (c) => celulaComResultado(c, saved.row)),
      },
    ],
    // The contract readiness and the per-party panels read the same resultado.
    invalidate: [
      ["sw", "clientes", clienteId, "contratos"],
      ["certidao-resultados-parte"],
      ["certidao-resultados-cliente"],
      ["certidao-resultados-empresa"],
    ],
    onSuccess: () => toast.success("Certidão salva."),
    onError: (e) => toast.error("Erro ao salvar certidão", { description: erroMsg(e) }),
  });
}

/**
 * "Voltar à leitura automática": `POST /api/certidoes/resultados/{id}/
 * voltar-automatico` releases a hand-edited cell — the server clears the
 * human's values + lock and re-runs the cell's automatic source (stored PDF,
 * Crednet for the serasa cell, registry response). The answer is the cell's
 * row (cleared and marked `processando` while a PDF re-reads, or already
 * refilled by the Crednet), written into the grid as it arrives.
 */
export function useVoltarAoAutomatico(clienteId: string, atendimentoId?: string | null) {
  return useCacheWriteMutation<ResultadoServidor, string>({
    mutationFn: (resultadoId) =>
      api.post<ResultadoServidor>(`/api/certidoes/resultados/${encodeURIComponent(resultadoId)}/voltar-automatico`, {}),
    targets: [
      {
        queryKey: certidoesPartesKey(clienteId, atendimentoId),
        commit: (old: CertidoesPartesResponse | undefined, saved: ResultadoServidor) =>
          comCelulaDoResultado(old, saved.id, (c) => celulaComResultado(c, saved)),
      },
    ],
    invalidate: [
      ["sw", "clientes", clienteId, "contratos"],
      ["certidao-resultados-parte"],
      ["certidao-resultados-cliente"],
      ["certidao-resultados-empresa"],
    ],
    onSuccess: () => toast.success("Voltou à leitura automática."),
    onError: (e) => toast.error("Não foi possível voltar à leitura automática", { description: erroMsg(e) }),
  });
}

/** Custom-row CRUD (§1.6, EXISTING routes) — invalidates THIS tab's key. */
export function useCriarLinhaPartes(clienteId: string) {
  const invalidate = useInvalidatePartes(clienteId);
  return useMutation({ // noc-allow: invalidate-only — a new custom row adds a cell to every party in the server-built matrix; the response is only the row
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
  return useMutation({ // noc-allow: invalidate-only — the custom row label is rendered inside the server-built matrix; the response is only the row
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
  return useMutation({ // noc-allow: invalidate-only — removing a custom row drops its cells from every party in the server-built matrix
    mutationFn: (linhaId: string) =>
      api.delete(`${clienteBase(clienteId)}/certidoes/matriz/linhas/${linhaId}`),
    onSuccess: () => void invalidate(),
    onError: (e) => toast.error("Erro ao remover certidão", { description: erroMsg(e) }),
  });
}

export { useInvalidatePartes };

// ─── Antigos proprietários ────────────────────────────────────────────────────

export const antigosKey = (clienteId: string, atendimentoId?: string | null) =>
  ["sw", "clientes", clienteId, "certidoes", "antigos-proprietarios", atendimentoId ?? null] as const;

/** Mutations here change the rows (partes) AND the header (antigos): refetch both. */
function useInvalidatePartesEAntigos(clienteId: string) {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId, "certidoes", "partes"] }),
      qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId, "certidoes", "antigos-proprietarios"] }),
      qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId, "contratos"] }),
    ]);
}

/** `api.delete` takes a body, not params — the optional atendimento rides the query string. */
const atQuery = (atendimentoId?: string | null) =>
  atendimentoId ? `?atendimento_id=${encodeURIComponent(atendimentoId)}` : "";

/** `GET …/certidoes/antigos-proprietarios` — header state (§2). */
export function useAntigosProprietarios(clienteId: string | null, atendimentoId?: string | null) {
  return useQuery({
    queryKey: antigosKey(clienteId ?? "__none__", atendimentoId),
    queryFn: () =>
      api.get<AntigosEstado>(`${clienteBase(clienteId as string)}/certidoes/antigos-proprietarios`, {
        ...(atendimentoId ? { atendimento_id: atendimentoId } : {}),
      }),
    enabled: !!clienteId,
    placeholderData: (prev) => prev,
  });
}

/** `POST …/sincronizar` (§3) — idempotent backstop, fired when the subtab opens. */
export function useSincronizarAntigos(clienteId: string, atendimentoId?: string | null) {
  const invalidate = useInvalidatePartesEAntigos(clienteId);
  return useMutation({ // noc-allow: invalidate-only — syncs antigos owners from the matrícula and adds party rows server-side; the response is a created list, not the partes
    mutationFn: () =>
      api.post<AntigosSincronizacao>(
        `${clienteBase(clienteId)}/certidoes/antigos-proprietarios/sincronizar`,
        { atendimento_id: atendimentoId ?? null },
      ),
    onSuccess: (r) => {
      if (r.criados.length > 0) toast.success(`${r.criados.length} antigo(s) proprietário(s) adicionado(s) da matrícula.`);
      void invalidate();
    },
    // Not a toast only: the subtab also renders `sincronizar.error` inline.
    onError: (e) => toast.error("Não foi possível sincronizar com a matrícula", { description: erroMsg(e) }),
  });
}

/** `POST …/antigos-proprietarios` (§4) — manual add. */
export function useAdicionarAntigo(clienteId: string, atendimentoId?: string | null) {
  const invalidate = useInvalidatePartesEAntigos(clienteId);
  return useMutation({ // noc-allow: invalidate-only — adds an antigo party (new row + cells in the server-built matrix); the response does not carry the partes
    mutationFn: (input: AntigoCriarInput) =>
      api.post<AntigoCriarResponse>(`${clienteBase(clienteId)}/certidoes/antigos-proprietarios`, {
        ...input,
        atendimento_id: atendimentoId ?? null,
      }),
    onSuccess: () => {
      toast.success("Antigo proprietário adicionado.");
      void invalidate();
    },
    onError: (e) => toast.error("Não foi possível adicionar", { description: erroMsg(e) }),
  });
}

/** `DELETE …/antigos-proprietarios/{parte_id}` (§4) — antigo rows only. */
export function useRemoverAntigo(clienteId: string, atendimentoId?: string | null) {
  const invalidate = useInvalidatePartesEAntigos(clienteId);
  return useMutation({ // noc-allow: invalidate-only — drops an antigo party and its cells from the server-built matrix, and the header counts
    mutationFn: (parteId: string) =>
      api.delete<void>(
        `${clienteBase(clienteId)}/certidoes/antigos-proprietarios/${encodeURIComponent(parteId)}${atQuery(atendimentoId)}`,
      ),
    onSuccess: () => {
      toast.success("Antigo proprietário removido.");
      void invalidate();
    },
    onError: (e) => toast.error("Não foi possível remover", { description: erroMsg(e) }),
  });
}

/** `PUT|DELETE …/antigos-proprietarios/dispensa` (§5) — admin only. A 403 is
 *  NOT toasted here: the caller renders it inline as "sem permissão". */
export function useDispensaAntigos(clienteId: string, atendimentoId?: string | null) {
  const base = `${clienteBase(clienteId)}/certidoes/antigos-proprietarios/dispensa`;
  return useCacheWriteMutation<AntigosEstado, { motivo: string } | null>({
    mutationFn: (input) =>
      input
        ? api.put<AntigosEstado>(base, { motivo: input.motivo, atendimento_id: atendimentoId ?? null })
        : api.delete<AntigosEstado>(`${base}${atQuery(atendimentoId)}`),
    // Both verbs answer with the new header state: it is the cache entry.
    targets: [{ queryKey: antigosKey(clienteId, atendimentoId), commit: (_old, saved) => saved }],
    // The rows and the contract readiness move with the dispensa.
    invalidate: [
      ["sw", "clientes", clienteId, "certidoes", "partes"],
      ["sw", "clientes", clienteId, "contratos"],
    ],
    onSuccess: (_r, input) => {
      toast.success(input ? "Antigos proprietários dispensados neste negócio." : "Exigência reativada.");
    },
  });
}

/** `PUT …/certidoes/exigencias` — the deal's opt-in switches for the optional
 *  certidões (owner 2026-10-21). Turning the antigos switch ON also runs the
 *  matrícula sync, so the group (and its automatic emissions) appears at once. */
export function useDefinirExigencias(clienteId: string, atendimentoId?: string | null) {
  const sincronizar = useSincronizarAntigos(clienteId, atendimentoId);
  type Resposta = { atendimento_id: string; exigencias: ExigenciasCertidoes };
  const comExigencias = (old: CertidoesPartesResponse | undefined, e: Partial<ExigenciasCertidoes>) =>
    old && {
      ...old,
      exigencias: { exigir_certidoes_antigos: false, exigir_crf_fgts: false, ...old.exigencias, ...e },
    };
  return useCacheWriteMutation<Resposta, Partial<ExigenciasCertidoes>>({
    mutationFn: (input) =>
      api.put<Resposta>(`${clienteBase(clienteId)}/certidoes/exigencias`, {
        ...input,
        atendimento_id: atendimentoId ?? null,
      }),
    // The switches are predictable from the input: draw them on the click, then take the server's.
    targets: (input) => [
      {
        queryKey: certidoesPartesKey(clienteId, atendimentoId),
        optimistic: (old: CertidoesPartesResponse | undefined) => comExigencias(old, input),
        commit: (old: CertidoesPartesResponse | undefined, saved) => comExigencias(old, saved.exigencias),
      },
      {
        queryKey: antigosKey(clienteId, atendimentoId),
        optimistic: (old: AntigosEstado | undefined) =>
          old && input.exigir_certidoes_antigos !== undefined ? { ...old, exigencia_ativa: input.exigir_certidoes_antigos } : old,
      },
    ],
    // Turning a switch on adds rows (antigos group, CRF) the server builds.
    invalidate: [
      ["sw", "clientes", clienteId, "certidoes", "partes"],
      ["sw", "clientes", clienteId, "certidoes", "antigos-proprietarios"],
      ["sw", "clientes", clienteId, "contratos"],
    ],
    onSuccess: (_r, input) => {
      if (input.exigir_certidoes_antigos) sincronizar.mutate();
    },
    onError: (e) => toast.error("Não foi possível salvar a exigência", { description: erroMsg(e) }),
  });
}
