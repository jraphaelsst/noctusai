/**
 * `<TestemunhasSelectContainer/>` — data for `<TestemunhasSelect/>`.
 *
 * Same split as `GeradorContratoContainer`: everything under `card/**` is
 * presentational and this file owns the two queries (`useContratoTestemunhas`
 * for the current selection, `useTestemunhas` — the SAME registry hook the
 * Settings page and `EnviarAssinaturaDialog`'s prefill already call, no
 * second fetch path) and the save mutation.
 *
 * 🔴 AUTO-SAVES ONLY WHEN EVERY CHOSEN SLOT IS FILLED. `testemunha_ids` is a
 * list of ids, not a list of nullable slots — picking "quantidade = 3" and
 * filling only 2 of them is a mid-edit state the server has no shape for, so
 * the PUT waits until every slot the operator asked for has a witness (or
 * the operator drops the count back down). `quantidade = 0` saves
 * immediately (an explicit "no witnesses" is a valid, complete state).
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { TestemunhasSelect } from "@/components/card/TestemunhasSelect";
import {
  useContratoTestemunhas,
  useDefinirContratoTestemunhas,
} from "@/hooks/useContratoTestemunhas";
import { useTestemunhas } from "@/hooks/useTestemunhas";

export interface TestemunhasSelectContainerProps {
  clienteId: string;
  contratoId: string;
  /** Whether the collapsible is open — same lazy-fetch gate
   *  `GeradorContratoContainer`'s `aberto` takes. */
  aberto: boolean;
}

export function TestemunhasSelectContainer({
  clienteId,
  contratoId,
  aberto,
}: TestemunhasSelectContainerProps) {
  const selecaoQuery = useContratoTestemunhas(clienteId, aberto ? contratoId : null);
  const registroQuery = useTestemunhas();
  const definir = useDefinirContratoTestemunhas(clienteId, contratoId);

  const [ids, setIds] = useState<(string | null)[] | null>(null);
  // Seeds local state from the server once per contract — mirrors
  // `EnviarAssinaturaDialog`'s "seed once, never re-seed on background
  // refetch" discipline so a save-in-flight is never clobbered mid-edit.
  const [seeded, setSeeded] = useState<string | null>(null);

  useEffect(() => {
    if (selecaoQuery.data && seeded !== contratoId) {
      setIds(selecaoQuery.data.items.map((item) => item.testemunha.id));
      setSeeded(contratoId);
    }
  }, [selecaoQuery.data, seeded, contratoId]);

  const registro = registroQuery.data?.items ?? [];
  const selecionados = ids ?? [];

  function salvar(proximos: (string | null)[]) {
    setIds(proximos);
    if (proximos.length === 0) {
      definir.mutate([], { onError: () => toast.error("Não foi possível salvar as testemunhas.") });
      return;
    }
    if (proximos.every((v): v is string => !!v)) {
      definir.mutate(proximos, {
        onError: () => toast.error("Não foi possível salvar as testemunhas."),
      });
    }
  }

  function mudarQuantidade(quantidade: number) {
    const atual = selecionados;
    const proximos =
      quantidade <= atual.length
        ? atual.slice(0, quantidade)
        : [...atual, ...Array(quantidade - atual.length).fill(null)];
    salvar(proximos);
  }

  function mudarSlot(indice: number, testemunhaId: string) {
    const proximos = selecionados.map((v, i) => (i === indice ? testemunhaId : v));
    salvar(proximos);
  }

  if (!aberto) return null;

  return (
    <TestemunhasSelect
      registro={registro}
      selecionados={selecionados}
      onChangeQuantidade={mudarQuantidade}
      onChangeSlot={mudarSlot}
      salvando={definir.isPending}
    />
  );
}
