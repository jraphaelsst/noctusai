/**
 * `SemAcessoPage` — seed-mounted at `/sem-acesso` in every product.
 *
 * Shown when the user's org holds no active license for the product (the
 * login/SSO access check said so, or any API call answered 403
 * `org_sem_licenca`). Offers the way back to core and a sign-out.
 */
import { useState } from "react";

export interface SemAcessoPageProps {
  /** Core dashboard URL ("Voltar para a NoctusAI"). */
  coreUrl: string;
  /** Sign the user out of this product. */
  onSignOut: () => void | Promise<void>;
}

export function SemAcessoPage({ coreUrl, onSignOut }: SemAcessoPageProps) {
  const [leaving, setLeaving] = useState(false);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md space-y-4 rounded-lg border border-border bg-card p-8 text-center shadow-sm">
        <h1 className="text-xl font-semibold text-foreground">Sem acesso</h1>
        <p className="text-muted-foreground">
          Sua organização não tem acesso a este produto.
        </p>
        <div className="flex flex-col gap-2">
          <a
            href={coreUrl}
            className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Voltar para a NoctusAI
          </a>
          <button
            type="button"
            disabled={leaving}
            onClick={async () => {
              setLeaving(true);
              try {
                await onSignOut();
              } finally {
                setLeaving(false);
              }
            }}
            className="inline-flex h-10 items-center justify-center rounded-md border border-input bg-background px-4 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            Sair
          </button>
        </div>
      </div>
    </div>
  );
}
