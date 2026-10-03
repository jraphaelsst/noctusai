/**
 * `<QualificacaoContratoContainer/>` — data for `QualificacaoContratoForm`
 * (identidade tipo + pacto antenupcial, migration 193) for ONE person: the
 * full person row (`useQualificacaoContrato`) and the shared person PATCH
 * (`useDadosPessoaisMutation` — one write path for the `clientes` columns).
 * Mounted per person: each party's documentos panel and the titular's tab.
 */
import { toast } from "sonner";

import { QualificacaoContratoForm } from "@/components/card/QualificacaoContratoForm";
import { useDadosPessoaisMutation } from "@/hooks/useCardHub";
import { useQualificacaoContrato } from "@/hooks/useQualificacaoContrato";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function QualificacaoContratoContainer({ clienteId }: { clienteId: string }) {
  const query = useQualificacaoContrato(clienteId);
  const salvar = useDadosPessoaisMutation(clienteId);
  return (
    <QualificacaoContratoForm
      testId={`qualificacao-contrato-${clienteId}`}
      registro={query.data}
      showSkeleton={query.showSkeleton}
      isRefreshing={query.isRefreshing}
      isError={query.isError}
      onRetry={() => query.refetch()}
      salvando={salvar.isPending}
      erro={salvar.isError ? mensagemErroServidor(salvar.error, "Não foi possível salvar.") : null}
      onSalvar={(patch) =>
        salvar.mutate(patch, {
          onSuccess: (res) =>
            toast.success(
              res?.pendente_confirmacao?.length
                ? "Salvo — parte dos valores aguarda a confirmação de um administrador."
                : "Dados do contrato salvos.",
            ),
        })
      }
    />
  );
}

export default QualificacaoContratoContainer;
