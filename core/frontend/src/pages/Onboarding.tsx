import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth-context';

interface OnboardingSteps {
  company_details: boolean;
  choose_plan: boolean;
  invite_team: boolean;
  enable_product: boolean;
}

interface OnboardingStatus {
  org_id: string;
  org_nome: string;
  onboarding_completed: boolean;
  steps: OnboardingSteps;
  progress: {
    completed: number;
    total: number;
    percentage: number;
  };
}

interface Plan {
  id: string;
  name: string;
  slug: string;
  description: string;
  price_monthly: number;
}

interface Product {
  id: string;
  nome: string;
  slug: string;
  descricao: string;
  icone: string;
  has_access: boolean;
}

const STEP_KEYS = ['company_details', 'choose_plan', 'invite_team', 'enable_product'] as const;

const STEP_LABELS: Record<string, { title: string; description: string }> = {
  company_details: {
    title: 'Dados da Empresa',
    description: 'Preencha as informações da sua empresa',
  },
  choose_plan: {
    title: 'Escolher Plano',
    description: 'Selecione o plano ideal para sua empresa',
  },
  invite_team: {
    title: 'Convidar Equipe',
    description: 'Convide membros da sua equipe',
  },
  enable_product: {
    title: 'Ativar Produto',
    description: 'Escolha os produtos que deseja utilizar',
  },
};

export function Onboarding() {
  const navigate = useNavigate();
  const { user, organization } = useAuth();
  const [currentStep, setCurrentStep] = useState(0);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Step 1: Company details
  const [companyNome, setCompanyNome] = useState('');
  const [companyCnpj, setCompanyCnpj] = useState('');
  const [companyTelefone, setCompanyTelefone] = useState('');
  const [companyEndereco, setCompanyEndereco] = useState('');

  // Step 2: Plan selection
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);

  // Step 3: Invite team
  const [inviteEmails, setInviteEmails] = useState<string[]>(['']);

  // Step 4: Products
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProducts, setSelectedProducts] = useState<string[]>([]);

  useEffect(() => {
    fetchStatus();
  }, []);

  async function fetchStatus() {
    try {
      const res = await api.get('/api/onboarding/status');
      const data = res.data as OnboardingStatus;
      setStatus(data);

      // Pre-fill company name from org
      if (data.org_nome) setCompanyNome(data.org_nome);

      // Find first incomplete step
      const firstIncomplete = STEP_KEYS.findIndex(key => !data.steps[key]);
      if (firstIncomplete >= 0) {
        setCurrentStep(firstIncomplete);
      }

      // If already completed, redirect to dashboard
      if (data.onboarding_completed) {
        navigate('/');
        return;
      }

      // Fetch plans and products for later steps
      const [plansRes, meRes] = await Promise.all([
        api.get('/api/plans').catch(() => ({ data: [] })),
        api.get('/api/auth/me').catch(() => ({ products: [] })),
      ]);
      setPlans(plansRes.data || []);
      setProducts(meRes.products || []);
    } catch (err) {
      console.error('Error fetching onboarding status:', err);
    } finally {
      setLoading(false);
    }
  }

  async function completeStep(step: string, data?: any) {
    setSaving(true);
    setError('');
    try {
      const res = await api.patch('/api/onboarding/complete', { step, data });
      setStatus(prev => prev ? {
        ...prev,
        steps: res.data.steps,
        onboarding_completed: res.data.onboarding_completed,
        progress: res.data.progress,
      } : null);

      if (res.data.onboarding_completed) {
        navigate('/');
      } else if (currentStep < STEP_KEYS.length - 1) {
        setCurrentStep(currentStep + 1);
      }
    } catch (err: any) {
      setError(err.message || 'Erro ao salvar passo');
    } finally {
      setSaving(false);
    }
  }

  function handleCompanySubmit() {
    completeStep('company_details', {
      nome: companyNome,
      cnpj: companyCnpj,
      telefone: companyTelefone,
      endereco: companyEndereco,
    });
  }

  function handlePlanSubmit() {
    if (selectedPlan) {
      completeStep('choose_plan', { plan_id: selectedPlan });
    } else {
      // Allow skipping plan selection
      completeStep('choose_plan');
    }
  }

  function handleInviteSubmit() {
    const validEmails = inviteEmails.filter(e => e.trim());
    completeStep('invite_team', { emails: validEmails });
  }

  function handleProductSubmit() {
    completeStep('enable_product', { product_slugs: selectedProducts });
  }

  function addEmailField() {
    setInviteEmails([...inviteEmails, '']);
  }

  function updateEmail(index: number, value: string) {
    const updated = [...inviteEmails];
    updated[index] = value;
    setInviteEmails(updated);
  }

  function removeEmail(index: number) {
    if (inviteEmails.length <= 1) return;
    setInviteEmails(inviteEmails.filter((_, i) => i !== index));
  }

  function toggleProduct(slug: string) {
    setSelectedProducts(prev =>
      prev.includes(slug) ? prev.filter(s => s !== slug) : [...prev, slug]
    );
  }

  function handleSkip() {
    completeStep(STEP_KEYS[currentStep]);
  }

  function handleBack() {
    if (currentStep > 0) setCurrentStep(currentStep - 1);
  }

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner" />
        <p>Carregando onboarding...</p>
      </div>
    );
  }

  const progressPercentage = status?.progress.percentage || 0;

  return (
    <div className="onboarding-page">
      <div className="onboarding-container">
        {/* Header */}
        <div className="onboarding-header">
          <div className="logo">
            <span className="logo-icon">⚡</span>
            <h1>NoctusAI</h1>
          </div>
          <p className="subtitle">Configure sua conta em poucos passos</p>
        </div>

        {/* Progress bar */}
        <div className="onboarding-progress">
          <div className="onboarding-progress-bar">
            <div
              className="onboarding-progress-fill"
              style={{ width: `${progressPercentage}%` }}
            />
          </div>
          <div className="onboarding-progress-steps">
            {STEP_KEYS.map((key, idx) => (
              <div
                key={key}
                className={`onboarding-progress-step ${
                  idx === currentStep ? 'active' : ''
                } ${status?.steps[key] ? 'completed' : ''}`}
                onClick={() => setCurrentStep(idx)}
              >
                <div className="onboarding-step-number">
                  {status?.steps[key] ? '✓' : idx + 1}
                </div>
                <span className="onboarding-step-label">{STEP_LABELS[key].title}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Step content */}
        <div className="onboarding-step">
          <h2>{STEP_LABELS[STEP_KEYS[currentStep]].title}</h2>
          <p className="onboarding-step-desc">{STEP_LABELS[STEP_KEYS[currentStep]].description}</p>

          {error && <div className="error">{error}</div>}

          {/* Step 1: Company Details */}
          {currentStep === 0 && (
            <div className="onboarding-form">
              <div className="field">
                <label>Nome da empresa</label>
                <input
                  type="text"
                  value={companyNome}
                  onChange={e => setCompanyNome(e.target.value)}
                  placeholder="Minha Empresa Ltda"
                />
              </div>
              <div className="field">
                <label>CNPJ</label>
                <input
                  type="text"
                  value={companyCnpj}
                  onChange={e => setCompanyCnpj(e.target.value)}
                  placeholder="00.000.000/0001-00"
                />
              </div>
              <div className="field">
                <label>Telefone</label>
                <input
                  type="text"
                  value={companyTelefone}
                  onChange={e => setCompanyTelefone(e.target.value)}
                  placeholder="(11) 99999-0000"
                />
              </div>
              <div className="field">
                <label>Endereco</label>
                <input
                  type="text"
                  value={companyEndereco}
                  onChange={e => setCompanyEndereco(e.target.value)}
                  placeholder="Rua Exemplo, 123 - Sao Paulo, SP"
                />
              </div>
            </div>
          )}

          {/* Step 2: Choose Plan */}
          {currentStep === 1 && (
            <div className="onboarding-plans">
              {plans.length === 0 ? (
                <p className="onboarding-empty">Nenhum plano disponivel no momento.</p>
              ) : (
                <div className="onboarding-plans-grid">
                  {plans.map(plan => (
                    <div
                      key={plan.id}
                      className={`onboarding-plan-card ${selectedPlan === plan.id ? 'selected' : ''}`}
                      onClick={() => setSelectedPlan(plan.id)}
                    >
                      <h3>{plan.name}</h3>
                      <p>{plan.description || 'Plano ' + plan.name}</p>
                      <div className="onboarding-plan-price">
                        <span className="onboarding-plan-value">
                          {plan.price_monthly === 0 ? 'Gratis' : `R$ ${plan.price_monthly}`}
                        </span>
                        {plan.price_monthly > 0 && <span className="onboarding-plan-period">/mes</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <button className="btn-link" onClick={() => navigate('/pricing')}>
                Ver todos os planos em detalhes
              </button>
            </div>
          )}

          {/* Step 3: Invite Team */}
          {currentStep === 2 && (
            <div className="onboarding-invite">
              {inviteEmails.map((email, idx) => (
                <div key={idx} className="onboarding-invite-row">
                  <div className="field" style={{ flex: 1, marginBottom: 0 }}>
                    <input
                      type="email"
                      value={email}
                      onChange={e => updateEmail(idx, e.target.value)}
                      placeholder="colega@empresa.com"
                    />
                  </div>
                  {inviteEmails.length > 1 && (
                    <button
                      type="button"
                      className="btn-sm btn-danger"
                      onClick={() => removeEmail(idx)}
                    >
                      Remover
                    </button>
                  )}
                </div>
              ))}
              <button type="button" className="btn-link" onClick={addEmailField}>
                + Adicionar outro email
              </button>
            </div>
          )}

          {/* Step 4: Enable Product */}
          {currentStep === 3 && (
            <div className="onboarding-products">
              {products.length === 0 ? (
                <p className="onboarding-empty">
                  Nenhum produto disponivel para ativacao. Voce podera solicitar acesso no painel principal.
                </p>
              ) : (
                <div className="onboarding-products-grid">
                  {products.map(product => (
                    <div
                      key={product.id}
                      className={`onboarding-product-card ${
                        selectedProducts.includes(product.slug) ? 'selected' : ''
                      }`}
                      onClick={() => toggleProduct(product.slug)}
                    >
                      <div className="onboarding-product-icon">{product.icone}</div>
                      <h3>{product.nome}</h3>
                      <p>{product.descricao}</p>
                      <div className="onboarding-product-check">
                        {selectedProducts.includes(product.slug) ? '✓ Selecionado' : 'Clique para selecionar'}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="onboarding-actions">
          <div className="onboarding-actions-left">
            {currentStep > 0 && (
              <button className="btn-secondary" onClick={handleBack}>
                Voltar
              </button>
            )}
          </div>
          <div className="onboarding-actions-right">
            <button className="btn-secondary" onClick={handleSkip} disabled={saving}>
              Pular
            </button>
            <button
              className="btn-primary"
              disabled={saving}
              onClick={() => {
                if (currentStep === 0) handleCompanySubmit();
                else if (currentStep === 1) handlePlanSubmit();
                else if (currentStep === 2) handleInviteSubmit();
                else if (currentStep === 3) handleProductSubmit();
              }}
            >
              {saving ? 'Salvando...' : currentStep === STEP_KEYS.length - 1 ? 'Concluir' : 'Proximo'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
