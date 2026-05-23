export const mockUser = {
  id: 'user-001',
  nome: 'Rafael Oliveira',
  email: 'rafael@imobiliaria.com',
  role: 'member',
  org_id: 'org-001',
};

export const mockAdminUser = {
  id: 'admin-001',
  nome: 'Ana Souza',
  email: 'ana@noctus.ai',
  role: 'admin',
  org_id: 'org-001',
};

export const mockOrganization = {
  id: 'org-001',
  nome: 'Imobiliária Centro Sul',
  slug: 'imobiliaria-centro-sul',
  plano: 'pro',
  category: 'production',
};

export const mockFreeOrganization = {
  id: 'org-002',
  nome: 'Imobiliária Teste',
  slug: 'imobiliaria-teste',
  plano: 'free',
  category: 'production',
};

export const mockProducts = [
  {
    id: 'prod-001',
    nome: 'ERP Imobiliário',
    slug: 'erp-imobiliario',
    descricao: 'Gestão completa para imobiliárias',
    icone: '🏢',
    url_base: 'http://localhost:8080',
    cor: '#3b82f6',
    has_access: true,
  },
  {
    id: 'prod-002',
    nome: 'CRM Vendas',
    slug: 'crm-vendas',
    descricao: 'Funil de vendas inteligente com IA',
    icone: '📊',
    url_base: 'http://localhost:8081',
    cor: '#10b981',
    has_access: false,
  },
];

export const mockSubscription = {
  id: 'sub-001',
  status: 'active',
  started_at: '2025-01-01T00:00:00Z',
  expires_at: null,
  plans: { name: 'Profissional', slug: 'pro' },
};

export const mockTrialSubscription = {
  id: 'sub-002',
  status: 'trial',
  started_at: '2026-02-20T00:00:00Z',
  expires_at: '2026-03-20T00:00:00Z',
  plans: { name: 'Profissional', slug: 'pro' },
};

// The /api/plans consumers (Pricing, AdminPlans, Onboarding) read the
// Portuguese contract fields `nome` / `descricao` (mirroring mockOrganization
// and mockProducts). The pre-refactor mock used `name` / `description`, which
// the pages never read → cards rendered with undefined names. Match the real
// contract here.
export const mockPlans = [
  {
    id: 'plan-001',
    nome: 'Gratuito',
    slug: 'free',
    descricao: 'Para conhecer a plataforma',
    price_monthly: 0,
    price_yearly: 0,
    max_users: 1,
    max_products: 1,
    features: { suporte_email: true },
    is_custom: false,
    is_active: true,
  },
  {
    id: 'plan-002',
    nome: 'Profissional',
    slug: 'pro',
    descricao: 'Para equipes em crescimento',
    price_monthly: 199.9,
    price_yearly: 1999.9,
    max_users: 10,
    max_products: 5,
    features: { suporte_email: true, suporte_prioritario: true, api_access: true },
    is_custom: false,
    is_active: true,
  },
];

export const mockTeamMembers = [
  {
    id: 'user-001',
    nome: 'Rafael Oliveira',
    email: 'rafael@imobiliaria.com',
    org_role: 'owner',
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 'user-002',
    nome: 'Mariana Lima',
    email: 'mariana@imobiliaria.com',
    org_role: 'member',
    created_at: '2025-03-15T00:00:00Z',
  },
];

export const mockInvitations = [
  {
    id: 'inv-001',
    email: 'joao@imobiliaria.com',
    role: 'member',
    status: 'pending',
    invited_by: 'user-001',
    expires_at: '2026-03-15T00:00:00Z',
    created_at: '2026-02-15T00:00:00Z',
  },
];

export const mockRoles = [
  { id: 'role-001', name: 'Proprietário', slug: 'owner', permissions: ['*'], is_system: true },
  { id: 'role-002', name: 'Administrador', slug: 'admin', permissions: ['manage_team', 'manage_billing'], is_system: true },
  { id: 'role-003', name: 'Membro', slug: 'member', permissions: ['read', 'write'], is_system: true },
];

export const mockOnboardingStatus = {
  org_id: 'org-001',
  org_nome: 'Imobiliária Centro Sul',
  onboarding_completed: false,
  steps: {
    company_details: false,
    choose_plan: false,
    invite_team: false,
    enable_product: false,
  },
  progress: { completed: 0, total: 4, percentage: 0 },
};

export const mockAdminStats = {
  total_orgs: 42,
  active_subscriptions: 35,
  total_api_keys: 12,
  total_plans: 3,
};

export const mockAdminOrganizations = [
  { id: 'org-001', nome: 'Imobiliária Centro Sul', slug: 'imobiliaria-centro-sul', created_at: '2025-01-01T00:00:00Z' },
  { id: 'org-002', nome: 'Construtora ABC', slug: 'construtora-abc', created_at: '2025-06-01T00:00:00Z' },
];

export const mockAdminSubscriptions = [
  {
    id: 'sub-001',
    org_id: 'org-001',
    plan_id: 'plan-002',
    status: 'active',
    started_at: '2025-01-01T00:00:00Z',
    organizations: { nome: 'Imobiliária Centro Sul' },
    plans: { name: 'Profissional' },
  },
];

export const mockAdminApiKeys = [
  {
    id: 'key-001',
    name: 'Produção',
    prefix: 'noctus_k_abc12',
    scopes: ['read', 'write'],
    is_active: true,
    created_at: '2025-06-01T00:00:00Z',
    expires_at: null,
  },
];
