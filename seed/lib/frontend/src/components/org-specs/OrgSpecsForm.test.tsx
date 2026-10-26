/**
 * `<OrgSpecsForm/>` + `createOrgSpecsHooks`: loading / error / empty / form, unsaved-draft notice,
 * save payload + cache commit, inline refusal with the server's `conflitos`, read-only mode, custom path.
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiError } from '../../api';
import type { ApiClient } from '../../api';
import { createOrgSpecsHooks, type OrgSpecsData } from './createOrgSpecsHooks';
import { OrgSpecsForm } from './OrgSpecsForm';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
afterEach(cleanup);

const DATA: OrgSpecsData = {
  agent_key: 'monica',
  declaradas: [
    { chave: 'quem_sou', rotulo: 'Quem eu sou', descricao: 'Apresentação.', tipo: 'texto', obrigatoria: true, exemplo: 'Psicanalista' },
    { chave: 'servicos', rotulo: 'Serviços', descricao: '', tipo: 'texto_longo', obrigatoria: false, exemplo: null },
  ],
  valores: [{ chave: 'servicos', valor: 'Análise individual' }],
  faltando: ['quem_sou'],
};

function setup(api: { get?: (...a: any[]) => any; put?: (...a: any[]) => any }, opts: Parameters<typeof createOrgSpecsHooks>[1] = {}, props: Partial<React.ComponentProps<typeof OrgSpecsForm>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const hooks = createOrgSpecsHooks(api as unknown as ApiClient, opts);
  render(
    <QueryClientProvider client={qc}>
      <OrgSpecsForm hooks={hooks} agentKey="monica" {...props} />
    </QueryClientProvider>,
  );
  return qc;
}

describe('OrgSpecsForm', () => {
  it('shows a skeleton while loading, never the empty state', () => {
    setup({ get: () => new Promise(() => {}) });
    expect(screen.getByTestId('org-specs-loading')).toBeInTheDocument();
    expect(screen.queryByText(/Nenhuma informação/)).toBeNull();
  });

  it('shows an honest error with retry', async () => {
    const get = vi.fn().mockRejectedValueOnce(new ApiError(503, 'agents indisponível')).mockResolvedValue(DATA);
    setup({ get });
    expect(await screen.findByText('agents indisponível')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Tentar novamente'));
    expect(await screen.findByTestId('spec-org-quem_sou')).toBeInTheDocument();
  });

  it('shows the empty state when the definition declares nothing', async () => {
    setup({ get: async () => ({ ...DATA, declaradas: [], valores: [], faltando: [] }) });
    expect(await screen.findByText(/Nenhuma informação foi pedida/)).toBeInTheDocument();
  });

  it('renders text vs long text, required/missing markers and values', async () => {
    setup({ get: async () => DATA });
    expect(await screen.findByTestId('specs-faltando')).toHaveTextContent('1 obrigatória');
    expect((screen.getByLabelText(/Quem eu sou/) as HTMLInputElement).tagName).toBe('INPUT');
    const longo = screen.getByLabelText(/Serviços/) as HTMLTextAreaElement;
    expect(longo.tagName).toBe('TEXTAREA');
    expect(longo.value).toBe('Análise individual');
    expect(screen.getByText('Exemplo: Psicanalista')).toBeInTheDocument();
  });

  it('says the draft is unsaved, PUTs every declared key and commits the saved view', async () => {
    const saved = { ...DATA, faltando: [], valores: [{ chave: 'quem_sou', valor: 'Mônica' }, { chave: 'servicos', valor: 'Análise individual' }] };
    let server = DATA; // the settle refetch must see what the PUT stored
    const put = vi.fn().mockImplementation(async () => (server = saved));
    const get = vi.fn().mockImplementation(async () => server);
    const qc = setup({ get, put });
    const save = await screen.findByTestId('specs-org-salvar');
    expect(save).toBeDisabled();
    expect(screen.queryByTestId('unsaved-changes-notice')).toBeNull();
    fireEvent.change(screen.getByLabelText(/Quem eu sou/), { target: { value: 'Mônica' } });
    expect(screen.getByTestId('unsaved-changes-notice')).toBeInTheDocument();
    fireEvent.click(save);
    await waitFor(() => expect(put).toHaveBeenCalledWith('/api/studio/agents/monica/specs', { valores: { quem_sou: 'Mônica', servicos: 'Análise individual' } }));
    await waitFor(() => expect(screen.queryByTestId('unsaved-changes-notice')).toBeNull());
    expect(qc.getQueryData(['org-specs', 'monica'])).toEqual(saved);
    expect(screen.getByText('Tudo preenchido')).toBeInTheDocument();
  });

  it('shows the refusal on the offending field with the locked-rule label, others stay clean', async () => {
    const err = new ApiError(422, 'servicos: contradiz uma regra fixa', { detail: 'servicos: contradiz uma regra fixa', code: 'x', conflitos: ['opt_out'] });
    setup({ get: async () => DATA, put: vi.fn().mockRejectedValue(err) }, {}, { conflictLabels: { opt_out: 'Pedido para parar' } });
    fireEvent.change(await screen.findByLabelText(/Serviços/), { target: { value: 'novo' } });
    fireEvent.click(screen.getByTestId('specs-org-salvar'));
    const box = await screen.findByTestId('spec-org-erro-servicos');
    expect(box).toHaveTextContent('contradiz uma regra fixa');
    expect(box).toHaveTextContent('Bloco fixo da plataforma: Pedido para parar');
    expect(screen.queryByTestId('spec-org-erro-quem_sou')).toBeNull();
  });

  it('is read-only without edit permission and uses a product proxy path', async () => {
    const get = vi.fn().mockResolvedValue(DATA);
    setup({ get }, { path: () => '/api/contexto', queryKey: (k) => ['monica', k, 'ctx'] }, { canEdit: false });
    expect(await screen.findByTestId('spec-org-quem_sou')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/api/contexto');
    expect(screen.queryByTestId('specs-org-salvar')).toBeNull();
    expect((screen.getByLabelText(/Quem eu sou/) as HTMLInputElement).readOnly).toBe(true);
  });
});
