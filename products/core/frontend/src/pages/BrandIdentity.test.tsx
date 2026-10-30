import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ConfirmProvider } from '@noctusai/lib/components';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockUpload = vi.fn();
let admin = true;

vi.mock('../lib/api', () => ({ api: { get: mockGet, post: mockPost, patch: mockPatch, upload: mockUpload } }));
vi.mock('@noctusai/lib/design-system', async (orig) => ({
  ...(await orig<object>()),
  useEffectiveSSOContext: () => ({ orgId: 'o1' }),
  useIsOrgAdmin: () => admin,
}));

const tokens = {
  light: { background: '0 0% 100%', foreground: '0 0% 10%', primary: '220 90% 50%', 'primary-foreground': '0 0% 100%' },
  dark: { background: '0 0% 5%', foreground: '0 0% 95%', primary: '220 90% 60%', 'primary-foreground': '0 0% 5%' },
  radius: '0.5rem',
  fonts: { heading: { family: 'Lora', weights: [500], source: 'google' } },
};
const detail = { id: 'd1', version: 2, status: 'draft', created_at: '2026-10-29T10:00:00Z', activated_at: null, tokens, brand_book: '# Marca', voice: {}, assets: {}, validation: { warnings: ['primary: contraste 3.1:1'] } };

function route(over: Record<string, unknown> = {}) {
  mockGet.mockImplementation(async (path: string) => {
    if (path in over) { const v = over[path]; if (v instanceof Error) throw v; return v; }
    if (path === '/api/brand/current') return { source: 'platform', identity_id: null, version: null, tokens, assets: {}, updated_at: null };
    if (path === '/api/brand/identities') return [{ id: 'd1', version: 2, status: 'draft', created_at: '2026-10-29T10:00:00Z', activated_at: null }];
    if (path === '/api/brand/identities/d1') return { data: detail };
    throw new Error(`unmocked ${path}`);
  });
}

async function mount() {
  const { BrandIdentity } = await import('./BrandIdentity');
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}><ConfirmProvider><MemoryRouter><BrandIdentity /></MemoryRouter></ConfirmProvider></QueryClientProvider>,
  );
  return qc;
}

beforeEach(() => { vi.resetAllMocks(); admin = true; });

describe('BrandIdentity page', () => {
  it('shows a skeleton, then the platform default, the draft editor, warnings and history', async () => {
    route();
    await mount();
    expect(screen.getByTestId('brand-loading')).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('brand-source').textContent).toMatch(/Padrão NoctusAI/));
    await waitFor(() => expect(screen.getByTestId('brand-draft-editor')).toBeTruthy());
    expect(screen.getByTestId('contrast-warnings').textContent).toMatch(/3.1:1/);
    expect(screen.getByTestId('brand-history').textContent).toMatch(/Versão 2/);
    expect(screen.getByLabelText('Cor primary')).toBeTruthy();
  });

  it('non-admins see a refusal, never the editor', async () => {
    admin = false;
    route();
    await mount();
    expect(screen.getByRole('alert').textContent).toMatch(/owners e admins/);
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('a failed current read shows the error branch, not an empty preview', async () => {
    route({ '/api/brand/current': new Error('down') });
    await mount();
    await waitFor(() => expect(screen.getByText('Não foi possível carregar a identidade em uso')).toBeTruthy());
  });

  it('empty org: no versions, invites the upload', async () => {
    route({ '/api/brand/identities': [] });
    await mount();
    await waitFor(() => expect(screen.getAllByText(/Envie o material da marca/).length).toBeGreaterThan(0));
  });

  it('editing a token marks the draft unsaved and saving PATCHes it', async () => {
    route();
    mockPatch.mockResolvedValue({ data: { ...detail } });
    await mount();
    const input = await screen.findByLabelText('Valor primary');
    fireEvent.change(input, { target: { value: '10 50% 40%' } });
    expect(screen.getByTestId('unsaved-changes-notice')).toBeTruthy();
    fireEvent.click(screen.getByText('Salvar rascunho'));
    await waitFor(() => expect(mockPatch).toHaveBeenCalled());
    expect((mockPatch.mock.calls[0][1] as any).tokens.light.primary).toBe('10 50% 40%');
  });

  it('an invalid triplet blocks saving', async () => {
    route();
    await mount();
    fireEvent.change(await screen.findByLabelText('Valor primary'), { target: { value: 'red' } });
    expect((screen.getByText('Salvar rascunho') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole('alert').textContent).toMatch(/H S% L%/);
  });

  it('refuses svg client-side and shows why', async () => {
    route();
    await mount();
    const input = await screen.findByTestId('brand-file-input');
    fireEvent.change(input, { target: { files: [new File(['<svg/>'], 'logo.svg')] } });
    expect(screen.getByText(/SVG não é aceito/)).toBeTruthy();
    expect((screen.getByText('Gerar identidade') as HTMLButtonElement).disabled).toBe(true);
  });
});
