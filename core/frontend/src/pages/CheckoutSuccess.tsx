import React from 'react';
import { useNavigate } from 'react-router-dom';

export function CheckoutSuccess() {
  const navigate = useNavigate();

  return (
    <div className="checkout-result">
      <div className="checkout-result-card">
        <div className="checkout-result-icon success">✓</div>
        <h2>Assinatura confirmada!</h2>
        <p>
          Seu pagamento foi processado com sucesso. Sua organização já tem acesso
          aos recursos do plano contratado.
        </p>
        <div className="checkout-result-actions">
          <button className="btn-primary checkout-result-btn" onClick={() => navigate('/')}>
            Ir para o Dashboard
          </button>
          <button className="btn-secondary" onClick={() => navigate('/billing')}>
            Ver Faturamento
          </button>
        </div>
      </div>
    </div>
  );
}
