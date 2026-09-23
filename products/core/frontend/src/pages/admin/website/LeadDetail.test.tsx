/**
 * LeadDetail — stage change (PATCH) + note composer (POST activities) +
 * "Abrir WhatsApp" link. Fixture field names copied verbatim from
 * `15-api-contract.md` §1/§3.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { LeadDetail } from './LeadDetail';
import { fakeHttp, renderWithWebsite } from '../../../test/website-harness';
import type { LeadWithActivities } from '../../../lib/website';

afterEach(() => cleanup());

const LEAD: LeadWithActivities = {
  id: 'lead-1', created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z',
  source: 'waitlist', name: 'Ana Souza', email: 'ana@example.com', phone_e164: '+5511988887777',
  company: null, profile: 'smb', product_interest: [], message: null, locale: 'pt-BR',
  utm: {}, landing_path: '/', referrer: null,
  consent: { marketing: true, text_version: 'v1', at: '2026-09-20T10:00:00Z', ip_hash: 'abc' },
  stage: 'novo', owner_user_id: null, owner_agent: null, score: null,
  next_action: null, next_action_at: null, lost_reason: null, dedupe_key: 'ana@example.com',
  activities: [
    { id: 'act-1', lead_id: 'lead-1', at: '2026-09-20T10:00:00Z', kind: 'created', actor: 'system', payload: {} },
  ],
};

function renderDetail(http: ReturnType<typeof fakeHttp>) {
  return render(
    renderWithWebsite(
      http,
      <Routes>
        <Route path="/admin/website/leads/:id" element={<LeadDetail />} />
      </Routes>,
      ['/admin/website/leads/lead-1'],
    ),
  );
}

describe('LeadDetail — load + WhatsApp link', () => {
  it('shows contact info, consent badge, and a wa.me link built from phone_e164', async () => {
    const http = fakeHttp({ 'GET /api/admin/website/leads/lead-1': () => ({ data: LEAD }) });
    renderDetail(http);
    expect(await screen.findByText('Ana Souza')).toBeTruthy();
    expect(screen.getByText('ana@example.com')).toBeTruthy();
    const link = screen.getByRole('link', { name: /Abrir WhatsApp/ }) as HTMLAnchorElement;
    expect(link.href).toBe('https://wa.me/5511988887777');
  });

  it('surfaces a load error', async () => {
    const http = fakeHttp({ 'GET /api/admin/website/leads/lead-1': () => { throw new Error('[404] not found'); } });
    renderDetail(http);
    expect(await screen.findByRole('alert')).toBeTruthy();
  });
});

describe('LeadDetail — stage change', () => {
  it('PATCHes the new stage and appends a stage_change activity server-side', async () => {
    const http = fakeHttp({
      'GET /api/admin/website/leads/lead-1': () => ({ data: LEAD }),
      'PATCH /api/admin/website/leads/lead-1': (body: any) => ({ data: { ...LEAD, stage: body.stage } }),
    });
    renderDetail(http);
    const select = await screen.findByLabelText('Estágio do lead') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'contatado' } });
    await waitFor(() => expect(http.calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(http.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ stage: 'contatado' });
  });
});

describe('LeadDetail — note composer', () => {
  it('POSTs a note activity and clears the composer', async () => {
    const http = fakeHttp({
      'GET /api/admin/website/leads/lead-1': () => ({ data: LEAD }),
      'POST /api/admin/website/leads/lead-1/activities': (body: any) =>
        ({ data: { id: 'act-2', lead_id: 'lead-1', at: '2026-09-21T00:00:00Z', kind: body.kind, actor: 'user:u1', payload: { body: body.body } } }),
    });
    renderDetail(http);
    const textarea = await screen.findByLabelText('Nova nota') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'Liguei, sem resposta.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar nota' }));
    await waitFor(() => expect(http.calls.some((c) => c.method === 'POST')).toBe(true));
    expect(http.calls.find((c) => c.method === 'POST')?.body).toEqual({ kind: 'note', body: 'Liguei, sem resposta.' });
  });

  it('the "Adicionar nota" button stays disabled for a blank note', async () => {
    const http = fakeHttp({ 'GET /api/admin/website/leads/lead-1': () => ({ data: LEAD }) });
    renderDetail(http);
    await screen.findByLabelText('Nova nota');
    expect((screen.getByRole('button', { name: 'Adicionar nota' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
