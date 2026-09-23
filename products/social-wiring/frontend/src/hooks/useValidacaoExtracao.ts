/**
 * useValidacaoExtracao — the human validation gate over machine-extracted
 * contract data (owner decision D2, backend migration 156,
 * `contrato_gerador/validacao_extracao.py`).
 *
 * Before a contract is generated, every contract-feeding value a MACHINE
 * extracted (a document read, the certidões API, the matrícula reader) and
 * no human has vouched for yet must be accepted or rejected. The backend
 * refuses `POST .../gerar` with 409 `EXTRACAO_PENDENTE_VALIDACAO` while any
 * is pending — this hook is the UI half, not the gate.
 *
 * Contract (backend is the source of truth):
 * - `GET  /api/clientes/{cliente}/contratos/{contrato}/validacao-extracao`
 *   → `{ pendentes: PendenteValidacao[], conflitos: ConflitoExtracao[] }`
 *   — `conflitos` are OPEN extraction conflicts (a later reading disagreed
 *   with a set value); read-only here, decided on the screen `link` names.
 *   Both block generation.
 * - `POST .../validacao-extracao/decisoes` body `{ decisoes: [{chave, decisao}] }`
 *   → `{ aplicadas, pendentes, conflitos }` (what STILL blocks); 409
 *   `EXTRACAO_VALIDACAO_DESATUALIZADA` when a `chave` is no longer pending
 *   (nothing written — refetch and retry).
 * - A REJECTED required value is typed back through the EXISTING manual
 *   route the item names in `edicao` (`PATCH /api/clientes/{id}` or
 *   `PATCH /api/imoveis/{codigo}/dados`), which stamps `origem='manual'`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@noctusai/lib";
import { api } from "@noctusai/seed/infra";

export type EntidadeValidacao =
  | "cliente"
  | "imovel"
  | "imovel_documento"
  | "certidao"
  | "ato_detalhe";

export type Decisao = "aceito" | "rejeitado";

/** The manual route a rejected value is typed back through. `null` = no
 *  single-input route (a multi-column group or an enumerated field) — the
 *  operator corrects it on the card instead. */
export interface EdicaoManual {
  rota: string;
  campo: string;
  tipo: "texto" | "data";
}

export interface PendenteValidacao {
  /** `entidade:entidade_id:campo` — the decision key. */
  chave: string;
  entidade: EntidadeValidacao;
  entidade_id: string;
  campo: string;
  /** Who/what the value belongs to, e.g. "Fulano (proprietario)". */
  grupo: string;
  rotulo: string;
  valor: string | null;
  /** The machine source — a document tipo, `api`, `ia`, `sugestao`, … */
  origem: string;
  fonte_documento_id: string | null;
  fonte_nome: string | null;
  confianca: string | null;
  obrigatorio: boolean;
  edicao: EdicaoManual | null;
}

/** An open extraction conflict on contract data — read-only in the modal. */
export interface ConflitoExtracao {
  id: string;
  entidade: "cliente" | "imovel";
  entidade_id: string;
  campo: string;
  grupo: string;
  rotulo: string;
  valor_atual: string | null;
  valor_proposto: string | null;
  origem_proposto: string | null;
  link: { rota: string; rotulo: string };
}

/** Everything that blocks generation — the GET answer. */
export interface SituacaoValidacao {
  pendentes: PendenteValidacao[];
  conflitos: ConflitoExtracao[];
}

export interface DecisaoInput {
  chave: string;
  decisao: Decisao;
}

export interface DecidirResult extends SituacaoValidacao {
  aplicadas: number;
}

/** The 409 `EXTRACAO_PENDENTE_VALIDACAO` code `POST .../gerar` answers while
 *  anything is pending — the container opens the modal on it. */
export const CODIGO_PENDENTE_VALIDACAO = "EXTRACAO_PENDENTE_VALIDACAO";
export const CODIGO_VALIDACAO_DESATUALIZADA = "EXTRACAO_VALIDACAO_DESATUALIZADA";

export const VALIDACAO_KEY = (clienteId: string, contratoId: string) =>
  ["sw", "clientes", clienteId, "contratos", contratoId, "validacao-extracao"] as const;

const url = (clienteId: string, contratoId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/contratos/${encodeURIComponent(
    contratoId,
  )}/validacao-extracao`;

export async function fetchValidacaoExtracao(
  clienteId: string,
  contratoId: string,
): Promise<SituacaoValidacao> {
  const res = await api.get<Partial<SituacaoValidacao>>(url(clienteId, contratoId));
  return { pendentes: res?.pendentes ?? [], conflitos: res?.conflitos ?? [] };
}

/** `enabled` is the modal's open state — nothing is fetched until the
 *  operator actually asks to generate. */
export function useValidacaoExtracao(clienteId: string, contratoId: string, enabled: boolean) {
  return useQuery({
    queryKey: VALIDACAO_KEY(clienteId, contratoId),
    queryFn: () => fetchValidacaoExtracao(clienteId, contratoId),
    enabled,
  });
}

/** The typed code of a seed `ApiError` (or `null`) — so callers branch on
 *  `EXTRACAO_*` without re-parsing the envelope. */
export function codigoDoErro(err: unknown): string | null {
  return err instanceof ApiError ? err.code ?? null : null;
}

export function useValidacaoExtracaoMutations(clienteId: string, contratoId: string) {
  const qc = useQueryClient();
  const key = VALIDACAO_KEY(clienteId, contratoId);

  /** The pre-check the "Gerar versão" click runs: a fresh read (never a
   *  cached answer — the gate is the backend's, and a stale empty list would
   *  only buy a 409). Seeds the query the dialog then renders. */
  const verificar = useMutation({
    mutationFn: () => fetchValidacaoExtracao(clienteId, contratoId),
    onSuccess: (situacao) => {
      qc.setQueryData(key, situacao);
    },
  });

  const decidir = useMutation({
    mutationFn: (decisoes: DecisaoInput[]) =>
      api.post<DecidirResult>(`${url(clienteId, contratoId)}/decisoes`, {
        decisoes,
      }),
    onSuccess: (res) => {
      qc.setQueryData<SituacaoValidacao>(key, {
        pendentes: res.pendentes,
        conflitos: res.conflitos,
      });
    },
    onError: (err) => {
      // Stale list (decided elsewhere / re-extracted) — show the current one.
      if (codigoDoErro(err) === CODIGO_VALIDACAO_DESATUALIZADA) {
        void qc.invalidateQueries({ queryKey: key });
      }
    },
  });

  const salvarManual = useMutation({
    mutationFn: ({ edicao, valor }: { edicao: EdicaoManual; valor: string }) =>
      api.patch<unknown>(edicao.rota, { [edicao.campo]: valor }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: key });
    },
  });

  return { verificar, decidir, salvarManual };
}
