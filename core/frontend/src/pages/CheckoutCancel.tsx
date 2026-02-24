import React from 'react';
import { useNavigate } from 'react-router-dom';

export function CheckoutCancel() {
  const navigate = useNavigate();

  return (
    <div className="checkout-result">
      <div className="checkout-result-card">
        <div className="checkout-result-icon cancel">✕</div>
        <h2>Checkout cancelado</h2>
        <p>
          O processo de pagamento foi cancelado. Nenhuma cobrança foi realizada.
          Você pode tentar novamente quando quiser.
        </p>
        <div className="checkout-result-actions">
          <button className="btn-primary checkout-result-btn" onClick={() => navigate('/pricing')}>
            Ver Planos
          </button>
          <button className="btn-secondary" onClick={() => navigate('/')}>
            Voltar ao Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
