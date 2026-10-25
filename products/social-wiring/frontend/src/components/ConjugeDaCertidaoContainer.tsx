/**
 * Container of `<ConjugeDaCertidao/>`: owns the add mutation and the 409
 * "same person already in the org" choice. `clienteId` is the CARD's cliente
 * (the route anchor); the suggestion names its own principal and lado.
 */
import { useState } from "react";

import { ConjugeDaCertidao } from "@/components/card/ConjugeDaCertidao";
import { useAdicionarConjugeDaCertidao } from "@/hooks/usePartes";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { ConjugeCandidato, ConjugeSugerido } from "@/types/partes";

function candidatosDoErro(err: unknown): ConjugeCandidato[] {
  const lista = (err as { body?: { error?: { details?: { candidatos?: unknown } } } } | null)?.body
    ?.error?.details?.candidatos;
  return Array.isArray(lista) ? (lista as ConjugeCandidato[]) : [];
}

export function ConjugeDaCertidaoContainer({
  clienteId,
  sugestao,
  atendimentoId,
}: {
  clienteId: string;
  sugestao: ConjugeSugerido;
  atendimentoId?: string | null;
}) {
  const adicionar = useAdicionarConjugeDaCertidao(clienteId);
  const [candidatos, setCandidatos] = useState<ConjugeCandidato[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  function enviar(s: ConjugeSugerido, extra: { cliente_id?: string; criar_novo?: boolean } = {}) {
    setErro(null);
    adicionar.mutate(
      {
        documento_id: s.documento_id,
        lado: s.lado,
        ...(atendimentoId ? { atendimento_id: atendimentoId } : {}),
        ...extra,
      },
      {
        onSuccess: () => setCandidatos([]),
        onError: (err) => {
          // A refusal is always shown: the choice when it is the match 409, else the server's sentence.
          setCandidatos(candidatosDoErro(err));
          setErro(mensagemErroServidor(err, "Não foi possível adicionar o cônjuge."));
        },
      },
    );
  }

  return (
    <ConjugeDaCertidao
      sugestao={sugestao}
      candidatos={candidatos}
      pending={adicionar.isPending}
      erro={erro}
      onAdicionar={(s) => enviar(s)}
      onVincular={(s, id) => enviar(s, { cliente_id: id })}
      onCriarNovo={(s) => enviar(s, { criar_novo: true })}
    />
  );
}
