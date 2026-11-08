/** AdminProducts public-site controls: No site switch, Destaque column, ordered panel, confirm-on-hide, descricao_publica field. */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ConfirmProvider } from '@noctusai/lib/components';

const { mockGet, mockPatch } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPatch: vi.fn() }));
vi.mock('../../lib/api', () => ({ api: { get: mockGet, patch: mockPatch, post: vi.fn(), delete: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { AdminProducts } from './AdminProducts';

afterEach(cleanup);

const row = (id: string, nome: string, over: object = {}) => ({
  id, nome, slug: id, descricao: null, icone: 'Box', url_base: `https://${id}.x`, cor: '#111111',
  ativo: true, deploy_scope: 'live', created_at: '2026-01-01',
  exibir_no_site: true, destaque_no_site: null, descricao_publica: 'Texto', ...over,
});
let DATA: any[];

beforeEach(() => {
  vi.clearAllMocks();
  DATA = [row('alfa', 'Alfa', { destaque_no_site: 1 }), row('beta', 'Beta', { destaque_no_site: 2 }), row('gama', 'Gama')];
  mockGet.mockImplementation(async (path: string) => {
    if (path.startsWith('/api/products?')) return { data: DATA };
    return { data: [], deployed: {} };
  });
  mockPatch.mockImplementation(async (path: string, body: object) => ({ data: { ...DATA.find(p => path.endsWith(p.id)), ...body } }));
});

const renderPage = () => render(<ConfirmProvider><AdminProducts /></ConfirmProvider>);

describe('AdminProducts site controls', () => {
  it('lists the featured panel in order with n/6', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Destaques no site (2/6)' })).toBeInTheDocument();
    const items = within(screen.getByRole('list')).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Alfa');
    expect(items[1]).toHaveTextContent('Beta');
  });

  it('hiding a featured product asks for confirmation and keeps it when declined', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('switch', { name: 'Alfa no site' }));
    expect(await screen.findByText(/destaque nº 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Manter no site' }));
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it('shows the server refusal inline when turning No site on is refused', async () => {
    DATA[2] = row('gama', 'Gama', { exibir_no_site: false, descricao_publica: null });
    mockPatch.mockRejectedValueOnce(new Error('Escreva a descrição pública antes de mostrar o produto no site.'));
    renderPage();
    fireEvent.click(await screen.findByRole('switch', { name: 'Gama no site' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Escreva a descrição pública');
  });

  it('refuses a 7th featured product without a request', async () => {
    DATA = ['a', 'b', 'c', 'd', 'e', 'f'].map((id, i) => row(id, id.toUpperCase(), { destaque_no_site: i + 1 }));
    DATA.push(row('g', 'G'));
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Destacar G no site' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Já há 6 destaques. Remova um antes de adicionar outro.');
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it('edit modal has the public description and saves it', async () => {
    renderPage();
    await waitFor(() => screen.getByText('Gama'));
    const edits = screen.getAllByRole('button', { name: /editar/i });
    fireEvent.click(edits[0]);
    const field = await screen.findByLabelText(/Descrição pública/);
    fireEvent.change(field, { target: { value: 'Nova' } });
    fireEvent.click(screen.getByRole('button', { name: /salvar|atualizar/i }));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(expect.stringMatching(/^\/api\/products\//), expect.objectContaining({ descricao_publica: 'Nova' })));
  });
});
