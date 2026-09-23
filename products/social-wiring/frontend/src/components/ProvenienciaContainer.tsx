/**
 * `<ProvenienciaContainer/>` — data for `<ProvenienciaPanel/>`.
 *
 * Same split as `GeradorContratoContainer`: `card/**` stays presentational
 * (S3) and this file owns the `useProveniencia` query. Mounted through
 * `ContratosPanel.renderProveniencia`, one instance per contract, gated by
 * that contract's own collapsible `aberto` state (see `useProveniencia`'s
 * header note on why `aberto` is the lazy-fetch gate, not just the ids).
 */
import ProvenienciaPanel from "@/components/card/ProvenienciaPanel";
import { useProveniencia } from "@/hooks/useProveniencia";

export interface ProvenienciaContainerProps {
  clienteId: string;
  contratoId: string;
  /** Whether the "Proveniência" collapsible is open. */
  aberto: boolean;
}

export function ProvenienciaContainer({ clienteId, contratoId, aberto }: ProvenienciaContainerProps) {
  const query = useProveniencia(clienteId, contratoId, aberto);

  // 🔴 Two signals off `data`, never `isLoading`: it is false mid-refetch, so
  // an empty/error branch keyed off it would lie over data still good to
  // look at (`KB § PATTERNS/frontend/lying-loading-state.md`).
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;

  return (
    <ProvenienciaPanel
      items={query.data?.items}
      showSkeleton={showSkeleton}
      isRefreshing={isRefreshing}
      isError={query.isError && !query.data}
      onRetry={() => query.refetch()}
    />
  );
}
