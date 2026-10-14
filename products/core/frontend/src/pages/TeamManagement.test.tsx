/**
 * Team admin (multi-org S5, owner D2–D5 2026-10-14): org scope, move (transfer | add), per-member
 * product access, removal copy, and the contract's error codes in pt-BR. api/auth are
 * module-boundary mocks (house pattern); the seed organs render for real.
 */
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ApiError } from '@noctusai/lib';

const { get, post, put, patch, del, toastSuccess, toastError } = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), del: vi.fn(),
  toastSuccess: vi.fn(), toastError: vi.fn(),
}));

vi.mock('../lib/api', () => ({ api: { get, post, put, patch, delete: del } }));
vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }));
vi.mock('../components/layout/CoreHeader', () => ({ CoreHeader: () => null }));
vi.mock('../lib/auth-context', () => {
  const auth = {
    user: { id: 'me', nome: 'Eu', email: 'eu@x.com', role: 'user', org_id: 'A' },
    organization: { id: 'A', nome: 'Alfa' },
    isAdmin: false, loading: false, unavailable: false,
  };
  return { useAuth: () => auth };
});

import { TeamManagement } from './TeamManagement';
import { teamErrorMessage } from '../lib/team-errors';

const ROLES = [
  { id: 'r1', name: 'Proprietário', slug: 'owner', permissions: [], is_system: true },
  { id: 'r2', name: 'Administrador', slug: 'admin', permissions: [], is_system: true },
  { id: 'r3', name: 'Membro', slug: 'member', permissions: [], is_system: true },
];
const MEMBERS: Record<string, unknown[]> = {
  A: [
    { id: 'me', nome: 'Eu', email: 'eu@x.com', org_role: 'owner', created_at: '2026-10-01' },
    { id: 'u2', nome: 'Bia', email: 'bia@x.com', org_role: 'member', created_at: '2026-10-02' },
  ],
  B: [{ id: 'u3', nome: 'Caio', email: 'caio@x.com', org_role: 'member', created_at: '2026-10-03' }],
};
const memberAccess = (manageable: unknown[]) => ({
  has_access: true, product_slug: 'core', org: { id: 'A', nome: 'Alfa' },
  org_selection: {
    available: false, required: false, mfa_required: false, acting: false, org: null, home_org: null,
    selection_id: null, eligible_orgs: [], platform_role: null, manage_any_org: false, manageable_orgs: manageable,
  },
});
const STAFF_ACCESS = {
  ...memberAccess([]),
  org_selection: { ...memberAccess([]).org_selection, manage_any_org: true, platform_role: 'admin' },
};
const OWNER_A_ADMIN_B = memberAccess([
  { id: 'A', nome: 'Alfa', org_role: 'owner' },
  { id: 'B', nome: 'Beta', org_role: 'admin' },
]);

function routeGet(access: unknown, extra: Record<string, unknown> = {}) {
  get.mockImplementation(async (url: string) => {
    if (url in extra) {
      const v = extra[url];
      if (v instanceof Error) throw v;
      return v;
    }
    if (url === '/api/me/access') return access;
    if (url === '/api/roles') return { data: ROLES };
    if (url === '/api/organizations') return { data: [{ id: 'A', nome: 'Alfa' }, { id: 'B', nome: 'Beta' }, { id: 'C', nome: 'Gama' }] };
    const team = url.match(/^\/api\/team\?org_id=(\w+)$/);
    if (team) return { data: MEMBERS[team[1]] ?? [] };
    if (url.startsWith('/api/team/invitations')) return { data: [] };
    throw new Error(`unexpected GET ${url}`);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><TeamManagement /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const apiErr = (status: number, code: string, detail = 'x') => new ApiError(status, detail, { detail, code });

beforeEach(() => { vi.clearAllMocks(); });
afterEach(() => cleanup());

describe('Equipe — states', () => {
  it('shows a skeleton while members load, never the empty state', () => {
    get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByTestId('team-skeleton')).toBeInTheDocument();
    expect(screen.queryByText('Nenhum membro encontrado')).not.toBeInTheDocument();
  });

  it('members failure: error + retry, not an empty list', async () => {
    routeGet(OWNER_A_ADMIN_B, { '/api/team?org_id=A': new ApiError(500, 'boom') });
    renderPage();
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
    expect(screen.queryByText('Nenhum membro encontrado')).not.toBeInTheDocument();
  });

  it('a member who manages no other org: no org selector, no Mover/Acessos', async () => {
    routeGet(memberAccess([]));
    renderPage();
    expect(await screen.findByText('Bia')).toBeInTheDocument();
    expect(screen.queryByTestId('team-org-select')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Mover' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Acessos' })).toBeNull();
    expect(get).toHaveBeenCalledWith('/api/team?org_id=A');
  });
});

describe('Equipe — org scope (D2)', () => {
  it('lists the orgs the viewer manages and re-scopes every list with ?org_id=', async () => {
    routeGet(OWNER_A_ADMIN_B);
    renderPage();
    const select = await screen.findByTestId('team-org-select');
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['Alfa', 'Beta']);
    expect(await screen.findByText('Bia')).toBeInTheDocument();
    fireEvent.change(select, { target: { value: 'B' } });
    expect(await screen.findByText('Caio')).toBeInTheDocument();
    expect(screen.queryByText('Bia')).toBeNull();
    expect(get).toHaveBeenCalledWith('/api/team?org_id=B');
    expect(get).toHaveBeenCalledWith('/api/team/invitations?org_id=B');
  });

  it('platform staff (manage_any_org) may open ANY org', async () => {
    routeGet({ ...OWNER_A_ADMIN_B, org_selection: { ...OWNER_A_ADMIN_B.org_selection, manage_any_org: true, platform_role: 'admin', manageable_orgs: [] } });
    renderPage();
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/organizations'));
    const select = await screen.findByTestId('team-org-select');
    await waitFor(() => expect(within(select).getAllByRole('option')).toHaveLength(3));
  });
});

describe('Equipe — mover usuário (D3)', () => {
  async function openMove() {
    routeGet(OWNER_A_ADMIN_B);
    renderPage();
    const row = await screen.findByTestId('member-row-u2');
    fireEvent.click(within(row).getByRole('button', { name: 'Mover' }));
    return screen.findByRole('dialog', { name: 'Mover usuário' });
  }

  it('the actor chooses target, role and mode EACH time (no mode preselected); add keeps both', async () => {
    post.mockResolvedValue({ data: { mode: 'add', org_role: 'member', source_ended: false } });
    const dialog = await openMove();
    const submit = within(dialog).getByRole('button', { name: 'Mover' });
    expect(submit).toBeDisabled();
    expect(within(dialog).getAllByRole('radio').every((r) => !(r as HTMLInputElement).checked)).toBe(true);
    // only the OTHER managed org is a target
    const target = within(dialog).getByTestId('move-target');
    expect(within(target).getAllByRole('option').map((o) => o.textContent)).toEqual(['Selecione…', 'Beta']);
    fireEvent.change(target, { target: { value: 'B' } });
    // admin in Beta: owner is above the actor's role there
    const role = within(dialog).getByTestId('move-role');
    expect(within(role).queryByRole('option', { name: 'Proprietário' })).toBeNull();
    fireEvent.change(role, { target: { value: 'member' } });
    expect(submit).toBeDisabled(); // mode still unchosen
    fireEvent.click(within(dialog).getByLabelText(/Adicionar \(mantém as duas\)/));
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/team/move', {
      user_id: 'u2', source_org_id: 'A', target_org_id: 'B', role: 'member', mode: 'add',
    }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining('continua em Alfa')));
  });

  it('an org owner of the target is NOT offered owner (P1: staff only)', async () => {
    routeGet(memberAccess([{ id: 'A', nome: 'Alfa', org_role: 'owner' }, { id: 'B', nome: 'Beta', org_role: 'owner' }]));
    renderPage();
    fireEvent.click(within(await screen.findByTestId('member-row-u2')).getByRole('button', { name: 'Mover' }));
    const dialog = await screen.findByRole('dialog', { name: 'Mover usuário' });
    fireEvent.change(within(dialog).getByTestId('move-target'), { target: { value: 'B' } });
    expect(within(within(dialog).getByTestId('move-role')).queryByRole('option', { name: 'Proprietário' })).toBeNull();
  });

  it('platform staff are offered owner in the move and in the row role selector (P1)', async () => {
    routeGet(STAFF_ACCESS);
    renderPage();
    const row = await screen.findByTestId('member-row-u2');
    expect(within(within(row).getByRole('combobox', { name: 'Papel de Bia' })).getByRole('option', { name: 'Proprietário' }))
      .toBeInTheDocument();
    fireEvent.click(await within(row).findByRole('button', { name: 'Mover' }));
    const dialog = await screen.findByRole('dialog', { name: 'Mover usuário' });
    fireEvent.change(within(dialog).getByTestId('move-target'), { target: { value: 'B' } });
    expect(within(within(dialog).getByTestId('move-role')).getByRole('option', { name: 'Proprietário' })).toBeInTheDocument();
  });

  it('an org owner\'s row role selector does not offer owner (P1)', async () => {
    routeGet(OWNER_A_ADMIN_B);
    renderPage();
    const row = await screen.findByTestId('member-row-u2');
    expect(within(within(row).getByRole('combobox', { name: 'Papel de Bia' })).queryByRole('option', { name: 'Proprietário' }))
      .toBeNull();
  });

  it.each([
    ['last_owner', 409, /último proprietário/],
    ['role_above_actor', 403, /acima do seu/],
    ['forbidden', 403, /nas duas organizações/],
    ['already_member', 409, /já é membro da organização de destino/],
    ['membership_suspended', 403, /está suspensa/],
    ['not_a_member', 404, /não é mais membro ativo/],
    ['same_org', 400, /precisa ser diferente/],
    ['org_not_found', 404, /Organização não encontrada/],
    ['invalid_mode', 400, /transferida ou adicionada/],
  ])('maps %s to a pt-BR message and keeps the dialog open', async (code, status, text) => {
    post.mockRejectedValue(apiErr(status as number, code));
    const dialog = await openMove();
    fireEvent.change(within(dialog).getByTestId('move-target'), { target: { value: 'B' } });
    fireEvent.change(within(dialog).getByTestId('move-role'), { target: { value: 'member' } });
    fireEvent.click(within(dialog).getByLabelText(/Transferir \(sai da org atual\)/));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mover' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(text);
    expect(screen.getByRole('dialog', { name: 'Mover usuário' })).toBeInTheDocument();
  });

  it('422 (schema) reads as invalid data', async () => {
    post.mockRejectedValue(new ApiError(422, 'Field required', { error: { code: 'VALIDATION_ERROR', message: 'Field required' } }));
    const dialog = await openMove();
    fireEvent.change(within(dialog).getByTestId('move-target'), { target: { value: 'B' } });
    fireEvent.change(within(dialog).getByTestId('move-role'), { target: { value: 'member' } });
    fireEvent.click(within(dialog).getByLabelText(/Transferir/));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mover' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Dados inválidos');
  });
});

describe('Equipe — acesso a produtos (D5)', () => {
  const ACCESS_URL = '/api/team/u2/product-access?org_id=A';
  const products = (blocked: boolean, extra: Record<string, unknown> = { can_edit: true, target_is_staff: false }) => (
    { data: { user_id: 'u2', org_id: 'A', ...extra, products: [
      { product_id: 'p1', slug: 'social-wiring', nome: 'Social Wiring', blocked, blocked_at: null, blocked_by: null },
    ] } });

  it('an org admin sees the list read-only (P5: only the owner or staff change it)', async () => {
    routeGet(OWNER_A_ADMIN_B, { [ACCESS_URL]: products(false, { can_edit: false, target_is_staff: false }) });
    renderPage();
    fireEvent.click(within(await screen.findByTestId('member-row-u2')).getByRole('button', { name: 'Acessos' }));
    expect(await screen.findByRole('switch', { name: 'Acesso a Social Wiring' })).toBeDisabled();
    expect(screen.getByTestId('product-access-readonly')).toHaveTextContent('Somente o proprietário');
  });

  it('NoctusAI staff are never blockable: no usable switch (P3)', async () => {
    routeGet(OWNER_A_ADMIN_B, { [ACCESS_URL]: products(false, { can_edit: true, target_is_staff: true }) });
    renderPage();
    fireEvent.click(within(await screen.findByTestId('member-row-u2')).getByRole('button', { name: 'Acessos' }));
    expect(await screen.findByRole('switch', { name: 'Acesso a Social Wiring' })).toBeDisabled();
    expect(screen.getByTestId('product-access-staff')).toHaveTextContent('equipe NoctusAI');
  });

  it.each([
    ['owner_grant_forbidden', 'Somente a equipe NoctusAI pode conceder o papel de proprietário.'],
    ['cannot_block_staff', 'A equipe NoctusAI não pode ser bloqueada de nenhum produto.'],
  ])('%s has its pt-BR message', (code, text) => {
    expect(teamErrorMessage(apiErr(403, code), 'x')).toBe(text);
  });

  it('lists the licensed products with a switch; turning it off blocks', async () => {
    routeGet(OWNER_A_ADMIN_B, { [ACCESS_URL]: products(false) });
    put.mockResolvedValue({ data: { changed: true, blocked: true } });
    renderPage();
    fireEvent.click(within(await screen.findByTestId('member-row-u2')).getByRole('button', { name: 'Acessos' }));
    const sw = await screen.findByRole('switch', { name: 'Acesso a Social Wiring' });
    expect(sw).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(sw);
    await waitFor(() => expect(put).toHaveBeenCalledWith('/api/team/u2/product-access/social-wiring?org_id=A', { blocked: true }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining('não tem mais acesso')));
  });

  it('not_licensed is reported in pt-BR', async () => {
    routeGet(OWNER_A_ADMIN_B, { [ACCESS_URL]: products(false) });
    put.mockRejectedValue(apiErr(409, 'not_licensed'));
    renderPage();
    fireEvent.click(within(await screen.findByTestId('member-row-u2')).getByRole('button', { name: 'Acessos' }));
    fireEvent.click(await screen.findByRole('switch', { name: 'Acesso a Social Wiring' }));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('A organização não tem licença ativa deste produto.'));
  });

  it('empty: the org has no licensed products', async () => {
    routeGet(OWNER_A_ADMIN_B, { [ACCESS_URL]: { data: { products: [] } } });
    renderPage();
    fireEvent.click(within(await screen.findByTestId('member-row-u2')).getByRole('button', { name: 'Acessos' }));
    expect(await screen.findByText('Esta organização não tem produtos licenciados.')).toBeInTheDocument();
  });
});

describe('Equipe — remover (D4)', () => {
  it('says the profile is kept (a personal org when this was their only one) and calls DELETE scoped to the org', async () => {
    routeGet(OWNER_A_ADMIN_B);
    del.mockResolvedValue({ message: 'ok' });
    renderPage();
    fireEvent.click(within(await screen.findByTestId('member-row-u2')).getByRole('button', { name: 'Remover' }));
    expect(await screen.findByTestId('remove-keeps-profile')).toHaveTextContent('organização pessoal própria');
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar remoção' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/api/team/u2?org_id=A'));
  });

  async function removeBiaWith(data: unknown) {
    routeGet(OWNER_A_ADMIN_B);
    del.mockResolvedValue({ message: 'Membro removido com sucesso', data });
    renderPage();
    fireEvent.click(within(await screen.findByTestId('member-row-u2')).getByRole('button', { name: 'Remover' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar remoção' }));
  }

  it('sole-org member: the success message says a personal org now holds the account (S5b)', async () => {
    await removeBiaWith({ removed: true, profile_moved_to: 'P', personal_org_id: 'P' });
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith(
      'Bia foi removido(a) de Alfa. Como esta era a única organização da pessoa, a conta foi mantida em uma '
      + 'organização pessoal própria, com o histórico preservado.',
    ));
  });

  it('profile moved to another org the viewer knows: names it', async () => {
    await removeBiaWith({ removed: true, profile_moved_to: 'B', personal_org_id: null });
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith(
      'Bia foi removido(a) de Alfa. A conta passa a usar Beta como organização principal.',
    ));
  });

  it('profile moved to an org the viewer cannot see: says so without inventing a name', async () => {
    await removeBiaWith({ removed: true, profile_moved_to: 'Z', personal_org_id: null });
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith(
      'Bia foi removido(a) de Alfa. A conta passa a usar outra organização de que a pessoa participa.',
    ));
  });

  it('this was not their profile org: nothing moved', async () => {
    await removeBiaWith({ removed: true, profile_moved_to: null, personal_org_id: null });
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith(
      'Bia foi removido(a) de Alfa. A pessoa continua nas outras organizações de que participa.',
    ));
  });
});
