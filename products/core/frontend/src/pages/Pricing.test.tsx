import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { Pricing } from './Pricing';
import { fakeHttp, renderWithBilling } from '../test/billing-harness';

afterEach(() => cleanup());

const CATALOG = {
  gateways: ['stripe', 'asaas'],
  plans: [{
    id: 'plan-0', nome: 'Gratuito', slug: 'free', audience: 'any', trial_days: 0,
    max_users: 1, max_products: 1, features: {},
    prices: [{ id: 'p0', billing_cycle: 'monthly', currency: 'BRL', amount_cents: 0 }],
  }, {
    id: 'plan-1', nome: 'Corretor', slug: 'corretor', audience: 'individual', trial_days: 7,
    max_users: -1, max_products: 2, features: { mais_popular: true, suporte_prioritario: true },
    prices: [
      { id: 'pm', billing_cycle: 'monthly', currency: 'BRL', amount_cents: 9900 },
      { id: 'py', billing_cycle: 'yearly', currency: 'BRL', amount_cents: 99000 },
    ],
  }],
};

function setup(subscribe: (body: any) => unknown) {
  const http = fakeHttp({
    'GET /api/billing/plans': () => ({ data: CATALOG }),
    'POST /api/billing/subscribe': subscribe,
  });
  const onRedirect = vi.fn();
  render(renderWithBilling(http, <Pricing onRedirect={onRedirect} />));
  return { http, onRedirect };
}

describe('Pricing', () => {
  it('subscribes with Stripe (yearly) and redirects to the checkout', async () => {
    const { http, onRedirect } = setup(() => ({
      data: { subscription_id: 's1', checkout_url: 'https://checkout.stripe.com/c/s1', gateway: 'stripe', mode: 'test', pix_qr: null },
    }));
    expect(await screen.findByText('Corretor')).toBeTruthy();
    expect(screen.getByText('7 dias grátis (cartão cadastrado no início)')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Anual/ }));
    expect(screen.getByText(/R\$\s*990,00/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Assinar' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continuar para o pagamento' }));
    await waitFor(() => expect(onRedirect).toHaveBeenCalledWith('https://checkout.stripe.com/c/s1'));
    const body = http.calls.find((c) => c.method === 'POST')!.body as any;
    expect(body).toMatchObject({ plan_price_id: 'py', gateway: 'stripe', billing_method: 'card' });
    expect(body.tax_id).toBeUndefined();
  });

  it('requires a CPF/CNPJ for Asaas and shows the Pix QR without redirecting', async () => {
    const { http, onRedirect } = setup(() => ({
      data: { subscription_id: 's2', checkout_url: 'https://asaas.test/i/pay_1', gateway: 'asaas', mode: 'test',
        pix_qr: { payload: '000201pix', encoded_image: 'aGVsbG8=' } },
    }));
    fireEvent.click(await screen.findByRole('button', { name: 'Assinar' }));
    fireEvent.click(screen.getByRole('button', { name: /Asaas/ }));
    fireEvent.click(screen.getByLabelText('Pix'));
    const go = screen.getByRole('button', { name: 'Continuar para o pagamento' }) as HTMLButtonElement;
    expect(go.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('CPF ou CNPJ'), { target: { value: '123.456.789-09' } });
    expect(go.disabled).toBe(false);
    fireEvent.click(go);
    expect(await screen.findByAltText('QR code Pix')).toBeTruthy();
    expect(onRedirect).not.toHaveBeenCalled();
    expect(http.calls.find((c) => c.method === 'POST')!.body).toMatchObject({
      plan_price_id: 'pm', gateway: 'asaas', billing_method: 'pix', tax_id: '12345678909',
    });
  });

  it('shows the backend refusal', async () => {
    setup(() => { throw new Error('Esta organização já tem uma assinatura em andamento para este produto.'); });
    fireEvent.click(await screen.findByRole('button', { name: 'Assinar' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continuar para o pagamento' }));
    expect((await screen.findByRole('alert')).textContent).toContain('assinatura em andamento');
  });

  it('keeps the free tier, popular highlight and feature list', async () => {
    const { http } = setup(() => ({ data: {} }));
    const free = await screen.findByRole('article', { name: 'Gratuito' });
    expect(within(free).getByText('Grátis', { exact: true })).toBeTruthy();
    fireEvent.click(within(free).getByRole('button', { name: 'Começar Grátis' }));
    expect(http.calls.some((c) => c.method === 'POST')).toBe(false);
    const paid = screen.getByRole('article', { name: 'Corretor' });
    expect(within(paid).getByText('Mais Popular')).toBeTruthy();
    expect(within(paid).getByText('Usuários ilimitados')).toBeTruthy();
    expect(within(paid).getByText('2 produtos')).toBeTruthy();
    expect(within(paid).getByText('Suporte prioritario')).toBeTruthy();
    expect(within(paid).queryByText(/mais popular/i, { selector: 'li' })).toBeNull();
    expect(within(free).queryByText('Mais Popular')).toBeNull();
  });

  it('says so when nothing is for sale', async () => {
    const http = fakeHttp({ 'GET /api/billing/plans': () => ({ data: { plans: [], gateways: [] } }) });
    render(renderWithBilling(http, <Pricing onRedirect={vi.fn()} />));
    expect(await screen.findByText('Nenhum plano disponível no momento.')).toBeTruthy();
  });
});
