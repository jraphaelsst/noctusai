/**
 * `<GeradorContratoContainer/>` — data for `<GeradorContratoSection/>`.
 *
 * Same split as `MatriculaAtosContainer`: everything under `card/**` is
 * presentational (S3 discipline) and this file owns the readiness query
 * (`useContratoGeracao`) and the generate mutation (`useContratoMutations`'s
 * `gerar`). The date draft, and the transient "what did the last attempt
 * return" state (a 400's `details`, a 201's `avisos`) live here too — they
 * are request lifecycle, not layout.
 */
import { useState } from "react";
import { toast } from "sonner";

import GeradorContratoSection from "@/components/card/GeradorContratoSection";
import {
  ContratoGeracaoError,
  useContratoGeracao,
  useContratoMutations,
} from "@/hooks/useContratos";

export interface GeradorContratoContainerProps {
  clienteId: string;
  contratoId: string;
  /** Whether the "Gerar contrato" collapsible is open — the lazy gate the F5
   *  brief asks for. See `useContratoGeracao`'s header note. */
  aberto: boolean;
}

function hoje(): string {
  return new Date().toISOString().slice(0, 10);
}

export function GeradorContratoContainer({
  clienteId,
  contratoId,
  aberto,
}: GeradorContratoContainerProps) {
  const query = useContratoGeracao(clienteId, contratoId, aberto);
  const { gerar } = useContratoMutations(clienteId);

  const [assinaturaData, setAssinaturaData] = useState(hoje);
  const [erroGeracao, setErroGeracao] = useState<ContratoGeracaoError | null>(null);
  const [avisosGerados, setAvisosGerados] = useState<string[] | null>(null);

  // 🔴 Two signals off `data`, never `isLoading`: it is false mid-refetch, so
  // an empty/error branch keyed off it would lie over data still good to
  // look at (`KB § PATTERNS/frontend/lying-loading-state.md`).
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;

  function handleGerar() {
    setErroGeracao(null);
    setAvisosGerados(null);
    gerar.mutate(
      { contratoId, assinaturaData: assinaturaData || undefined },
      {
        onSuccess: (result) => {
          setAvisosGerados(result.avisos.map((a) => a.mensagem));
          toast.success("Nova versão gerada.");
        },
        onError: (err) => {
          if (err instanceof ContratoGeracaoError && err.code === "CONTRATO_INCOMPLETO") {
            setErroGeracao(err);
            return;
          }
          toast.error(
            err instanceof Error ? err.message : "Não foi possível gerar o contrato.",
          );
        },
      },
    );
  }

  return (
    <GeradorContratoSection
      status={query.data}
      showSkeleton={showSkeleton}
      isRefreshing={isRefreshing}
      isError={query.isError && !query.data}
      onRetry={() => query.refetch()}
      assinaturaData={assinaturaData}
      onAssinaturaDataChange={setAssinaturaData}
      gerando={gerar.isPending}
      onGerar={handleGerar}
      erroGeracao={erroGeracao}
      avisosGerados={avisosGerados}
    />
  );
}
