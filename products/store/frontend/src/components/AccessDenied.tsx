import { ApiError } from "@noctusai/lib";
import { ShieldAlert } from "lucide-react";

/** True when a query failed because the signed-in user is not a store admin (403). */
export const isForbidden = (err: unknown): boolean => err instanceof ApiError && err.status === 403;

/** Explicit "Sem acesso" state — shown INSTEAD of any admin form/table. */
export function AccessDenied() {
  return (
    <div role="alert" className="mx-auto max-w-md rounded-lg border border-border bg-card p-8 text-center space-y-3">
      <ShieldAlert className="mx-auto h-8 w-8 text-destructive" />
      <h1 className="text-lg font-semibold text-foreground">Sem acesso</h1>
      <p className="text-sm text-muted-foreground">
        Esta área é restrita à administração da loja. Entre com a conta autorizada ou peça acesso ao responsável.
      </p>
    </div>
  );
}
