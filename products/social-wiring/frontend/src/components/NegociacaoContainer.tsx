/**
 * `<NegociacaoContainer/>` — data for the card's Negociação subpage.
 *
 * Same split as `PessoaDocumentosPanel`: `ClienteCardDialog` is presentational
 * and must stay renderable in a test with plain objects and no query client,
 * so everything that fetches lives out here and reaches it as a render prop.
 */
import NegociacaoPanel from "@/components/card/NegociacaoPanel";
import {
  useNegociacao,
  useNegociacaoMutation,
} from "@/hooks/useNegociacao";

export function NegociacaoContainer({ clienteId }: { clienteId: string }) {
  const query = useNegociacao(clienteId);
  const mutation = useNegociacaoMutation(clienteId);

  return (
    <NegociacaoPanel
      negociacao={query.data}
      // 🔴 `isPending || isFetching`, never `isLoading`: TanStack v5's
      // `isLoading` is false during a background refetch, so an empty branch
      // would render "nothing here" over data that exists.
      loading={query.isPending || query.isFetching}
      saving={mutation.isPending}
      error={mutation.error?.message ?? null}
      onSave={(patch) => mutation.mutate(patch)}
    />
  );
}
