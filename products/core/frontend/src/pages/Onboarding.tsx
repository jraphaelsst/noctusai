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
      <div className="flex min-h-screen flex-col items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
        <p className="mt-4 text-muted-foreground">Carregando onboarding...</p>
      </div>
    );
  }

  const progressPercentage = status?.progress.percentage || 0;

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 sm:px-6 lg:px-8 py-6 sm:py-10 lg:py-12">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="flex items-center justify-center gap-2">
            <span className="text-2xl">⚡</span>
            <h1 className="text-2xl font-bold text-foreground">NoctusAI</h1>
          </div>
          <p className="mt-2 text-muted-foreground">Configure sua conta em poucos passos</p>
        </div>

        {/* Progress bar */}
        <div className="mb-8">
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${progressPercentage}%` }}
            />
          </div>
          <div className="mt-4 flex justify-between">
            {STEP_KEYS.map((key, idx) => (
              <button
                key={key}
                className="flex flex-col items-center gap-1.5"
                onClick={() => setCurrentStep(idx)}
              >
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-colors ${
                    status?.steps[key]
                      ? 'bg-primary text-primary-foreground'
                      : idx === currentStep
                        ? 'border-2 border-primary bg-background text-primary'
                        : 'border border-border bg-muted text-muted-foreground'
                  }`}
                >
                  {status?.steps[key] ? '✓' : idx + 1}
                </div>
                <span className={`hidden text-xs sm:block ${
                  idx === currentStep ? 'font-medium text-foreground' : 'text-muted-foreground'
                }`}>
                  {STEP_LABELS[key].title}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Step content */}
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h2 className="text-xl font-semibold text-foreground">
            {STEP_LABELS[STEP_KEYS[currentStep]].title}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {STEP_LABELS[STEP_KEYS[currentStep]].description}
          </p>

          {error && (
            <div className="mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-800">
              {error}
            </div>
          )}

          {/* Step 1: Company Details */}
          {currentStep === 0 && (
            <div className="mt-6 space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Nome da empresa
                </label>
                <input
                  type="text"
                  value={companyNome}
                  onChange={e => setCompanyNome(e.target.value)}
                  placeholder="Minha Empresa Ltda"
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">CNPJ</label>
                <input
                  type="text"
                  value={companyCnpj}
                  onChange={e => setCompanyCnpj(e.target.value)}
                  placeholder="00.000.000/0001-00"
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Telefone</label>
                <input
                  type="text"
                  value={companyTelefone}
                  onChange={e => setCompanyTelefone(e.target.value)}
                  placeholder="(11) 99999-0000"
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Endereco</label>
                <input
                  type="text"
                  value={companyEndereco}
                  onChange={e => setCompanyEndereco(e.target.value)}
                  placeholder="Rua Exemplo, 123 - Sao Paulo, SP"
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>
          )}

          {/* Step 2: Choose Plan */}
          {currentStep === 1 && (
            <div className="mt-6">
              {plans.length === 0 ? (
                <p className="py-8 text-center text-muted-foreground">
                  Nenhum plano disponivel no momento.
                </p>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {plans.map(plan => (
                    <button
                      key={plan.id}
                      type="button"
                      className={`rounded-lg border p-4 text-left transition-colors ${
                        selectedPlan === plan.id
                          ? 'border-primary bg-primary/5 ring-2 ring-primary'
                          : 'border-border bg-card hover:border-primary/50'
                      }`}
                      onClick={() => setSelectedPlan(plan.id)}
                    >
                      <h3 className="font-semibold text-foreground">{plan.name}</h3>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {plan.description || 'Plano ' + plan.name}
                      </p>
                      <div className="mt-3">
                        <span className="text-lg font-bold text-foreground">
                          {plan.price_monthly === 0 ? 'Gratis' : `R$ ${plan.price_monthly}`}
                        </span>
                        {plan.price_monthly > 0 && (
                          <span className="text-sm text-muted-foreground">/mes</span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              <button
                className="mt-4 text-sm text-primary hover:underline"
                onClick={() => navigate('/pricing')}
              >
                Ver todos os planos em detalhes
              </button>
            </div>
          )}

          {/* Step 3: Invite Team */}
          {currentStep === 2 && (
            <div className="mt-6 space-y-3">
              {inviteEmails.map((email, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <input
                    type="email"
                    value={email}
                    onChange={e => updateEmail(idx, e.target.value)}
                    placeholder="colega@empresa.com"
                    className="h-10 flex-1 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  {inviteEmails.length > 1 && (
                    <button
                      type="button"
                      className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700 hover:bg-red-100"
                      onClick={() => removeEmail(idx)}
                    >
                      Remover
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                className="text-sm text-primary hover:underline"
                onClick={addEmailField}
              >
                + Adicionar outro email
              </button>
            </div>
          )}

          {/* Step 4: Enable Product */}
          {currentStep === 3 && (
            <div className="mt-6">
              {products.length === 0 ? (
                <p className="py-8 text-center text-muted-foreground">
                  Nenhum produto disponivel para ativacao. Voce podera solicitar acesso no painel principal.
                </p>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  {products.map(product => (
                    <button
                      key={product.id}
                      type="button"
                      className={`rounded-lg border p-4 text-left transition-colors ${
                        selectedProducts.includes(product.slug)
                          ? 'border-primary bg-primary/5 ring-2 ring-primary'
                          : 'border-border bg-card hover:border-primary/50'
                      }`}
                      onClick={() => toggleProduct(product.slug)}
                    >
                      <div className="mb-2 text-2xl">{product.icone}</div>
                      <h3 className="font-semibold text-foreground">{product.nome}</h3>
                      <p className="mt-1 text-xs text-muted-foreground">{product.descricao}</p>
                      <div className={`mt-3 text-xs font-medium ${
                        selectedProducts.includes(product.slug) ? 'text-primary' : 'text-muted-foreground'
                      }`}>
                        {selectedProducts.includes(product.slug) ? '✓ Selecionado' : 'Clique para selecionar'}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="mt-6 flex items-center justify-between">
          <div>
            {currentStep > 0 && (
              <button
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted"
                onClick={handleBack}
              >
                Voltar
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
              onClick={handleSkip}
              disabled={saving}
            >
              Pular
            </button>
            <button
              className="rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
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
