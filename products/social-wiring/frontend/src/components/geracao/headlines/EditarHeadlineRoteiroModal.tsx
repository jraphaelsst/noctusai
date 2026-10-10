/**
 * "Editar Headline e Roteiro" (Favoritas / Sugeridas, page-map-v2 §18/§19):
 * the shared EditarHeadlineModal + the linked roteiro's edit state from FE-3
 * (`useRoteiro` + `useEdicaoRoteiro`). No second modal body.
 */
import { useRoteiro } from "@/hooks/geracao/useRoteiros";
import type { Headline } from "@/types/geracao";
import { useEdicaoRoteiro } from "../roteiro/RoteiroEdicao";
import { EditarHeadlineModal } from "./EditarHeadlineModal";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  headline: Headline | null;
}

export function EditarHeadlineRoteiroModal({ open, onOpenChange, headline }: Props) {
  const roteiroId = open ? (headline?.roteiro_id ?? null) : null;
  const q = useRoteiro(roteiroId);
  const pronto = q.data?.status === "completo" ? q.data : undefined;
  const edicao = useEdicaoRoteiro(pronto);

  return (
    <EditarHeadlineModal
      open={open}
      onOpenChange={onOpenChange}
      headline={headline}
      roteiroBloco={
        headline?.roteiro_id
          ? { roteiro: pronto, carregando: q.showSkeleton, edicao, onRecarregar: () => void q.refetch() }
          : undefined
      }
    />
  );
}
