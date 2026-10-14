/** P4 money + fiscal organs: refund (idempotency, em andamento), money panel gating, installments, fiscal, picker, checkout parcelas. */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RefundDialog } from './RefundDialog';
import { OrderMoneyPanel } from './OrderMoneyPanel';
import { InstallmentsSettings, percentToBps, bpsToPercent } from './InstallmentsSettings';
import { FiscalSettingsForm } from './FiscalSettingsForm';
import { InstallmentPicker } from './InstallmentPicker';
import { CheckoutForm } from './CheckoutForm';
import { createCommerceHooks } from './hooks';
import { refundableCents } from './moneyMath';
import { ApiError } from '../api';
import { makeApi, wrapperFor, VALID_CPF } from './testUtils';
import { NFSE_CUTOVER_PHRASE, type FiscalView } from './fiscalTypes';
import type { InstallmentOption, Order, OrderRefund, Quote, StoreProfile } from './types';

afterEach(cleanup);

const charge = { id: 'c1', order_id: 'o1', attempt: 1, gateway: 'asaas', payment_method: 'credit_card' as const, installment_count: 3, amount_cents: 10000, status: 'paid' as const, created_at: '2026-10-14T10:00:00Z', closed_at: null };
const refund = (over: Partial<OrderRefund> = {}): OrderRefund => ({ id: 'r1', order_id: 'o1', charge_id: 'c1', amount_cents: 2500, reason: 'defeito', status: 'done', gateway_refund_id: null, requested_by: null, created_at: '2026-10-14T11:00:00Z', done_at: '2026-10-14T11:01:00Z', ...over });
const order = (over: Partial<Order> = {}): Order => ({
  id: 'o1', token: 't', customer_id: null, status: 'paid', subtotal_cents: 10000, discount_cents: 0, total_cents: 10000, currency: 'BRL', coupon_id: null,
  payment_method: 'credit_card', gateway: 'asaas', gateway_charge_id: 'g', checkout_url: null, pix_qr: null, expires_at: null, paid_at: '2026-10-14T10:05:00Z', platform_fee_cents: 0,
  items: [], events: [], charges: [charge], refunds: [], reminders: [], ...over,
});

describe('moneyMath', () => {
  it('refundable = paid charge (interest included) minus every non-failed refund', () => {
    expect(refundableCents(order({ charges: [{ ...charge, amount_cents: 10800 }], refunds: [refund({ amount_cents: 800 }), refund({ id: 'r2', status: 'requested', amount_cents: 1000 }), refund({ id: 'r3', status: 'failed', amount_cents: 5000 })] }))).toBe(9000);
  });
});

describe('RefundDialog', () => {
  function mount(o: Order, post: (path: string, body: unknown, opts?: { headers?: Record<string, string> }) => Promise<unknown>) {
    const api = makeApi();
    api.post.mockImplementation(post);
    const Wrapper = wrapperFor();
    render(<Wrapper><RefundDialog hooks={createCommerceHooks(api)} open onClose={() => undefined} order={o} /></Wrapper>);
    return api;
  }

  it('full refund sends no amount and an Idempotency-Key; a requested refund reads "em andamento"', async () => {
    const user = userEvent.setup();
    const api = mount(order(), () => Promise.resolve({ data: refund({ status: 'requested', amount_cents: 10000, done_at: null }) }));
    expect(screen.getByTestId('refund-balance')).toHaveTextContent('Reembolsável: R$ 100,00');
    await user.type(screen.getByLabelText(/Motivo/), 'cliente desistiu');
    await user.click(screen.getByRole('button', { name: 'Reembolsar' }));
    expect(await screen.findByTestId('refund-in-progress')).toHaveTextContent('em andamento');
    const [path, body, opts] = api.post.mock.calls[0];
    expect(path).toBe('/api/commerce/orders/o1/refunds');
    expect(body).toEqual({ reason: 'cliente desistiu' });
    expect(opts.headers['Idempotency-Key']).toMatch(/.{8,}/);
  });

  it('partial refund sends cents, validates against the balance and the reason', async () => {
    const user = userEvent.setup();
    const api = mount(order(), () => Promise.resolve({ data: refund({ amount_cents: 3000 }) }));
    await user.click(screen.getByLabelText('Reembolso parcial'));
    await user.type(screen.getByLabelText(/Valor a reembolsar/), '150,00');
    await user.type(screen.getByLabelText(/Motivo/), 'parcial');
    await user.click(screen.getByRole('button', { name: 'Reembolsar' }));
    expect(await screen.findByText('O valor excede o saldo reembolsável.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    const amount = screen.getByLabelText(/Valor a reembolsar/);
    await user.clear(amount);
    await user.type(amount, '30,00');
    await user.click(screen.getByRole('button', { name: 'Reembolsar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0][1]).toEqual({ amount_cents: 3000, reason: 'parcial' });
    expect(await screen.findByText(/Reembolso de R\$ 30,00 concluído/)).toBeInTheDocument();
  });

  it('a retry of the SAME input re-sends the SAME key; editing the input starts a new attempt', async () => {
    const user = userEvent.setup();
    const api = mount(order(), vi.fn().mockRejectedValueOnce(new ApiError(502, 'Não foi possível consultar o gateway agora.')).mockResolvedValue({ data: refund() }));
    await user.type(screen.getByLabelText(/Motivo/), 'abc');
    await user.click(screen.getByRole('button', { name: 'Reembolsar' }));
    expect(await screen.findByText(/consultar o gateway/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Reembolsar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[1][2].headers['Idempotency-Key']).toBe(api.post.mock.calls[0][2].headers['Idempotency-Key']);
  });

  it('lists the refund history of the order', () => {
    mount(order({ refunds: [refund(), refund({ id: 'r2', status: 'requested', amount_cents: 1000 })] }), () => Promise.resolve({}));
    const table = screen.getByTestId('refund-history');
    expect(within(table).getByText('Concluído')).toBeInTheDocument();
    expect(within(table).getByText('Em andamento')).toBeInTheDocument();
  });
});

describe('OrderMoneyPanel', () => {
  function mount(o: Order, isAdmin: boolean) {
    const api = makeApi();
    api.get.mockResolvedValue({ data: [] });
    const Wrapper = wrapperFor();
    render(<Wrapper><OrderMoneyPanel hooks={createCommerceHooks(api)} order={o} isAdmin={isAdmin} /></Wrapper>);
    return api;
  }
  it('shows charges with parcelas and hides admin actions from staff', async () => {
    mount(order({ reminders: [{ order_id: 'o1', kind: 'before_expiry', sent_at: '2026-10-14T09:00:00Z' }] }), false);
    expect(await screen.findByText('Nenhuma nota fiscal emitida.')).toBeInTheDocument();
    expect(screen.getByText('3x')).toBeInTheDocument();
    expect(screen.getByText(/Antes de vencer/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Reembolsar/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Emitir' })).toBeNull();
  });
  it('offers refund + invoice issue to an admin; no refund once nothing is refundable', async () => {
    const api = mount(order(), true);
    expect(await screen.findByRole('button', { name: 'Reembolsar…' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Emitir' })).toBeInTheDocument();
    cleanup();
    mount(order({ refunds: [refund({ amount_cents: 10000 })] }), true);
    await screen.findByText('Nenhuma nota fiscal emitida.');
    expect(screen.queryByRole('button', { name: 'Reembolsar…' })).toBeNull();
    expect(api.get).toHaveBeenCalled();
  });
  it('shows a skeleton first, then the invoices error with retry', async () => {
    const api = makeApi();
    api.get.mockRejectedValue(new ApiError(500, 'boom'));
    const Wrapper = wrapperFor();
    render(<Wrapper><OrderMoneyPanel hooks={createCommerceHooks(api)} order={order()} /></Wrapper>);
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });
});

const profile: StoreProfile = {
  org_id: 'org', version: 5, legal_name: 'Loja LTDA', trade_name: 'Loja', cnpj: '11222333000181', tax_regime: 'simples', tax_treatment: {}, locale: 'pt-BR',
  currency: 'BRL', brand_tokens: {}, address: {}, contact_email: 'a@b.co', contact_phone: '1133334444',
};

describe('InstallmentsSettings', () => {
  it('percent <-> bps conversion', () => {
    expect(percentToBps('1,99')).toBe(199);
    expect(percentToBps('20')).toBe(2000);
    expect(percentToBps('20,01')).toBeNull();
    expect(percentToBps('abc')).toBeNull();
    expect(bpsToPercent(199)).toBe('1,99');
  });
  function mount(p: StoreProfile | null, isAdmin = true) {
    const api = makeApi();
    api.get.mockResolvedValue({ data: p });
    api.put.mockResolvedValue({ data: { ...p, version: 6 } });
    const Wrapper = wrapperFor();
    render(<Wrapper><InstallmentsSettings hooks={createCommerceHooks(api)} isAdmin={isAdmin} /></Wrapper>);
    return api;
  }
  it('defaults 12x / 3x sem juros / platform rate; saves the whole profile with null rate', async () => {
    const user = userEvent.setup();
    const api = mount(profile);
    await screen.findByLabelText('Máximo de parcelas');
    expect(screen.getByLabelText('Máximo de parcelas')).toHaveValue('12');
    expect(screen.getByLabelText('Parcelas sem juros (até)')).toHaveValue('3');
    await user.selectOptions(screen.getByLabelText('Máximo de parcelas'), '6');
    await user.click(screen.getByRole('button', { name: 'Salvar parcelamento' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(api.put.mock.calls[0][1]).toMatchObject({ legal_name: 'Loja LTDA', installments_max: 6, installments_interest_free: 3, installment_interest_monthly_bps: null, expected_version: 5 });
  });
  it('a custom rate is sent in bps and validated', async () => {
    const user = userEvent.setup();
    const api = mount({ ...profile, installments_max: 10, installments_interest_free: 2, installment_interest_monthly_bps: 250 });
    const pct = await screen.findByLabelText('Taxa mensal (%)');
    expect(pct).toHaveValue('2,50');
    await user.clear(pct);
    await user.type(pct, '25');
    await user.click(screen.getByRole('button', { name: 'Salvar parcelamento' }));
    expect(await screen.findByText(/taxa entre 0 e 20/)).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
    await user.clear(pct);
    await user.type(pct, '1,5');
    await user.click(screen.getByRole('button', { name: 'Salvar parcelamento' }));
    await waitFor(() => expect(api.put.mock.calls[0][1]).toMatchObject({ installment_interest_monthly_bps: 150, installments_max: 10 }));
  });
  it('interest-free above the maximum is refused client-side', async () => {
    const user = userEvent.setup();
    const api = mount({ ...profile, installments_max: 2, installments_interest_free: 2 });
    await user.selectOptions(await screen.findByLabelText('Máximo de parcelas'), '1');
    await user.click(screen.getByRole('button', { name: 'Salvar parcelamento' }));
    expect(await screen.findByText(/não podem passar do máximo/)).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
  });
  it('is read-only for non-admins and says so; skeleton while loading; hint without a profile', async () => {
    mount(profile, false);
    expect(screen.getByTestId('installments-loading')).toBeInTheDocument();
    expect(await screen.findByText(/Somente administradores/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Salvar parcelamento' })).toBeNull();
    cleanup();
    mount(null);
    expect(await screen.findByText(/Salve o perfil da loja/)).toBeInTheDocument();
  });
});

const fiscal = (over: Partial<FiscalView> = {}): FiscalView => ({
  cnpj: '11222333000181', tax_regime: 'lucro_presumido', inscricao_municipal: '123', inscricao_estadual: null, municipio_ibge: '3550308', invoice_company_ref: 'x',
  certificate_valid_until: '2027-01-01T00:00:00Z', certificate_cnpj: '11222333000181', auto_issue_invoices: false, nfse_mode: 'municipal', nfse_cutover: {},
  nfse_nacional_forced: false, certificate_status: 'valido', can_cutover: true, can_rollback: false, version: 2, ...over,
});

describe('FiscalSettingsForm', () => {
  function mount(f: FiscalView, isAdmin = true) {
    const api = makeApi();
    api.get.mockResolvedValue({ data: f });
    api.put.mockResolvedValue({ data: { ...f, version: 3 } });
    api.post.mockResolvedValue({ data: { ...f, nfse_mode: 'nacional' } });
    api.upload.mockResolvedValue({ data: {} });
    const Wrapper = wrapperFor();
    render(<Wrapper><FiscalSettingsForm hooks={createCommerceHooks(api)} isAdmin={isAdmin} /></Wrapper>);
    return api;
  }
  it('saves registrations with expected_version and validates the IBGE code', async () => {
    const user = userEvent.setup();
    const api = mount(fiscal());
    const ibge = await screen.findByDisplayValue('3550308');
    await user.clear(ibge);
    await user.type(ibge, '123');
    await user.click(screen.getByRole('button', { name: 'Salvar dados fiscais' }));
    expect(await screen.findByText('O código IBGE tem 7 dígitos.')).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
    await user.clear(ibge);
    await user.type(ibge, '3304557');
    await user.click(screen.getByRole('button', { name: 'Salvar dados fiscais' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(api.put.mock.calls[0][1]).toMatchObject({ expected_version: 2, inscricao_municipal: '123', inscricao_estadual: null, municipio_ibge: '3304557', auto_issue_invoices: false });
  });
  it('uploads the certificate as multipart and clears the password afterwards', async () => {
    const user = userEvent.setup();
    const api = mount(fiscal());
    await screen.findByText('Certificado válido');
    await user.click(screen.getByRole('button', { name: 'Enviar certificado' }));
    expect(await screen.findByText('Escolha o arquivo do certificado.')).toBeInTheDocument();
    await user.upload(screen.getByLabelText(/Arquivo \.pfx/), new File(['x'], 'cert.pfx'));
    await user.type(screen.getByLabelText('Senha do certificado'), 'segredo');
    await user.click(screen.getByRole('button', { name: 'Enviar certificado' }));
    await waitFor(() => expect(api.upload).toHaveBeenCalledTimes(1));
    const form = api.upload.mock.calls[0][1] as FormData;
    expect(form.get('password')).toBe('segredo');
    expect((form.get('file') as File).name).toBe('cert.pfx');
    expect(await screen.findByText('Certificado enviado.')).toBeInTheDocument();
    expect(screen.getByLabelText('Senha do certificado')).toHaveValue('');
  });
  it('rejects an oversized certificate client-side', async () => {
    const user = userEvent.setup();
    const api = mount(fiscal());
    await screen.findByText('Certificado válido');
    await user.upload(screen.getByLabelText(/Arquivo \.pfx/), new File([new Uint8Array(70 * 1024)], 'big.pfx'));
    await user.type(screen.getByLabelText('Senha do certificado'), 'x');
    await user.click(screen.getByRole('button', { name: 'Enviar certificado' }));
    expect(await screen.findByText(/passa de 64 KB/)).toBeInTheDocument();
    expect(api.upload).not.toHaveBeenCalled();
  });
  it('cutover needs the typed phrase', async () => {
    const user = userEvent.setup();
    const api = mount(fiscal());
    await user.click(await screen.findByRole('button', { name: 'Migrar para NFS-e Nacional…' }));
    const dialog = screen.getByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Confirmar' });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText('Frase de confirmação'), 'migrar');
    expect(confirm).toBeDisabled();
    await user.clear(within(dialog).getByLabelText('Frase de confirmação'));
    await user.type(within(dialog).getByLabelText('Frase de confirmação'), NFSE_CUTOVER_PHRASE);
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/commerce/fiscal/nfse-cutover', { confirm: NFSE_CUTOVER_PHRASE }));
  });
  it('is read-only for non-admins (no save, upload or danger actions)', async () => {
    mount(fiscal(), false);
    expect(await screen.findByText(/Somente administradores/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Salvar dados fiscais' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Enviar certificado' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Migrar/ })).toBeNull();
  });
  it('MEI / Simples forced Nacional: no rollback offered', async () => {
    mount(fiscal({ tax_regime: 'mei', nfse_mode: 'nacional', nfse_nacional_forced: true, can_cutover: false, can_rollback: false }));
    expect(await screen.findByText(/sempre pelo Emissor Nacional/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Voltar para NFS-e municipal/ })).toBeNull();
  });
});

const options: InstallmentOption[] = [
  { count: 1, installment_cents: 10000, total_cents: 10000, interest_free: true },
  { count: 3, installment_cents: 3333, total_cents: 10000, interest_free: true },
  { count: 6, installment_cents: 1800, total_cents: 10800, interest_free: false },
];

describe('InstallmentPicker', () => {
  it('shows per-parcela value and the total with interest', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<InstallmentPicker options={options} value={6} onChange={onChange} />);
    expect(screen.getByLabelText('3x de R$ 33,33 sem juros')).toBeInTheDocument();
    expect(screen.getByLabelText('6x de R$ 18,00 (total R$ 108,00)')).toBeChecked();
    expect(screen.getByTestId('installment-total')).toHaveTextContent('R$ 108,00');
    await user.click(screen.getByLabelText('3x de R$ 33,33 sem juros'));
    expect(onChange).toHaveBeenCalledWith(3);
  });
  it('renders nothing when there is no choice', () => {
    const { container } = render(<InstallmentPicker options={[options[0]]} value={1} onChange={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('CheckoutForm card installments', () => {
  const quote: Quote = {
    lines: [{ offer_id: 'o1', title: 'Curso', unit_price_cents: 10000, qty: 1, total_cents: 10000, product_type: 'digital', fulfillment_type: 'digital_delivery' }],
    subtotal_cents: 10000, discount_cents: 0, total_cents: 10000, currency: 'BRL', requires_immediate_delivery_waiver: false, installment_options: options,
  };
  it('offers parcelas only for the card, pays the interest-inclusive total and sends the count', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.post.mockResolvedValue({ data: { order_token: 'tok', status: 'pending_payment' } });
    const Wrapper = wrapperFor();
    render(
      <Wrapper>
        <CheckoutForm hooks={createCommerceHooks(api)} request={{ items: [{ offer_id: 'o1', qty: 1 }] }} quote={quote} legal={{ terms_version: 't', privacy_version: 'p', withdrawal_text: '' }} onSuccess={vi.fn()} />
      </Wrapper>,
    );
    expect(screen.queryByTestId('installment-picker')).toBeNull(); // pix by default
    await user.click(screen.getByLabelText('Cartão de crédito'));
    await user.click(screen.getByLabelText('6x de R$ 18,00 (total R$ 108,00)'));
    expect(screen.getByRole('button', { name: /Pagar R\$\s108,00/ })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Nome completo/), 'Maria Souza');
    await user.type(screen.getByLabelText(/E-mail/), 'maria@example.com');
    await user.type(screen.getByLabelText(/CPF ou CNPJ/), VALID_CPF);
    await user.type(screen.getByLabelText(/Telefone/), '11987654321');
    await user.click(screen.getByLabelText(/Termos de uso/));
    await user.click(screen.getByLabelText(/Política de privacidade/));
    await user.click(screen.getByRole('button', { name: /Pagar/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const body = api.post.mock.calls.find((c) => String(c[0]).endsWith('/checkout'))?.[1] as Record<string, unknown>;
    expect(body).toMatchObject({ payment_method: 'credit_card', installments: 6 });
  });
});
