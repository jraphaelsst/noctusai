/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ConfirmProvider } from '@noctusai/lib/components';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn(), download: vi.fn() } }));
vi.mock('../../lib/api', () => ({ api }));

import { TemplatesAdmin } from './TemplatesAdmin';

const meta = {
  kinds: [
    { key: 'design_system', label: 'Design system', scopes: [{ scope: '_platform', label: 'Plataforma', templates: 1, sources: 0 }] },
    { key: 'agent', label: 'Agentes e prompts', scopes: [{ scope: 'agents', label: 'Agents', templates: 0, sources: 5 }] },
    { key: 'message', label: 'Mensagens', scopes: [] },
    { key: 'document', label: 'Documentos', scopes: [] },
    { key: 'repo_workflow', label: 'Repositório e workflow', scopes: [] },
  ],
  formats: ['json', 'markdown', 'text'], products: [{ slug: 'agents', label: 'Agents' }], platform_scope: '_platform',
};
const row = (over: Record<string, unknown> = {}) => ({
  id: 't1', product: null, kind: 'design_system', key: 'org-design-system', title: 'Design system da organização', description: '',
  format: 'json', version: 1, status: 'active', created_at: '2026-10-30T10:00:00Z', updated_at: '2026-10-30T10:00:00Z', activated_at: '2026-10-30T10:00:00Z',
  versions: 1, latest_version: 1, has_draft: false, ...over,
});
const sources = [{ kind: 'agent', product: 'agents', title: 'Bia — especificação', description: 'Prompt da Bia', path: 'products/agents/backend/app/agents/bia/BIA.md' }];

function routes(over: Record<string, unknown> = {}) {
  api.get.mockImplementation(async (path: string) => {
    for (const [k, v] of Object.entries(over)) if (k.endsWith('?') ? path.startsWith(k) : path === k) { if (v instanceof Error) throw v; return v; }
    if (path === '/api/admin/templates/meta') return { data: meta };
    if (path.startsWith('/api/admin/templates/sources')) return { data: sources };
    if (path === '/api/admin/templates/t1') return { data: { ...row(), body: '{"schema": "noctus.brand-tokens/v1"}' } };
    if (path === '/api/admin/templates/t1/history') return { data: [row()] };
    if (path.startsWith('/api/admin/templates?')) return { data: [row()] };
    throw new Error(`unmocked ${path}`);
  });
}

function mount(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}><ConfirmProvider><MemoryRouter initialEntries={[path]}><TemplatesAdmin /></MemoryRouter></ConfirmProvider></QueryClientProvider>,
  );
  return qc;
}

beforeEach(() => { vi.resetAllMocks(); });
afterEach(cleanup);

describe('TemplatesAdmin', () => {
  it('shows loading, then the kind -> scope nav and the scope list', async () => {
    routes();
    mount('/admin/templates/design_system/_platform');
    expect(screen.getByTestId('templates-loading')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('templates-list')).toBeInTheDocument());
    expect(screen.getByRole('navigation', { name: 'Templates' })).toBeInTheDocument();
    expect(screen.getByText('Design system da organização')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Agentes e prompts/ })).toBeInTheDocument();
  });

  it('renders an empty state that points at the Fontes', async () => {
    routes({ '/api/admin/templates?': { data: [] } });
    mount('/admin/templates/agent/agents');
    await waitFor(() => expect(screen.getByTestId('templates-empty')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Bia — especificação')).toBeInTheDocument());
    expect(screen.getByText('products/agents/backend/app/agents/bia/BIA.md')).toBeInTheDocument();
  });

  it('renders an error state with retry when the list fails', async () => {
    routes({ '/api/admin/templates?': new Error('boom') });
    mount('/admin/templates/design_system');
    await waitFor(() => expect(screen.getAllByRole('button', { name: /tentar|novamente/i }).length).toBeGreaterThan(0));
  });

  it('the Fontes page lists every discovered source grouped by kind, read-only', async () => {
    routes();
    mount('/admin/templates/fontes');
    await waitFor(() => expect(screen.getByTestId('template-sources')).toBeInTheDocument());
    expect(screen.getByText('Agentes e prompts', { selector: 'h4' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /salvar|ativar/i })).toBeNull();
  });

  it('opens the editor with history; invalid JSON blocks saving', async () => {
    routes();
    mount('/admin/templates/design_system/_platform?t=t1');
    const body = await screen.findByLabelText('Conteúdo');
    await waitFor(() => expect(screen.getByTestId('template-history')).toBeInTheDocument());
    fireEvent.change(body, { target: { value: '{oops' } });
    expect(screen.getByTestId('body-error').textContent).toMatch(/JSON inválido/);
    expect(screen.getByRole('button', { name: /salvar como nova versão/i })).toBeDisabled();
  });

  it('editing an active version posts a PATCH and then the new draft opens', async () => {
    routes();
    api.patch.mockResolvedValue({ data: { ...row({ id: 't2', version: 2, status: 'draft' }), body: '{"schema": "noctus.brand-tokens/v1", "radius": "1rem"}' } });
    mount('/admin/templates/design_system/_platform?t=t1');
    const body = await screen.findByLabelText('Conteúdo');
    fireEvent.change(body, { target: { value: '{"schema": "noctus.brand-tokens/v1", "radius": "1rem"}' } });
    fireEvent.click(screen.getByRole('button', { name: /salvar como nova versão/i }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/admin/templates/t1', expect.objectContaining({ format: 'json' })));
  });

  it('activating a draft writes the cache while the request is in flight', async () => {
    routes({ '/api/admin/templates/t1': { data: { ...row({ status: 'draft', version: 2 }), body: '{}' } },
             '/api/admin/templates?': { data: [row({ status: 'draft', version: 2 })] } });
    let resolve!: (v: unknown) => void;
    api.post.mockReturnValue(new Promise((r) => { resolve = r; }));
    mount('/admin/templates/design_system/_platform?t=t1');
    fireEvent.click(await screen.findByRole('button', { name: 'Ativar' }));
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Ativar' }).length).toBe(2)); // confirm dialog
    fireEvent.click(screen.getAllByRole('button', { name: 'Ativar' })[1]);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/admin/templates/t1/activate'));
    resolve({ data: row({ status: 'active', version: 2 }) });
    await waitFor(() => expect(screen.getAllByText('Ativo').length).toBeGreaterThan(0));
  });
});
