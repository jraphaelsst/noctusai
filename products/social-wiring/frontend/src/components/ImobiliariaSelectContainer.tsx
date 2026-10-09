/**
 * `<ImobiliariaSelectContainer/>` — data for `<ImobiliariaSelect/>`.
 *
 * Same split as `TestemunhasSelectContainer`: everything under `card/**` is
 * presentational; this owns `useContratoImobiliaria` (the resolved choice,
 * GET/PUT) and `useImobiliarias` (the SAME registry hook the settings page
 * calls — no second fetch path). A pick saves immediately.
 *
 * Unlike the witnesses picker this is always mounted (not behind a
 * collapsible): the choice is REQUIRED, so it must be visible.
 */
import { ImobiliariaSelect } from "@/components/card/ImobiliariaSelect";
import {
  useContratoImobiliaria,
  useDefinirContratoImobiliaria,
} from "@/hooks/useContratoImobiliaria";
import { useImobiliarias } from "@/hooks/useImobiliarias";
import { toastServerError } from "@/lib/erroServidor";

export interface ImobiliariaSelectContainerProps {
  clienteId: string;
  contratoId: string;
}

export function ImobiliariaSelectContainer({ clienteId, contratoId }: ImobiliariaSelectContainerProps) {
  const selecao = useContratoImobiliaria(clienteId, contratoId);
  const registro = useImobiliarias();
  const definir = useDefinirContratoImobiliaria(clienteId, contratoId);

  // 🔴 Two signals off `data`, never `isLoading`.
  const showSkeleton = selecao.isPending && !selecao.data;
  const isRefreshing = selecao.isFetching && !!selecao.data;

  if (showSkeleton) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="imobiliaria-skeleton">
        Carregando imobiliária…
      </p>
    );
  }
  if (selecao.isError && !selecao.data) {
    return (
      <p className="text-xs text-destructive" data-testid="imobiliaria-erro">
        Não foi possível carregar a imobiliária do contrato.
      </p>
    );
  }
  if (!selecao.data) return null;

  return (
    <div data-refreshing={isRefreshing || undefined}>
      <ImobiliariaSelect
        contratoId={contratoId}
        atual={selecao.data}
        registro={registro.data?.items ?? []}
        onChange={(id) =>
          definir.mutate(id, {
            onError: (err) => toastServerError(err, "Não foi possível salvar a imobiliária."),
          })
        }
        salvando={definir.isPending}
      />
    </div>
  );
}
