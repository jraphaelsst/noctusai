import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StoreProfileForm } from './StoreProfileForm';
import { createCommerceHooks } from './hooks';
import { ApiError } from '../api';
import { makeApi, wrapperFor, VALID_CNPJ } from './testUtils';
import type { StoreProfile } from './types';

afterEach(cleanup);

const profile: StoreProfile = {
  org_id: 'org',
  version: 3,
  legal_name: 'Loja LTDA',
  trade_name: 'Loja',
  cnpj: '11222333000181',
  tax_regime: 'simples',
  tax_treatment: {},
  locale: 'pt-BR',
  currency: 'BRL',
  brand_tokens: { primary: '#112233' },
  address: {},
  contact_email: 'a@b.co',
  contact_phone: '1133334444',
};

function mount(initial: StoreProfile | null, extra: Record<string, unknown> = {}) {
  const api = makeApi();
  api.get.mockResolvedValue({ data: initial });
  Object.entries(extra).forEach(([k, v]) => ((api as any)[k].mockImplementation(v)));
  const hooks = createCommerceHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper><StoreProfileForm hooks={hooks} /></Wrapper>);
  return api;
}

describe('StoreProfileForm', () => {
  it('shows a skeleton first, then the masked CNPJ', async () => {
    mount(profile);
    expect(screen.getByTestId('store-profile-loading')).toBeInTheDocument();
    expect(await screen.findByDisplayValue(VALID_CNPJ)).toBeInTheDocument();
  });

  it('blocks save and shows an error for a CNPJ with bad check digits', async () => {
    const user = userEvent.setup();
    const api = mount(profile);
    const cnpj = await screen.findByDisplayValue(VALID_CNPJ);
    await user.clear(cnpj);
    await user.type(cnpj, '11222333000182');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText(/CNPJ inválido/)).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
  });

  it('saves with expected_version and digits-only CNPJ', async () => {
    const user = userEvent.setup();
    const api = mount(profile, { put: () => Promise.resolve({ data: { ...profile, version: 4 } }) });
    await screen.findByDisplayValue(VALID_CNPJ);
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const body = api.put.mock.calls[0][1] as Record<string, unknown>;
    expect(body.expected_version).toBe(3);
    expect(body.cnpj).toBe('11222333000181');
    expect(await screen.findByText('Salvo')).toBeInTheDocument();
  });

  it('409 shows the "someone else saved; reload" banner and reload refetches', async () => {
    const user = userEvent.setup();
    const api = mount(profile, {
      put: () => Promise.reject(new ApiError(409, 'versao_conflitante', { error: { code: 'versao_conflitante', message: 'x' } })),
    });
    await screen.findByDisplayValue(VALID_CNPJ);
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText(/Outra pessoa salvou/)).toBeInTheDocument();
    const before = api.get.mock.calls.length;
    await user.click(screen.getByRole('button', { name: 'Recarregar' }));
    await waitFor(() => expect(api.get.mock.calls.length).toBeGreaterThan(before));
  });

  it('lookup prefills names from the registry', async () => {
    const user = userEvent.setup();
    const api = mount(null, { post: () => Promise.resolve({ data: { legal_name: 'ACME SA', trade_name: 'Acme' } }) });
    const cnpj = await screen.findByLabelText(/^CNPJ/);
    await user.type(cnpj, '11222333000181');
    await user.click(screen.getByRole('button', { name: 'Preencher pelo CNPJ' }));
    expect(await screen.findByDisplayValue('ACME SA')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/commerce/profile/cnpj-lookup', { cnpj: '11222333000181' });
  });

  it('platform_fee_bps only appears for platform admins', async () => {
    mount(profile);
    await screen.findByDisplayValue(VALID_CNPJ);
    expect(screen.queryByText(/Taxa da plataforma/)).not.toBeInTheDocument();
  });

  it('shows an error state with retry when the load fails', async () => {
    const api = makeApi();
    api.get.mockRejectedValue(new ApiError(500, 'down'));
    const Wrapper = wrapperFor();
    render(<Wrapper><StoreProfileForm hooks={createCommerceHooks(api)} /></Wrapper>);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });
});
