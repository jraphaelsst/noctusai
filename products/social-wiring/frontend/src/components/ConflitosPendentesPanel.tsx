/**
 * `<ConflitosPendentesPanel/>` — one person's admin-decide surface (owner
 * directive, 2026-09-19), mirroring `QualificacaoCompletudePanel`'s own
 * self-contained shape: the only required input is `clienteId`, the panel
 * owns its own query + mutation, and it is mounted BOTH directly by
 * `PessoaDocumentosPanel` (which already has `clienteId` as a prop) and
 * thunked in for the titular via `ClienteCardDialog`'s
 * `renderConflitosPendentes` (that component is never handed the titular's
 * raw id — see its own docstring).
 *
 * Presentational work is `ConflitosPendentesCard`'s; this file is the
 * container `components/card/**`'s S3 rule keeps out of that one.
 */
import { toast } from "sonner";

import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext } from "@noctusai/lib";

import { ConflitosPendentesCard } from "@/components/card/ConflitosPendentesCard";
import { useConflitosPendentes, useDecidirConflitoMutation } from "@/hooks/useCardHub";

export interface ConflitosPendentesPanelProps {
  /** The PERSON's own `clientes.id` — never a parte edge id. */
  clienteId: string;
}

function erro(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

export function ConflitosPendentesPanel({ clienteId }: ConflitosPendentesPanelProps) {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  // A UI convenience ONLY — same posture `Equipe.tsx`'s button visibility
  // already takes. The server's own `decidir_conflito_route` reads the
  // TRUSTED `noctus_users` row and 403s a spoofed claim regardless of what
  // this renders.
  const isAdmin =
    ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";

  const conflitos = useConflitosPendentes(clienteId);
  const decidir = useDecidirConflitoMutation();

  if (!conflitos.data?.length) return null;

  return (
    <ConflitosPendentesCard
      conflitos={conflitos.data}
      isAdmin={isAdmin}
      decidingId={decidir.isPending ? decidir.variables?.conflitoId ?? null : null}
      onDecidir={(conflitoId, aceitar) =>
        decidir.mutate(
          { conflitoId, aceitar },
          {
            onError: (e) =>
              toast.error(erro(e, "Não foi possível decidir a pendência.")),
          },
        )
      }
      testId={`conflitos-pendentes-${clienteId}`}
    />
  );
}
