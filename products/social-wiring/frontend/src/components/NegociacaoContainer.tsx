/**
 * `<NegociacaoContainer/>` — data for the card's Negociação subpage.
 *
 * Same split as `PessoaDocumentosPanel`: `ClienteCardDialog` is presentational
 * and must stay renderable in a test with plain objects and no query client,
 * so everything that fetches lives out here and reaches it as a render prop.
 */
import { ImovelCodigoPicker } from "@/components/card/ImovelCodigoPicker";
import NegociacaoEstruturadaPanel from "@/components/card/NegociacaoEstruturadaPanel";
import NegociacaoPanel from "@/components/card/NegociacaoPanel";
import {
  useNegociacao,
  useNegociacaoMutation,
} from "@/hooks/useNegociacao";

export function NegociacaoContainer({ clienteId }: { clienteId: string }) {
  const query = useNegociacao(clienteId);
  const mutation = useNegociacaoMutation(clienteId);

  return (
    <>
      <NegociacaoPanel
        negociacao={query.data}
        // 🔴 First load only — `isPending && !data`, never `isLoading` (false
        // mid-refetch) and never a bare `|| isFetching`: every save refetches
        // this query, and that disabled the very form the operator was
        // typing in (lying-loading-state, KB § PATTERNS/frontend/
        // lying-loading-state.md).
        loading={query.isPending && !query.data}
        saving={mutation.isPending}
        error={mutation.error?.message ?? null}
        onSave={(patch) => mutation.mutate(patch)}
        // The picker fetches, so it is injected here rather than imported by
        // the panel — same seam as `ClienteCardDialog`'s `renderNegociacao`,
        // and for the same reason: the panel stays renderable in a test with
        // plain objects and no query client.
        renderImovelPicker={(props) => (
          <ImovelCodigoPicker id="negociacao-imovel" {...props} />
        )}
      />
      {/* The contract's structured terms (migration 108): parcelas,
          favorecidos, intermediários, posse, permuta. Self-contained — it owns
          its queries — and sits under the price/commission panel because it
          allocates the valor negociado that panel sets. */}
      <NegociacaoEstruturadaPanel clienteId={clienteId} />
    </>
  );
}
