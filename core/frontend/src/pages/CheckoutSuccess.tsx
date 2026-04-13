import React from 'react';
import { useNavigate } from 'react-router-dom';

export function CheckoutSuccess() {
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-8 text-center shadow-sm">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 text-2xl font-bold text-green-600">
          ✓
        </div>
        <h2 className="mb-3 text-2xl font-bold text-foreground">Assinatura confirmada!</h2>
        <p className="mb-8 text-muted-foreground">
          Seu pagamento foi processado com sucesso. Sua organização já tem acesso
          aos recursos do plano contratado.
        </p>
        <div className="flex flex-col gap-3">
          <button
            className="w-full rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            onClick={() => navigate('/')}
          >
            Ir para o Dashboard
          </button>
          <button
            className="w-full rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted"
            onClick={() => navigate('/billing')}
          >
            Ver Faturamento
          </button>
        </div>
      </div>
    </div>
  );
}
