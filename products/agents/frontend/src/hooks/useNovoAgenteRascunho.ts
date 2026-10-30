/**
 * The new-agent wizard's draft: answers + start mode + current step, kept in THIS browser (localStorage) until
 * "Publicar". Nothing reaches the server before that, so the page must say the draft is unsaved (KB server-state
 * family, "a draft says it is unsaved"): `dirty` compares the answers with the model's starting values through the
 * seed `useUnsavedChanges`, and `guardado` says whether the browser actually kept the copy.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useUnsavedChanges } from "@noctusai/lib";
import type { PassoAssistente } from "@/api/agentes/types";
import {
  apagarRascunho,
  gravarRascunho,
  lerRascunho,
  valoresIniciais,
  type ModoInicio,
  type ValorCampo,
  type Valores,
} from "@/lib/assistente";

export interface NovoAgenteRascunho {
  modo: ModoInicio;
  valores: Valores;
  passo: string | null;
  chaveTocada: boolean;
  /** Restored from an earlier visit (the page offers to discard it). */
  restaurado: boolean;
  /** The answers differ from the starting values: something is on screen the server does not have. */
  dirty: boolean;
  /** false when the browser refused to keep the local copy (private mode / quota). */
  guardado: boolean;
  salvoEm: string | null;
  setModo: (m: ModoInicio) => void;
  setValor: (campo: string, v: ValorCampo) => void;
  setPasso: (id: string) => void;
  setChaveTocada: (v: boolean) => void;
  descartar: () => void;
  /** After a successful publish: the draft is now the server's. */
  concluir: () => void;
}

/** `passos` undefined while the model loads: the hook holds the restored draft and seeds defaults once it arrives. */
export function useNovoAgenteRascunho(passos: PassoAssistente[] | undefined): NovoAgenteRascunho {
  const [inicial] = useState(() => lerRascunho());
  const [modo, setModo] = useState<ModoInicio>(inicial?.modo ?? "vazio");
  const [valores, setValores] = useState<Valores>(inicial?.valores ?? {});
  const [passo, setPasso] = useState<string | null>(inicial?.passo ?? null);
  const [chaveTocada, setChaveTocada] = useState(inicial?.chaveTocada ?? false);
  const [restaurado, setRestaurado] = useState(inicial !== null);
  const [guardado, setGuardado] = useState(true);
  const [salvoEm, setSalvoEm] = useState<string | null>(inicial?.salvoEm ?? null);
  const concluido = useRef(false);

  const base = useMemo(() => (passos ? valoresIniciais(passos) : undefined), [passos]);
  // Defaults fill only the fields the draft does not already answer.
  useEffect(() => {
    if (base) setValores((v) => ({ ...base, ...v }));
  }, [base]);

  // Local copy, never a server write: the unsaved state stays visible until "Publicar".
  const { dirty } = useUnsavedChanges(valores, base, { guardNavigation: false });

  useEffect(() => {
    if (concluido.current || !base) return;
    if (!dirty) {
      apagarRascunho();
      setSalvoEm(null);
      return;
    }
    const agora = new Date().toISOString();
    setGuardado(gravarRascunho({ modo, valores, passo, chaveTocada, salvoEm: agora }));
    setSalvoEm(agora);
  }, [modo, valores, passo, chaveTocada, dirty, base]);

  const setValor = useCallback((campo: string, v: ValorCampo) => setValores((old) => ({ ...old, [campo]: v })), []);

  const descartar = useCallback(() => {
    apagarRascunho();
    setValores(base ?? {});
    setModo("vazio");
    setPasso(null);
    setChaveTocada(false);
    setRestaurado(false);
    setSalvoEm(null);
  }, [base]);

  const concluir = useCallback(() => {
    concluido.current = true;
    apagarRascunho();
  }, []);

  return {
    modo, valores, passo, chaveTocada, restaurado, dirty, guardado, salvoEm,
    setModo, setValor, setPasso, setChaveTocada, descartar, concluir,
  };
}
