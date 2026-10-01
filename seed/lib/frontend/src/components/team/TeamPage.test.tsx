/**
 * Tests for the TeamPage organ.
 *
 * Coverage:
 *   1. Loading — skeleton while the roster is pending; nothing fetched until `user` exists
 *   2. Error — role="alert" + retry
 *   3. Success — roster rows with policy labels (incl. a product extra role)
 *   4. No "Remover" action; the Core note links to `${coreUrl}/team`
 *   5. Invite dialog options come from `/api/team/policy` invitable_roles + labels
 *   6. Invite toast tells the e-mail truth (`email_enviado` false → warning w/ motivo)
 *   7. Pending invitations render + cancel DELETEs the invitation
 *   8. Non-manager sees neither invite nor invitations (and never GETs them)
 *   9. Refetch over data keeps the table mounted (two-signal loading rule)
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';

import { TeamPage } from './TeamPage';
import { TEAM_QUERY_KEYS } from './createTeamHooks';
import type { TeamApi, TeamMember, TeamInvitation, TeamPolicyContract } from './createTeamHooks';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

const MEMBERS: TeamMember[] = [
  { id: 'u1', nome: 'Ana Admin', email: 'ana@x.com', org_role: 'admin', created_at: '2026-01-02T00:00:00Z' },
  { id: 'u2', nome: 'Mo Derador', email: 'mo@x.com', org_role: 'moderador', created_at: '2026-02-03T00:00:00Z' },
];

const POLICY: TeamPolicyContract = {
  staff_roles: ['owner', 'admin', 'dev', 'moderador'],
  invitable_roles: ['admin', 'moderador'],
  labels: { owner: 'Proprietário', admin: 'Administrador', dev: 'Desenvolvedor', moderador: 'Moderador' },
};

const INVITES: TeamInvitation[] = [
  { id: 'i1', email: 'novo@x.com', role: 'moderador', status: 'pending', expires_at: '2026-12-01T00:00:00Z' },
];

const ADMIN_USER = { id: 'u1', user_metadata: { org_role: 'admin' } };
const MEMBER_USER = { id: 'u9', user_metadata: { org_role: 'member' } };

function makeApi(overrides: Partial<Record<string, any>> = {}): TeamApi {
  const get = vi.fn(async (path: string) => {
    if (path === '/api/team') return { data: overrides.members ?? MEMBERS };
    if (path === '/api/team/policy') return overrides.policy ?? POLICY;
    if (path === '/api/team/invitations') return { data: overrides.invites ?? INVITES };
    throw new Error(`unexpected GET ${path}`);
  });
  return {
    get: (overrides.get ?? get) as TeamApi['get'],
    post: (overrides.post ?? vi.fn(async () => ({ data: { id: 'i2' }, email_enviado: true }))) as TeamApi['post'],
    delete: (overrides.delete ?? vi.fn(async () => ({ ok: true }))) as TeamApi['delete'],
  };
}

function renderPage(props: Partial<Parameters<typeof TeamPage>[0]> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const api = props.api ?? makeApi();
  const utils = render(
    <QueryClientProvider client={client}>
      <TeamPage api={api} user={ADMIN_USER} coreUrl="https://core.example.com/" {...props} />
    </QueryClientProvider>,
  );
  return { ...utils, api, client };
}

describe('TeamPage: loading', () => {
  it('shows the skeleton and fetches nothing until the user exists', async () => {
    const api = makeApi();
    renderPage({ api, user: null });
    expect(screen.getByLabelText('Carregando equipe')).toHaveAttribute('aria-busy', 'true');
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe('TeamPage: error', () => {
  it('renders an alert with retry when the roster fails', async () => {
    const api = makeApi({
      get: vi.fn(async (path: string) => {
        if (path === '/api/team') throw new Error('boom');
        if (path === '/api/team/policy') return POLICY;
        return { data: [] };
      }),
    });
    renderPage({ api });
    const alert = await screen.findByText('Erro ao carregar a equipe.');
    expect(alert.closest('[role="alert"]')).not.toBeNull();
    expect(screen.getAllByRole('button', { name: /Tentar novamente/ }).length).toBeGreaterThan(0);
  });
});

describe('TeamPage: success', () => {
  it('renders the roster with policy labels, including product extras', async () => {
    renderPage();
    expect(await screen.findByText('Ana Admin')).toBeInTheDocument();
    expect(screen.getByText('Mo Derador')).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('Moderador').length).toBeGreaterThan(0));
    expect(screen.getByText('Você')).toBeInTheDocument();
    expect(screen.getAllByText('Ações').length).toBeGreaterThan(0);
  });

  it('renders the empty state', async () => {
    renderPage({ api: makeApi({ members: [] }) });
    expect(await screen.findByText('Nenhum membro encontrado.')).toBeInTheDocument();
  });
});

describe('TeamPage: removal is Core-only', () => {
  it('has no Remover action and links the note to Core /team', async () => {
    renderPage();
    await screen.findByText('Ana Admin');
    expect(screen.queryByRole('button', { name: /Remover/ })).toBeNull();
    const note = screen.getByTestId('team-remove-core-note');
    expect(note).toHaveTextContent('Para remover alguém da organização, use o NoctusAI Core.');
    expect(within(note).getByRole('link', { name: /NoctusAI Core/ })).toHaveAttribute(
      'href',
      'https://core.example.com/team',
    );
  });
});

describe('TeamPage: invite', () => {
  it('offers exactly the policy invitable roles, labelled', async () => {
    renderPage();
    await screen.findByText('Ana Admin');
    fireEvent.click(screen.getByRole('button', { name: /Convidar/ }));
    const select = (await screen.findByLabelText('Papel')) as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => [o.value, o.textContent]);
    expect(options).toEqual([
      ['admin', 'Administrador'],
      ['moderador', 'Moderador'],
    ]);
  });

  it('warns with email_motivo when the e-mail was not sent', async () => {
    const post = vi.fn(async () => ({
      data: { id: 'i2' },
      email_enviado: false,
      email_motivo: 'Servico de e-mail nao configurado',
    }));
    const { api } = renderPage({ api: makeApi({ post }) });
    await screen.findByText('Ana Admin');
    fireEvent.click(screen.getByRole('button', { name: /Convidar/ }));
    const select = (await screen.findByLabelText('Papel')) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'moderador' } });
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'mod@x.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar convite' }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/team/invite', { email: 'mod@x.com', role: 'moderador' }),
    );
    await waitFor(() => expect(toast.warning).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
    const [, opts] = (toast.warning as any).mock.calls[0];
    expect(opts.description).toContain('Servico de e-mail nao configurado');
  });

  it('confirms success only when email_enviado is true', async () => {
    renderPage();
    await screen.findByText('Ana Admin');
    fireEvent.click(screen.getByRole('button', { name: /Convidar/ }));
    await screen.findByLabelText('Papel');
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'a@x.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar convite' }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Convite enviado para a@x.com.'));
    expect(toast.warning).not.toHaveBeenCalled();
  });
});

describe('TeamPage: pending invitations', () => {
  it('lists invitations and cancels via DELETE', async () => {
    const { api } = renderPage();
    expect(await screen.findByText('novo@x.com')).toBeInTheDocument();
    const row = screen.getByText('novo@x.com').closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/team/invitations/i1'));
  });
});

describe('TeamPage: non-manager', () => {
  it('hides invite + invitations and never fetches them', async () => {
    const api = makeApi();
    renderPage({ api, user: MEMBER_USER });
    await screen.findByText('Ana Admin');
    expect(screen.queryByRole('button', { name: /Convidar/ })).toBeNull();
    expect(screen.queryByText('Convites pendentes')).toBeNull();
    expect((api.get as any).mock.calls.map((c: any[]) => c[0])).not.toContain('/api/team/invitations');
  });
});

describe('TeamPage: two-signal loading', () => {
  it('keeps the roster mounted during a refetch', async () => {
    let resolveSecond: (v: unknown) => void = () => {};
    let calls = 0;
    const api = makeApi({
      get: vi.fn((path: string) => {
        if (path === '/api/team') {
          calls += 1;
          if (calls === 1) return Promise.resolve({ data: MEMBERS });
          return new Promise((r) => {
            resolveSecond = r;
          });
        }
        if (path === '/api/team/policy') return Promise.resolve(POLICY);
        return Promise.resolve({ data: [] });
      }),
    });
    const { client } = renderPage({ api });
    await screen.findByText('Ana Admin');
    void client.invalidateQueries({ queryKey: TEAM_QUERY_KEYS.roster });
    await waitFor(() => expect(screen.getAllByLabelText('Atualizando').length).toBeGreaterThan(0));
    expect(screen.getByText('Ana Admin')).toBeInTheDocument();
    expect(screen.queryByLabelText('Carregando equipe')).toBeNull();
    resolveSecond({ data: MEMBERS });
  });
});
