import React from 'react';
import { useNavigate } from 'react-router-dom';

export function CheckoutCancel() {
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-8 text-center shadow-sm">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 text-2xl font-bold text-red-600">
          ✕
        </div>
        <h2 className="mb-3 text-2xl font-bold text-foreground">Checkout cancelado</h2>
        <p className="mb-8 text-muted-foreground">
          O processo de pagamento foi cancelado. Nenhuma cobrança foi realizada.
          Você pode tentar novamente quando quiser.
        </p>
        <div className="flex flex-col gap-3">
          <button
            className="w-full rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            onClick={() => navigate('/pricing')}
          >
            Ver Planos
          </button>
          <button
            className="w-full rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted"
            onClick={() => navigate('/')}
          >
            Voltar ao Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
