/**
 * useRoteiroRascunho — the AUTOSAVE engine behind the roteiro editor
 * (roteiro-ciclo CONTRACT §5; mockup `02-roteiro-ciclo-de-vida`).
 *
 * Owner decision (2026-11-09): every edit to a roteiro saves; "rascunho" is
 * automatic, and leaving and coming back loses nothing until it is generated.
 *
 *  - The draft is CREATED (R2) on the first meaningful edit: the first imóvel
 *    or the date. A title alone never creates one.
 *  - Text fields (título / data / horário) go out debounced (~800 ms, R3);
 *    adding, removing and reordering imóveis go out immediately (R6 / R7 / R5).
 *  - ONE serial queue: a second edit made while the create is still in flight
 *    runs after it, against the id the create returned — never a second draft.
 *  - The editor's visitas are DERIVED from the cached roteiro (written by
 *    `useRoteiroMutations` from every answer); nothing is copied into state.
 *
 * 🔴 A DRAFT ALWAYS SAYS WHETHER IT IS SAVED (`server-state-family-index.md`):
 * `salvando` while a write is in flight or debounced, `erro` (with the
 * server's own sentence) after a failure — the input is KEPT and the failed
 * writes are retried in order by `tentarDeNovo`. A failure is never silent.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useRoteiroMutations, useRoteiros } from "@/hooks/useCardHub";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { ImovelVisita, Roteiro } from "@/types/cardHub";

/** The debounce for text fields (CONTRACT §5: "about 800 ms"). */
export const AUTOSAVE_DEBOUNCE_MS = 800;

export type EstadoSalvamento =
  /** Nothing in flight, nothing failed. `em` is the last successful write (`null` = none yet). */
  | { tipo: "salvo"; em: number | null }
  | { tipo: "salvando" }
  | { tipo: "erro"; mensagem: string };

export interface CamposRoteiro {
  titulo: string;
  /** `YYYY-MM-DD` or "" */
  data: string;
  /** `HH:MM` or "" */
  hora: string;
}

export interface UseRoteiroRascunhoArgs {
  clienteId: string;
  /** Reopen an existing draft. Absent ⇒ a new one, created on the first meaningful edit. */
  roteiroId?: string | null;
  /** More than one open atendimento ⇒ the caller must resolve which (else 409 `AmbiguousAtendimento`). */
  atendimentoId?: string | null;
  /** `false` while the atendimento is still unresolved: nothing can be created yet. */
  podeCriar?: boolean;
  /** The imóveis the draft is opened with (interest list): created at once, in this order. */
  inicial?: ImovelVisita[];
}

const hhmm = (h: string | null | undefined) => (h ? h.slice(0, 5) : "");

export function useRoteiroRascunho({
  clienteId,
  roteiroId: roteiroIdInicial = null,
  atendimentoId,
  podeCriar = true,
  inicial,
}: UseRoteiroRascunhoArgs) {
  const lista = useRoteiros(clienteId);
  const mut = useRoteiroMutations(clienteId);

  const [roteiroId, setRoteiroId] = useState<string | null>(roteiroIdInicial);
  const idRef = useRef<string | null>(roteiroIdInicial);

  const existente = useMemo(
    () => (roteiroIdInicial ? lista.data?.find((r) => r.id === roteiroIdInicial) : undefined),
    [lista.data, roteiroIdInicial],
  );
  const camposDe = (r: Roteiro | undefined): CamposRoteiro => ({
    titulo: r?.titulo ?? "",
    data: r?.data_visita ?? "",
    hora: hhmm(r?.hora_visita),
  });
  const [campos, setCampos] = useState<CamposRoteiro>(() => camposDe(existente));
  const camposRef = useRef(campos);
  // 🔴 A draft being REOPENED hydrates its fields from the server's row the moment
  // that row is known — and only then are the inputs shown (`carregando`). Editing
  // fields that were never loaded would PATCH their empty defaults over real data.
  const [hidratado, setHidratado] = useState(!roteiroIdInicial || !!existente);
  if (!hidratado && existente) {
    const doServidor = camposDe(existente);
    camposRef.current = doServidor;
    setCampos(doServidor);
    setHidratado(true);
  }

  // A draft being REOPENED is saved already: its last save is the server's `updated_at`.
  const [estado, setEstado] = useState<EstadoSalvamento>({
    tipo: "salvo",
    em: existente?.updated_at ? Date.parse(existente.updated_at) : null,
  });
  /** Writes in flight + debounced ones not yet sent. */
  const pendentes = useRef(0);
  const falhas = useRef<Array<{ descricao: string; op: () => Promise<unknown> }>>([]);
  const fila = useRef<Promise<void>>(Promise.resolve());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [anuncio, setAnuncio] = useState("");

  // The roteiro as the server last answered it — the ONE source for visitas + permissoes.
  const roteiro: Roteiro | undefined = useMemo(
    () => (roteiroId ? lista.data?.find((r) => r.id === roteiroId) : undefined),
    [lista.data, roteiroId],
  );

  const atendimentoRef = useRef(atendimentoId);
  atendimentoRef.current = atendimentoId;
  const podeCriarRef = useRef(podeCriar);
  podeCriarRef.current = podeCriar;

  /** Run `op` after every earlier write; track saved / saving / error. */
  const executar = useCallback((descricao: string, op: () => Promise<unknown>) => {
    pendentes.current += 1;
    setEstado({ tipo: "salvando" });
    const rodar = async () => {
      try {
        await op();
        pendentes.current -= 1;
        if (pendentes.current === 0 && falhas.current.length === 0) {
          setEstado({ tipo: "salvo", em: Date.now() });
        }
      } catch (err) {
        pendentes.current -= 1;
        falhas.current.push({ descricao, op });
        setEstado({
          tipo: "erro",
          mensagem: mensagemErroServidor(err, "Não foi possível salvar a alteração."),
        });
      }
    };
    fila.current = fila.current.then(rodar);
    return fila.current;
  }, []);

  /** The create write — used by the first imóvel, the initial set and the first text edit. */
  const criar = useCallback(
    async (imoveis: string[]) => {
      const c = camposRef.current;
      const saved = await mut.create.mutateAsync({
        titulo: c.titulo.trim() || null,
        data_visita: c.data || null,
        hora_visita: c.hora || null,
        ...(atendimentoRef.current ? { atendimento_id: atendimentoRef.current } : {}),
        ...(imoveis.length ? { imoveis } : {}),
      });
      idRef.current = saved.id;
      setRoteiroId(saved.id);
      return saved;
    },
    [mut.create],
  );

  /** Send the three text fields (R3), or create the draft when they are meaningful on their own. */
  const salvarCampos = useCallback(() => {
    timer.current = null;
    pendentes.current -= 1; // the debounced write is leaving the "waiting" state
    const c = camposRef.current;
    const id = idRef.current;
    if (!id) {
      // Only the DATE makes a draft worth keeping on its own; a title alone waits.
      if (!c.data || !podeCriarRef.current) {
        if (pendentes.current === 0 && falhas.current.length === 0) {
          setEstado({ tipo: "salvo", em: null });
        }
        return;
      }
      void executar("os dados do roteiro", () => criar([]));
      return;
    }
    void executar("os dados do roteiro", () =>
      mut.update.mutateAsync({
        id,
        body: {
          titulo: c.titulo.trim() || null,
          data_visita: c.data || null,
          hora_visita: c.hora || null,
        },
      }),
    );
  }, [criar, executar, mut.update]);

  /** Edit one text field: the input changes at once, the save follows the debounce. */
  const editarCampo = useCallback(
    <K extends keyof CamposRoteiro>(campo: K, valor: CamposRoteiro[K]) => {
      const proximo = { ...camposRef.current, [campo]: valor };
      camposRef.current = proximo;
      setCampos(proximo);
      if (timer.current) clearTimeout(timer.current);
      else pendentes.current += 1; // the debounced write counts as pending
      setEstado((e) => (e.tipo === "erro" ? e : { tipo: "salvando" }));
      timer.current = setTimeout(salvarCampos, AUTOSAVE_DEBOUNCE_MS);
    },
    [salvarCampos],
  );

  /** Send a pending debounced edit NOW and wait for every write to settle. */
  const aguardar = useCallback(async () => {
    if (timer.current) {
      clearTimeout(timer.current);
      salvarCampos();
    }
    await fila.current;
  }, [salvarCampos]);

  const adicionar = useCallback(
    (codigo: string) => {
      if (!idRef.current && !podeCriarRef.current) return;
      void executar(`o imóvel ${codigo}`, async () => {
        const id = idRef.current;
        if (!id) await criar([codigo]);
        else await mut.addVisita.mutateAsync({ roteiroId: id, codigo });
      });
    },
    [criar, executar, mut.addVisita],
  );

  const remover = useCallback(
    (visitaId: string, codigo: string) => {
      void executar(`a remoção de ${codigo}`, async () => {
        const id = idRef.current;
        if (!id) return;
        await mut.removeVisita.mutateAsync({ roteiroId: id, visitaId });
      });
    },
    [executar, mut.removeVisita],
  );

  /** ↑ (−1) / ↓ (+1): the new order goes out at once; the live region says where it landed. */
  const mover = useCallback(
    (visitaId: string, delta: -1 | 1) => {
      const visitas = roteiro?.visitas ?? [];
      const de = visitas.findIndex((v) => v.id === visitaId);
      const para = de + delta;
      if (de < 0 || para < 0 || para >= visitas.length) return;
      const ids = visitas.map((v) => v.id);
      [ids[de], ids[para]] = [ids[para], ids[de]];
      setAnuncio(`${visitas[de].codigo} agora é o ${para + 1}º.`);
      void executar(`a ordem dos imóveis`, async () => {
        const id = idRef.current;
        if (!id) return;
        await mut.reorder.mutateAsync({ id, visitaIds: ids });
      });
    },
    [executar, mut.reorder, roteiro],
  );

  /** Replay every failed write, in order. The input was never discarded. */
  const tentarDeNovo = useCallback(() => {
    const anteriores = falhas.current;
    falhas.current = [];
    if (anteriores.length === 0) return;
    setEstado({ tipo: "salvando" });
    for (const f of anteriores) void executar(f.descricao, f.op);
  }, [executar]);

  /** R8 — after every pending save has landed. Rejects with the server's error. */
  const gerar = useCallback(async (): Promise<Roteiro> => {
    await aguardar();
    const id = idRef.current;
    if (!id) throw new Error("Adicione ao menos um imóvel.");
    return mut.gerar.mutateAsync({ id });
  }, [aguardar, mut.gerar]);

  /** R4 on the draft being edited. */
  const excluir = useCallback(async () => {
    await aguardar();
    const id = idRef.current;
    if (!id) return;
    await mut.remove.mutateAsync(id);
    idRef.current = null;
    setRoteiroId(null);
  }, [aguardar, mut.remove]);

  // The initial set (interest list → "Gerar roteiro") is the first meaningful edit: create at once.
  const iniciou = useRef(false);
  useEffect(() => {
    if (iniciou.current || roteiroIdInicial || !inicial?.length || !podeCriar) return;
    iniciou.current = true;
    void executar("os imóveis do roteiro", () => criar(inicial.map((i) => i.codigo)));
  }, [inicial, podeCriar, roteiroIdInicial, executar, criar]);

  // A pending debounce must not fire into an unmounted editor with a stale closure.
  useEffect(
    () => () => {
      if (timer.current) {
        clearTimeout(timer.current);
        // Closing flushes: "Closing never loses a draft."
        salvarCampos();
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cleanup must see the latest refs only
    [],
  );

  return {
    roteiro,
    roteiroId,
    campos,
    editarCampo,
    estado,
    anuncio,
    adicionar,
    remover,
    mover,
    tentarDeNovo,
    aguardar,
    /** After `aguardar()`: did any write fail (and is it still unsaved)? */
    temFalha: () => falhas.current.length > 0,
    gerar,
    excluir,
    gerando: mut.gerar.isPending,
    /** The draft being reopened is not known yet: show a skeleton, never empty inputs. */
    carregando: !hidratado && !lista.isError && (lista.isPending || !lista.data),
    /** The list answered and the draft being reopened is not in it (deleted elsewhere). */
    naoEncontrado: !hidratado && !!lista.data && !existente,
    /** The list could not be loaded at all. */
    erroAoCarregar: !hidratado && lista.isError,
  };
}
