/**
 * Leads — list + stats strip + filter. Fixture field names copied verbatim
 * from `15-api-contract.md` §1/§3. Stage-change and the note composer are
 * covered in `LeadDetail.test.tsx` (the detail page owns those actions).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Leads } from './Leads';
import { fakeHttp, renderWithWebsite } from '../../../test/website-harness';
import type { Lead } from '../../../lib/website';

afterEach(() => cleanup());

let mockAuth = { isAdmin: true };
vi.mock('../../../lib/auth-context', () => ({
  useAuth: () => mockAuth,
}));
afterEach(() => { mockAuth = { isAdmin: true }; });

const STATS = { new_today: 2, new_7d: 9, by_source: { waitlist: 6, contact: 3 }, by_stage: { novo: 5 }, events_7d: { page_view: 40 } };

function lead(overrides: Partial<Lead> = {}): Lead {
  return {
    id: 'lead-1', created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z',
    source: 'waitlist', name: 'Ana Souza', email: 'ana@example.com', phone_e164: '+5511988887777',
    company: null, profile: 'smb', product_interest: [], message: null, locale: 'pt-BR',
    utm: {}, landing_path: '/', referrer: null,
    consent: { marketing: true, text_version: 'v1', at: '2026-09-20T10:00:00Z', ip_hash: 'abc' },
    stage: 'novo', owner_user_id: null, owner_agent: null, score: null,
    next_action: null, next_action_at: null, lost_reason: null, dedupe_key: 'ana@example.com',
    ...overrides,
  };
}

describe('Leads — list', () => {
  it('shows a skeleton, then the stats strip and table', async () => {
    const http = fakeHttp({
      'GET /api/admin/website/stats': () => ({ data: STATS }),
      'GET /api/admin/website/leads': () => ({ data: [lead()], total: 1 }),
    });
    render(renderWithWebsite(http, <Leads />));
    expect(screen.queryByText('Ana Souza')).toBeNull();
    expect(await screen.findByText('Ana Souza')).toBeTruthy();
    expect(screen.getByText('Novos hoje')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
  });

  it('shows a real empty state, never a lying skeleton or stale text', async () => {
    const http = fakeHttp({
      'GET /api/admin/website/stats': () => ({ data: STATS }),
      'GET /api/admin/website/leads': () => ({ data: [], total: 0 }),
    });
    render(renderWithWebsite(http, <Leads />));
    expect(await screen.findByText('Nenhum lead encontrado.')).toBeTruthy();
  });

  it('surfaces a load error', async () => {
    const http = fakeHttp({
      'GET /api/admin/website/stats': () => ({ data: STATS }),
      'GET /api/admin/website/leads': () => { throw new Error('[500] boom'); },
    });
    render(renderWithWebsite(http, <Leads />));
    expect((await screen.findByText(/Não foi possível carregar os leads/))).toBeTruthy();
  });

  it('hides the CSV export button for non-admins', async () => {
    mockAuth = { isAdmin: false };
    const http = fakeHttp({
      'GET /api/admin/website/stats': () => ({ data: STATS }),
      'GET /api/admin/website/leads': () => ({ data: [lead()], total: 1 }),
    });
    render(renderWithWebsite(http, <Leads />));
    await screen.findByText('Ana Souza');
    expect(screen.queryByRole('button', { name: /Exportar CSV/ })).toBeNull();
  });
});

describe('Leads — filter', () => {
  it('re-fetches with the stage filter applied', async () => {
    const http = fakeHttp({
      'GET /api/admin/website/stats': () => ({ data: STATS }),
      'GET /api/admin/website/leads': () => ({ data: [lead()], total: 1 }),
    });
    render(renderWithWebsite(http, <Leads />));
    await screen.findByText('Ana Souza');

    fireEvent.change(screen.getByLabelText('Filtrar por estágio'), { target: { value: 'qualificado' } });
    await waitFor(() =>
      expect(http.calls.some((c) => c.method === 'GET' && c.path.endsWith('/leads') && c.params?.stage === 'qualificado'))
        .toBe(true));

    expect(screen.getByText('Estágio: Qualificado')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Remover filtro Estágio: Qualificado' }));
    await waitFor(() => expect(screen.queryByText('Estágio: Qualificado')).toBeNull());
  });

  it('re-fetches with the search term applied', async () => {
    const http = fakeHttp({
      'GET /api/admin/website/stats': () => ({ data: STATS }),
      'GET /api/admin/website/leads': () => ({ data: [lead()], total: 1 }),
    });
    render(renderWithWebsite(http, <Leads />));
    await screen.findByText('Ana Souza');

    fireEvent.change(screen.getByLabelText('Buscar por nome, e-mail, telefone ou empresa'), { target: { value: 'ana' } });
    await waitFor(() =>
      expect(http.calls.some((c) => c.method === 'GET' && c.path.endsWith('/leads') && c.params?.q === 'ana')).toBe(true));
  });
});
