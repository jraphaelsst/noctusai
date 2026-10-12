/** Consent rules of the checkout form (CONTRACT §4 / Decreto 7.962 / CDC art. 49). */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CheckoutForm } from './CheckoutForm';
import { createCommerceHooks } from './hooks';
import { ApiError } from '../api';
import { makeApi, wrapperFor, VALID_CPF } from './testUtils';
import type { Quote, StorefrontLegal } from './types';

afterEach(cleanup);

const legal: StorefrontLegal = { terms_version: 't3', privacy_version: 'p2', withdrawal_text: 'Direito de arrependimento em 7 dias.' };
const quote = (over: Partial<Quote> = {}): Quote => ({
  lines: [{ offer_id: 'o1', title: 'Curso', unit_price_cents: 9900, qty: 1, total_cents: 9900, product_type: 'digital', fulfillment_type: 'digital_delivery' }],
  subtotal_cents: 9900,
  discount_cents: 0,
  total_cents: 9900,
  currency: 'BRL',
  requires_immediate_delivery_waiver: false,
  ...over,
});

function setup(q: Quote, checkoutImpl?: () => Promise<unknown>) {
  const api = makeApi();
  api.post.mockImplementation((path: string) => {
    if (path.endsWith('/checkout')) return (checkoutImpl ?? (() => Promise.resolve({ data: { order_token: 'tok', status: 'pending_payment' } })))();
    return Promise.resolve({ data: q });
  });
  const hooks = createCommerceHooks(api);
  const onSuccess = vi.fn();
  const Wrapper = wrapperFor();
  render(
    <Wrapper>
      <CheckoutForm hooks={hooks} request={{ items: [{ offer_id: 'o1', qty: 1 }] }} quote={q} legal={legal} onSuccess={onSuccess} />
    </Wrapper>,
  );
  return { api, onSuccess };
}

async function fillBuyer(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/Nome completo/), 'Maria Souza');
  await user.type(screen.getByLabelText(/E-mail/), 'maria@example.com');
  await user.type(screen.getByLabelText(/CPF ou CNPJ/), VALID_CPF);
  await user.type(screen.getByLabelText(/Telefone/), '11987654321');
}

const checkoutCalls = (api: ReturnType<typeof makeApi>) => api.post.mock.calls.filter((c) => String(c[0]).endsWith('/checkout'));

describe('CheckoutForm consent rules', () => {
  it('marketing opt-in is unchecked by default; terms and privacy are required', async () => {
    const user = userEvent.setup();
    const { api, onSuccess } = setup(quote());
    expect(screen.getByLabelText(/Quero receber novidades/)).not.toBeChecked();
    await fillBuyer(user);
    await user.click(screen.getByRole('button', { name: /Pagar/ }));
    expect(await screen.findByText('É necessário aceitar os Termos de uso')).toBeInTheDocument();
    expect(screen.getByText('É necessário aceitar a Política de privacidade')).toBeInTheDocument();
    expect(checkoutCalls(api)).toHaveLength(0);
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('shows the waiver only when the quote requires it, and blocks submit without it', async () => {
    const user = userEvent.setup();
    const { api } = setup(quote({ requires_immediate_delivery_waiver: true }));
    expect(screen.getByLabelText(/entrega imediata do conteúdo digital/)).toBeInTheDocument();
    await fillBuyer(user);
    await user.click(screen.getByLabelText(/Termos de uso/));
    await user.click(screen.getByLabelText(/Política de privacidade/));
    await user.click(screen.getByRole('button', { name: /Pagar/ }));
    expect(await screen.findByText(/concordar com a entrega imediata/)).toBeInTheDocument();
    expect(checkoutCalls(api)).toHaveLength(0);
  });

  it('does not render the waiver when not required', () => {
    setup(quote());
    expect(screen.queryByLabelText(/entrega imediata do conteúdo digital/)).not.toBeInTheDocument();
  });

  it('submits normalized buyer data with versions, marketing=false and waiver=false when not required', async () => {
    const user = userEvent.setup();
    const { api, onSuccess } = setup(quote());
    await fillBuyer(user);
    await user.click(screen.getByLabelText(/Termos de uso/));
    await user.click(screen.getByLabelText(/Política de privacidade/));
    await user.click(screen.getByRole('button', { name: /Pagar/ }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith({ order_token: 'tok', status: 'pending_payment' }));
    const body = checkoutCalls(api)[0][1] as Record<string, any>;
    expect(body.buyer).toEqual({ name: 'Maria Souza', email: 'maria@example.com', doc: '52998224725', phone: '11987654321' });
    expect(body.consents).toEqual({ terms_version: 't3', privacy_version: 'p2', marketing: false, immediate_delivery_waiver: false });
    expect(body.payment_method).toBe('pix');
    expect(body.items).toEqual([{ offer_id: 'o1', qty: 1 }]);
  });

  it('sends waiver=true and marketing=true when ticked', async () => {
    const user = userEvent.setup();
    const { api } = setup(quote({ requires_immediate_delivery_waiver: true }));
    await fillBuyer(user);
    await user.click(screen.getByLabelText(/Termos de uso/));
    await user.click(screen.getByLabelText(/Política de privacidade/));
    await user.click(screen.getByLabelText(/Quero receber novidades/));
    await user.click(screen.getByLabelText(/entrega imediata do conteúdo digital/));
    await user.click(screen.getByLabelText('Boleto'));
    await user.click(screen.getByRole('button', { name: /Pagar/ }));
    await waitFor(() => expect(checkoutCalls(api)).toHaveLength(1));
    const body = checkoutCalls(api)[0][1] as Record<string, any>;
    expect(body.consents).toMatchObject({ marketing: true, immediate_delivery_waiver: true });
    expect(body.payment_method).toBe('boleto');
  });

  it('rejects an invalid CPF/CNPJ before calling the server', async () => {
    const user = userEvent.setup();
    const { api } = setup(quote());
    await user.type(screen.getByLabelText(/Nome completo/), 'Maria Souza');
    await user.type(screen.getByLabelText(/E-mail/), 'maria@example.com');
    await user.type(screen.getByLabelText(/CPF ou CNPJ/), '11111111111');
    await user.type(screen.getByLabelText(/Telefone/), '11987654321');
    await user.click(screen.getByLabelText(/Termos de uso/));
    await user.click(screen.getByLabelText(/Política de privacidade/));
    await user.click(screen.getByRole('button', { name: /Pagar/ }));
    expect(await screen.findByText('CPF/CNPJ inválido')).toBeInTheDocument();
    expect(checkoutCalls(api)).toHaveLength(0);
  });

  it('shows a server aceite_obrigatorio 422 inline', async () => {
    const user = userEvent.setup();
    setup(quote(), () => Promise.reject(new ApiError(422, 'aceite', { error: { code: 'aceite_obrigatorio', message: 'aceite' } })));
    await fillBuyer(user);
    await user.click(screen.getByLabelText(/Termos de uso/));
    await user.click(screen.getByLabelText(/Política de privacidade/));
    await user.click(screen.getByRole('button', { name: /Pagar/ }));
    expect(await screen.findByText(/aceites obrigatórios não foram confirmados/)).toBeInTheDocument();
  });

  it('requires an address for shippable lines', async () => {
    const user = userEvent.setup();
    const { api } = setup(
      quote({ lines: [{ offer_id: 'o1', title: 'Caneca', unit_price_cents: 5000, qty: 1, total_cents: 5000, product_type: 'physical', fulfillment_type: 'shipping' }] }),
    );
    expect(screen.getByText('Endereço de entrega')).toBeInTheDocument();
    await fillBuyer(user);
    await user.click(screen.getByLabelText(/Termos de uso/));
    await user.click(screen.getByLabelText(/Política de privacidade/));
    await user.click(screen.getByRole('button', { name: /Pagar/ }));
    expect((await screen.findAllByText('Campo obrigatório')).length).toBeGreaterThan(0);
    expect(checkoutCalls(api)).toHaveLength(0);
  });
});
