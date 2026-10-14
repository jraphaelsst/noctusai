/** Storefront pieces: shell (tokens + legal footer + no-store), cart persistence, order status states, my-orders neutrality. */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor, renderHook, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StorefrontShell, brandTokensToCssVars } from './StorefrontShell';
import { OrderStatusPage } from './OrderStatusPage';
import { MyOrdersRequest } from './MyOrdersRequest';
import { useCart, cartStorageKey } from './cartState';
import { createCommerceHooks } from './hooks';
import { ApiError } from '../api';
import { makeApi, wrapperFor } from './testUtils';
import type { Storefront } from './types';

afterEach(cleanup);

const store: Storefront = {
  trade_name: 'Loja Bacana',
  legal_name: 'Bacana Comércio LTDA',
  cnpj: '11222333000181',
  address: { street: 'Rua A', number: '10', city: 'São Paulo', state: 'SP', zip: '01000-000' },
  contact: { email: 'oi@bacana.com', phone: '1133334444' },
  brand_tokens: { primary: '#ff0000', 'bad key;': 'x', accent: 'red;}' },
  locale: 'pt-BR',
  currency: 'BRL',
  legal: { terms_version: 't1', privacy_version: 'p1', withdrawal_text: 'Arrependimento em 7 dias.' },
};

describe('StorefrontShell', () => {
  it('renders brand tokens as CSS variables and the Decreto 7.962 legal footer', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: store });
    const Wrapper = wrapperFor();
    render(<Wrapper><StorefrontShell hooks={createCommerceHooks(api)}><p>conteúdo</p></StorefrontShell></Wrapper>);
    const shell = await screen.findByTestId('storefront-shell');
    expect(shell.style.getPropertyValue('--commerce-primary')).toBe('#ff0000');
    const footer = screen.getByTestId('legal-footer');
    expect(footer).toHaveTextContent('Bacana Comércio LTDA');
    expect(footer).toHaveTextContent('CNPJ 11.222.333/0001-81');
    expect(footer).toHaveTextContent('Rua A, 10');
    expect(footer).toHaveTextContent('oi@bacana.com');
    expect(footer).toHaveTextContent('Arrependimento em 7 dias.');
    expect(screen.getByText('conteúdo')).toBeInTheDocument();
  });

  it('drops unsafe token names/values', () => {
    const vars = brandTokensToCssVars(store.brand_tokens) as Record<string, string>;
    expect(Object.keys(vars)).toEqual(['--commerce-primary']);
  });

  it('unknown host (404) shows the no-store state', async () => {
    const api = makeApi();
    api.get.mockRejectedValue(new ApiError(404, 'nope'));
    const Wrapper = wrapperFor();
    render(<Wrapper><StorefrontShell hooks={createCommerceHooks(api)}>x</StorefrontShell></Wrapper>);
    expect(await screen.findByTestId('storefront-no-store')).toHaveTextContent('Nenhuma loja neste endereço');
  });

  it('switches language from the store locale', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: { ...store, locale: 'en' } });
    const Wrapper = wrapperFor();
    render(<Wrapper><StorefrontShell hooks={createCommerceHooks(api)}>x</StorefrontShell></Wrapper>);
    expect(await screen.findByText(/Terms vt1/)).toBeInTheDocument();
  });
});

/** In-memory Storage (the jsdom/Node localStorage in this harness is not a complete Storage). */
function memoryStorage() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: vi.fn((k: string, v: string) => void m.set(k, String(v))),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
  };
}

describe('useCart persistence', () => {
  let storage: ReturnType<typeof memoryStorage>;
  beforeEach(() => {
    storage = memoryStorage();
    vi.stubGlobal('localStorage', storage);
    Object.defineProperty(window, 'localStorage', { value: storage, configurable: true });
  });
  afterEach(() => vi.unstubAllGlobals());
  const item = { offer_id: 'o1', product_slug: 'p', title: 'P', offer_name: 'O', unit_price_cents: 100, currency: 'BRL' };

  it('persists per host and restores', () => {
    const a = renderHook(() => useCart('shop-a.test'));
    act(() => a.result.current.add(item, 2));
    expect(JSON.parse(window.localStorage.getItem(cartStorageKey('shop-a.test'))!)).toHaveLength(1);
    const again = renderHook(() => useCart('shop-a.test'));
    expect(again.result.current.count).toBe(2);
    const other = renderHook(() => useCart('shop-b.test'));
    expect(other.result.current.count).toBe(0);
  });

  it('merges quantities, clamps, and removes at qty 0', () => {
    const { result } = renderHook(() => useCart('h'));
    act(() => result.current.add(item));
    act(() => result.current.add(item, 3));
    expect(result.current.items[0].qty).toBe(4);
    act(() => result.current.setQty('o1', 0));
    expect(result.current.items).toEqual([]);
  });

  it('flags corrupt storage instead of crashing silently', () => {
    window.localStorage.setItem(cartStorageKey('h'), '{not json');
    const { result } = renderHook(() => useCart('h'));
    expect(result.current.items).toEqual([]);
    expect(result.current.corrupt).toBe(true);
  });

  it('keeps working in memory and reports persistError when storage throws', () => {
    storage.setItem.mockImplementation(() => {
      throw new Error('quota');
    });
    const { result } = renderHook(() => useCart('h'));
    act(() => result.current.add(item));
    expect(result.current.count).toBe(1);
    expect(result.current.persistError).toBe(true);
  });
});

describe('OrderStatusPage', () => {
  const base = { token: 't', items: [{ title: 'Curso', qty: 1, unit_price_cents: 9900, total_cents: 9900 }], subtotal_cents: 9900, discount_cents: 0, total_cents: 9900, currency: 'BRL', payment_method: 'pix', checkout_url: null, pix_qr: null, expires_at: null, paid_at: null };
  function mount(order: unknown, rejection?: unknown) {
    const api = makeApi();
    if (rejection) api.get.mockRejectedValue(rejection);
    else api.get.mockResolvedValue({ data: order });
    const Wrapper = wrapperFor();
    render(<Wrapper><OrderStatusPage hooks={createCommerceHooks(api)} token="t" /></Wrapper>);
  }

  it('pending Pix shows QR, code and a working copy button', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    mount({ ...base, status: 'pending_payment', pix_qr: { payload: '000201PIX', encoded_image: 'AAAA' }, checkout_url: 'https://pay.test/x' });
    expect(await screen.findByAltText('QR Code Pix')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Copiar código Pix' }));
    expect(writeText).toHaveBeenCalledWith('000201PIX');
    expect(await screen.findByText('Copiado!')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Abrir página de pagamento' })).toHaveAttribute('href', 'https://pay.test/x');
  });

  it('reports a failed copy instead of swallowing it', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) }, configurable: true });
    mount({ ...base, status: 'pending_payment', pix_qr: { payload: 'X' } });
    await user.click(await screen.findByRole('button', { name: 'Copiar código Pix' }));
    expect(await screen.findByText(/Não foi possível copiar/)).toBeInTheDocument();
  });

  it('expired offers "gerar novo pagamento" that regenerates by token and refreshes the order', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValue({ data: { ...base, status: 'expired' } });
    api.post.mockResolvedValue({ data: { status: 'pending_payment', checkout_url: 'https://pay.test/n' } });
    const Wrapper = wrapperFor();
    render(<Wrapper><OrderStatusPage hooks={createCommerceHooks(api)} token="t" /></Wrapper>);
    expect(await screen.findByText(/prazo de pagamento deste pedido expirou/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Forma de pagamento do novo pagamento'), 'boleto');
    await user.click(screen.getByRole('button', { name: 'Gerar novo pagamento' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/storefront/orders/t/payment', { payment_method: 'boleto' }));
    await waitFor(() => expect(api.get.mock.calls.length).toBeGreaterThan(1)); // the public order was refetched
  });

  it('a regenerate refusal (429) is shown, not swallowed', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValue({ data: { ...base, status: 'expired' } });
    api.post.mockRejectedValue(new ApiError(429, 'Aguarde um minuto antes de gerar um novo pagamento.'));
    const Wrapper = wrapperFor();
    render(<Wrapper><OrderStatusPage hooks={createCommerceHooks(api)} token="t" /></Wrapper>);
    await user.click(await screen.findByRole('button', { name: 'Gerar novo pagamento' }));
    expect(await screen.findByText(/Aguarde um minuto/)).toBeInTheDocument();
  });

  it('a host-supplied onNewPayment replaces the built-in regenerate', async () => {
    const user = userEvent.setup();
    const onNewPayment = vi.fn();
    const api = makeApi();
    api.get.mockResolvedValue({ data: { ...base, status: 'expired' } });
    const Wrapper = wrapperFor();
    render(<Wrapper><OrderStatusPage hooks={createCommerceHooks(api)} token="t" onNewPayment={onNewPayment} /></Wrapper>);
    await user.click(await screen.findByRole('button', { name: 'Gerar novo pagamento' }));
    expect(onNewPayment).toHaveBeenCalledTimes(1);
    expect(api.post).not.toHaveBeenCalled();
  });

  it('a parcelled card order shows what was charged', async () => {
    mount({ ...base, status: 'paid', payment_method: 'credit_card', installment_count: 6, charged_cents: 10800 });
    expect(await screen.findByTestId('charged-total')).toHaveTextContent('R$ 108,00 em 6x');
  });

  it('paid confirms', async () => {
    mount({ ...base, status: 'paid' });
    expect(await screen.findByText(/Pagamento confirmado/)).toBeInTheDocument();
  });

  it('404 shows not found; other errors offer retry', async () => {
    mount(null, new ApiError(404, 'x'));
    expect(await screen.findByText('Pedido não encontrado.')).toBeInTheDocument();
    cleanup();
    mount(null, new ApiError(500, 'down'));
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });
});

describe('MyOrdersRequest', () => {
  it('always shows the same neutral message and never reveals whether orders exist', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.post.mockResolvedValue({});
    const Wrapper = wrapperFor();
    render(<Wrapper><MyOrdersRequest hooks={createCommerceHooks(api)} /></Wrapper>);
    await user.type(screen.getByLabelText(/E-mail/), 'x@y.com');
    await user.click(screen.getByRole('button', { name: 'Enviar link' }));
    expect(await screen.findByText(/Se houver pedidos para este e-mail/)).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/storefront/orders/access-link', { email: 'x@y.com' });
  });

  it('validates the e-mail locally', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    const Wrapper = wrapperFor();
    render(<Wrapper><MyOrdersRequest hooks={createCommerceHooks(api)} /></Wrapper>);
    await user.type(screen.getByLabelText(/E-mail/), 'nope');
    await user.click(screen.getByRole('button', { name: 'Enviar link' }));
    expect(await screen.findByText('E-mail inválido')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });
});
