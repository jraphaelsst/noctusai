/** "Créditos e uso": balance, product → feature breakdown, the buy flow (cache write), and complete states. */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { deferred } from '../../test/billing-harness';
import { fakeHttp, renderWithCredits, USAGE, WALLET } from '../../test/credits-harness';

vi.mock('@noctusai/lib/design-system', async (orig) => ({
  ...(await orig<object>()),
  useEffectiveSSOContext: () => ({ orgId: 'org-1' }),
}));

import { CreditosUso } from './CreditosUso';

afterEach(cleanup);

const walletBody = (over: Record<string, unknown> = {}) => ({
  data: { wallet: { ...WALLET, ...over }, entries: [], purchases: [], gateways: ['asaas'] },
});

describe('CreditosUso', () => {
  it('shows the balance in credits and R$, and usage per product then feature', async () => {
    const http = fakeHttp({ 'GET /api/credits/wallet': () => walletBody(), 'GET /api/credits/usage': () => ({ data: USAGE }) });
    render(renderWithCredits(http, <CreditosUso />));
    expect(await screen.findByText(/12\.500 créditos/)).toBeInTheDocument();
    expect(screen.getByText('R$ 125,00')).toBeInTheDocument();
    const table = await screen.findByRole('table');
    expect(within(table).getByText('erp-imobiliario')).toBeInTheDocument();
    expect(within(table).getByText('resumo')).toBeInTheDocument();
    expect(within(table).getByText('legenda')).toBeInTheDocument();
    expect(screen.getByText(/ainda não cobrada/)).toBeInTheDocument();
  });

  it('never shows provider cost or margin', async () => {
    const http = fakeHttp({ 'GET /api/credits/wallet': () => walletBody(), 'GET /api/credits/usage': () => ({ data: USAGE }) });
    render(renderWithCredits(http, <CreditosUso />));
    await screen.findByRole('table');
    expect(screen.queryByText(/custo|margem/i)).not.toBeInTheDocument();
  });

  it('says the AI is blocked when the prepaid balance is exhausted', async () => {
    const http = fakeHttp({
      'GET /api/credits/wallet': () => walletBody({ balance_credits: 0, balance_brl: 0, blocked: true }),
      'GET /api/credits/usage': () => ({ data: USAGE }),
    });
    render(renderWithCredits(http, <CreditosUso />));
    expect(await screen.findByRole('alert')).toHaveTextContent(/bloqueadas/);
  });

  it('shows an empty state when there is no usage', async () => {
    const http = fakeHttp({
      'GET /api/credits/wallet': () => walletBody(),
      'GET /api/credits/usage': () => ({ data: { ...USAGE, per_product: [], daily: [], products: [],
        totals: { ...USAGE.totals, calls: 0, pending_calls: 0 } } }),
    });
    render(renderWithCredits(http, <CreditosUso />));
    expect((await screen.findAllByText('Nenhum uso de IA no período.')).length).toBeGreaterThan(0);
  });

  it('shows an error state when the wallet cannot be read', async () => {
    const http = fakeHttp({
      'GET /api/credits/wallet': () => { throw new Error('boom'); },
      'GET /api/credits/usage': () => ({ data: USAGE }),
    });
    render(renderWithCredits(http, <CreditosUso />));
    expect(await screen.findByText(/Não foi possível carregar o saldo: boom/)).toBeInTheDocument();
  });

  it('buying opens a PIX charge and lists it as pending without waiting for a reload', async () => {
    const charge = deferred<unknown>();
    const http = fakeHttp({
      'GET /api/credits/wallet': () => walletBody(),
      'GET /api/credits/usage': () => ({ data: USAGE }),
      'POST /api/credits/purchase': () => charge.promise,
    });
    render(renderWithCredits(http, <CreditosUso />));
    await screen.findByText(/12\.500 créditos/);
    http.routes['GET /api/credits/wallet'] = () => new Promise(() => {}); // the settle refetch never answers
    fireEvent.change(screen.getByLabelText('CPF ou CNPJ'), { target: { value: '12345678909' } });
    fireEvent.click(screen.getByRole('button', { name: 'Comprar créditos' }));
    expect(await screen.findByRole('button', { name: 'Gerando cobrança…' })).toBeDisabled();
    charge.resolve({ data: { purchase_id: 'p1', credits: 10000, amount_cents: 10000, checkout_url: 'https://pay/x',
      gateway: 'asaas', pix_qr: { payload: 'PIXCODE', encoded_image: 'aGk=' } } });
    expect(await screen.findByText('PIXCODE')).toBeInTheDocument();
    expect(await screen.findByText('Aguardando pagamento')).toBeInTheDocument();
    const post = http.calls.find((c) => c.method === 'POST')!;
    expect(post.body).toEqual({ amount_brl: '100.00', gateway: 'asaas', billing_method: 'pix', tax_id: '12345678909' });
  });

  it('hides the buy section for a BYOK org', async () => {
    const http = fakeHttp({
      'GET /api/credits/wallet': () => walletBody({ mode: 'byok' }),
      'GET /api/credits/usage': () => ({ data: USAGE }),
    });
    render(renderWithCredits(http, <CreditosUso />));
    await screen.findByText(/Chave própria/);
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Comprar créditos' })).not.toBeInTheDocument());
  });
});
