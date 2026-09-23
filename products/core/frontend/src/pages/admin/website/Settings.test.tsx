/**
 * Settings — load / save / 409-conflict / marketing-disabled-fields.
 *
 * Fixture field names copied verbatim from `15-api-contract.md` §2/§3 (never
 * guessed) — a contract-shaped fetch fixture per the brief. `useAuth` is
 * substituted via `vi.mock` (house pattern, see `CoreLayout.test.tsx`); the
 * HTTP layer is the real `createWebsiteApi` behind a recording fake
 * (`website-harness.tsx`) — no mocking of our own modules for that part.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiError } from '@noctusai/lib';
import { Settings } from './Settings';
import { fakeHttp, renderWithWebsite } from '../../../test/website-harness';
import type { WebsiteSettings } from '../../../lib/website';

afterEach(() => cleanup());

let mockAuth = { isMarketing: false };
vi.mock('../../../lib/auth-context', () => ({
  useAuth: () => mockAuth,
}));

const SETTINGS: WebsiteSettings = {
  site_enabled: true,
  signup_enabled: true,
  whatsapp: { number_e164: '+5511999999999', default_message: { pt: 'Oi!', en: 'Hi!' }, float_enabled: true },
  sections: {
    audiences: true, products: true, custom_builds: true, trust: true, social_proof: false,
    pricing: true, news: false, faq: true, hero_update_card: false,
  },
  products: [
    { slug: 'erp-imobiliario', visible: true, order: 0, state: 'disponivel' },
    { slug: 'orbity', visible: true, order: 1, state: 'lista_de_espera' },
  ],
  trust_items: [],
  social_proof_items: [],
  faq: [],
  tracking: { plausible_domain: null, ga4_id: null, meta_pixel_id: null },
};

function settingsVersion(version = 3) {
  return { version, settings: SETTINGS, created_at: '2026-09-20T10:00:00Z', created_by: 'admin-1' };
}

afterEach(() => { mockAuth = { isMarketing: false }; });

describe('Settings — load', () => {
  it('shows a skeleton while pending, then the loaded settings', async () => {
    const http = fakeHttp({ 'GET /api/admin/website/settings': () => ({ data: settingsVersion() }) });
    render(renderWithWebsite(http, <Settings />));
    expect(screen.queryByText('Configurações do site')).toBeNull();
    expect(await screen.findByText('Configurações do site')).toBeTruthy();
    expect((screen.getByLabelText('Site habilitado') as HTMLInputElement).checked).toBe(true);
  });

  it('surfaces a load error', async () => {
    const http = fakeHttp({ 'GET /api/admin/website/settings': () => { throw new Error('[500] boom'); } });
    render(renderWithWebsite(http, <Settings />));
    expect((await screen.findByRole('alert')).textContent).toContain('500');
  });
});

describe('Settings — save', () => {
  it('enables Salvar only once dirty, and PUTs the whole settings + expected_version', async () => {
    const http = fakeHttp({
      'GET /api/admin/website/settings': () => ({ data: settingsVersion(3) }),
      'PUT /api/admin/website/settings': (body: any) => ({ data: { ...settingsVersion(4), settings: body.settings } }),
    });
    render(renderWithWebsite(http, <Settings />));
    const save = await screen.findByRole('button', { name: 'Salvar alterações' });
    expect((save as HTMLButtonElement).disabled).toBe(true);

    const whatsappInput = screen.getByPlaceholderText('+5511999999999') as HTMLInputElement;
    fireEvent.change(whatsappInput, { target: { value: '+5511888888888' } });
    expect((save as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(save);
    await waitFor(() => expect(http.calls.some((c) => c.method === 'PUT')).toBe(true));
    const putCall = http.calls.find((c) => c.method === 'PUT')!;
    expect((putCall.body as any).expected_version).toBe(3);
    expect((putCall.body as any).settings.whatsapp.number_e164).toBe('+5511888888888');
  });

  it('409 shows the contract message and Recarregar discards the local draft', async () => {
    let getCount = 0;
    const http = fakeHttp({
      'GET /api/admin/website/settings': () => { getCount += 1; return { data: settingsVersion(3) }; },
      'PUT /api/admin/website/settings': () => { throw new ApiError(409, 'version_conflict'); },
    });
    render(renderWithWebsite(http, <Settings />));
    const whatsappInput = await screen.findByPlaceholderText('+5511999999999') as HTMLInputElement;
    fireEvent.change(whatsappInput, { target: { value: '+5511888888888' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }));

    expect(await screen.findByText('Outra pessoa salvou antes — recarregue.')).toBeTruthy();
    const getsBefore = getCount;
    fireEvent.click(screen.getByRole('button', { name: 'Recarregar' }));
    await waitFor(() => expect(getCount).toBe(getsBefore + 1));
    await waitFor(() =>
      expect((screen.getByPlaceholderText('+5511999999999') as HTMLInputElement).value).toBe('+5511999999999'));
  });
});

describe('Settings — marketing role', () => {
  it('disables site_enabled and signup_enabled for a marketing user', async () => {
    mockAuth = { isMarketing: true };
    const http = fakeHttp({ 'GET /api/admin/website/settings': () => ({ data: settingsVersion() }) });
    render(renderWithWebsite(http, <Settings />));
    expect((await screen.findByLabelText('Site habilitado') as unknown as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText('Cadastro habilitado') as HTMLInputElement).disabled).toBe(true);
  });

  it('leaves other fields editable for marketing', async () => {
    mockAuth = { isMarketing: true };
    const http = fakeHttp({ 'GET /api/admin/website/settings': () => ({ data: settingsVersion() }) });
    render(renderWithWebsite(http, <Settings />));
    const whatsappInput = await screen.findByPlaceholderText('+5511999999999') as HTMLInputElement;
    expect(whatsappInput.disabled).toBe(false);
  });
});
