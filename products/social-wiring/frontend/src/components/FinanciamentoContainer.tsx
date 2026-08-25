/**
 * `<FinanciamentoContainer/>` — data for the card's Financiamento subpage.
 *
 * Same split as `PessoaDocumentosPanel`: the dialog stays presentational and
 * this owns the queries.
 */
import { toast } from "sonner";

import FinanciamentoPanel from "@/components/card/FinanciamentoPanel";
import {
  useFinanciamento,
  useFinanciamentoDocumentoMutations,
  useFinanciamentoMutation,
} from "@/hooks/useFinanciamento";

export function FinanciamentoContainer({ clienteId }: { clienteId: string }) {
  const query = useFinanciamento(clienteId);
  const mutation = useFinanciamentoMutation(clienteId);
  const docs = useFinanciamentoDocumentoMutations(clienteId);

  return (
    <FinanciamentoPanel
      financiamento={query.data}
      // `isPending || isFetching`, never `isLoading` — see NegociacaoContainer.
      loading={query.isPending || query.isFetching}
      saving={mutation.isPending}
      uploading={docs.upload.isPending}
      error={
        mutation.error?.message ??
        docs.upload.error?.message ??
        docs.remove.error?.message ??
        null
      }
      onSave={(patch) => mutation.mutate(patch)}
      onUpload={(file, tipoDocumento) =>
        docs.upload.mutate({ file, tipoDocumento })
      }
      onRemove={(documentoId, motivo) =>
        docs.remove.mutate({ documentoId, motivo })
      }
      onOpen={async (documentoId) => {
        try {
          // 🔴 This call is a RECORDED access to the document's content.
          // Only ever fired from an explicit click.
          const res = await docs.getUrl.mutateAsync({ documentoId });
          if (res?.url) window.open(res.url, "_blank", "noopener,noreferrer");
        } catch (err) {
          toast.error(
            err instanceof Error ? err.message : "Não foi possível abrir o documento.",
          );
        }
      }}
    />
  );
}
