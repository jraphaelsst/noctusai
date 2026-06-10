/**
 * Shared mock data for social-wiring e2e tests.
 * Mirrors the §1 contract shapes from the plan.
 */

export const mockSupabaseUser = {
  id: 'user-sw-001',
  aud: 'authenticated',
  role: 'authenticated',
  email: 'usuario@social.com',
  email_confirmed_at: '2025-01-01T00:00:00Z',
  phone: '',
  confirmed_at: '2025-01-01T00:00:00Z',
  last_sign_in_at: '2026-06-01T10:00:00Z',
  app_metadata: { provider: 'email', providers: ['email'] },
  user_metadata: { nome: 'Usuário Social' },
  identities: [],
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2026-06-01T10:00:00Z',
};

export const mockSession = {
  access_token: 'mock-supabase-jwt-token',
  token_type: 'bearer',
  expires_in: 3600,
  expires_at: Math.floor(Date.now() / 1000) + 3600,
  refresh_token: 'mock-refresh-token',
  user: mockSupabaseUser,
};

export const mockProfile = {
  id: 'user-sw-001',
  nome: 'Usuário Social',
  email: 'usuario@social.com',
  telefone: null,
  avatar: null,
  cargo: null,
  last_activity_at: '2026-06-01T10:00:00Z',
};

// ─── Mailchimp fixtures ────────────────────────────────────────────────────

export const mockConnectionConnected = {
  connected: true,
  server_prefix: 'us6',
  audience_id: 'aud-001',
  audience_name: 'Minha Audiência',
  created_at: '2026-06-01T10:00:00Z',
  updated_at: '2026-06-01T10:00:00Z',
};

export const mockConnectionDisconnected = {
  connected: false,
  server_prefix: null,
  audience_id: null,
  audience_name: null,
  created_at: null,
  updated_at: null,
};

export const mockAudiences = {
  items: [
    { id: 'aud-001', name: 'Minha Audiência', member_count: 150 },
    { id: 'aud-002', name: 'Lista VIP', member_count: 42 },
  ],
  total: 2,
};

export const mockContacts = {
  items: [
    {
      email: 'joao@exemplo.com',
      status: 'subscribed',
      first_name: 'João',
      last_name: 'Silva',
      tags: ['vip', 'newsletter'],
      vip: true,
      last_changed: '2026-06-01T10:00:00Z',
    },
    {
      email: 'maria@exemplo.com',
      status: 'subscribed',
      first_name: 'Maria',
      last_name: 'Santos',
      tags: [],
      vip: false,
      last_changed: '2026-05-15T08:00:00Z',
    },
  ],
  total: 2,
};

export const mockSegments = {
  items: [
    {
      id: 1,
      name: 'Clientes VIP',
      member_count: 25,
      created_at: '2026-05-01T00:00:00Z',
      updated_at: '2026-06-01T00:00:00Z',
    },
    {
      id: 2,
      name: 'Newsletter',
      member_count: 100,
      created_at: '2026-04-01T00:00:00Z',
      updated_at: '2026-05-20T00:00:00Z',
    },
  ],
  total: 2,
};

export const mockSegmentMembers = {
  items: [
    {
      email: 'joao@exemplo.com',
      status: 'subscribed',
      first_name: 'João',
      last_name: 'Silva',
    },
  ],
  total: 1,
};

export const mockTemplates = {
  items: [
    {
      id: 101,
      name: 'Newsletter Junho',
      category: 'newsletter',
      type: 'user',
      drag_and_drop: false,
      preview_image: null,
      date_created: '2026-06-01T10:00:00Z',
      date_edited: '2026-06-01T12:00:00Z',
      edit_url: 'https://us6.admin.mailchimp.com/templates/edit?id=101',
    },
    {
      id: 102,
      name: 'Promoção Verão',
      category: 'promotional',
      type: 'user',
      drag_and_drop: true,
      preview_image: null,
      date_created: '2026-05-15T10:00:00Z',
      date_edited: '2026-05-16T10:00:00Z',
      edit_url: 'https://us6.admin.mailchimp.com/templates/edit?id=102',
    },
  ],
  total: 2,
};

export const mockCampaigns = {
  items: [
    {
      id: 'camp-001',
      web_id: 1001,
      title: 'Campanha Junho',
      status: 'save' as const,
      subject_line: 'Ofertas especiais de junho',
      preview_text: 'Confira nossas novidades',
      from_name: 'Social Wiring',
      reply_to: 'noreply@social.com',
      segment_id: null,
      template_id: 101,
      send_time: null,
      create_time: '2026-06-01T10:00:00Z',
      emails_sent: null,
      opens: null,
      clicks: null,
      archive_url: null,
    },
    {
      id: 'camp-002',
      web_id: 1002,
      title: 'Newsletter Maio',
      status: 'sent' as const,
      subject_line: 'Newsletter de maio',
      preview_text: null,
      from_name: 'Social Wiring',
      reply_to: 'noreply@social.com',
      segment_id: 1,
      template_id: null,
      send_time: '2026-05-10T14:00:00Z',
      create_time: '2026-05-09T10:00:00Z',
      emails_sent: 120,
      opens: 45,
      clicks: 12,
      archive_url: 'https://mailchi.mp/exemplo/newsletter-maio',
    },
  ],
  total: 2,
};
