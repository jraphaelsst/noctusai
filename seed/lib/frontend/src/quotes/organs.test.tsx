/** Organ behaviour: every state (skeleton, error + retry, empty, data, refreshing, frozen, decided) and each write path. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '../api';
import { createQuotesHooks, createQuotesPublicHooks } from './hooks';
import { QuoteAcceptPage } from './QuoteAcceptPage';
import { QuoteEditor } from './QuoteEditor';
import { QuoteSendDialog } from './QuoteSendDialog';
import { QuoteConversionChip, QuoteStatusChip } from './QuoteStatusChip';
import { QuotesTable } from './QuotesTable';
import { makeApi, page, publicView, quote, wrapperFor } from './testUtils';
import { QUOTE_STATUSES } from './types';

afterEach(cleanup);

const PARTIES = [{ id: 'p1', name: 'Ana Souza', email: 'ana@cliente.com' }, { id: 'p2', name: 'Beto Lima' }];
const ITEMS = [{ id: 'i1', name: 'Cadeira', unit: 'UN', price_cents: 15000, kind: 'goods' as const }];

function mountStaff(ui: (hooks: ReturnType<typeof createQuotesHooks>) => React.ReactElement, routes: Record<string, unknown>) {
  const api = makeApi(routes);
  const Wrapper = wrapperFor();
  render(<Wrapper>{ui(createQuotesHooks(api))}</Wrapper>);
  return api;
}

describe('status chips', () => {
  it('renders every status with its pt-BR label and a data hook', () => {
    for (const s of QUOTE_STATUSES) {
      const { unmount } = render(<QuoteStatusChip status={s} />);
      expect(document.querySelector(`[data-status="${s}"]`)).toBeInTheDocument();
      unmount();
    }
    render(<QuoteStatusChip status="accepted" />);
    expect(screen.getByText('Aceito')).toBeInTheDocument();
  });
  it('conversion chip: hidden for none, loud for failed', () => {
    const { container, rerender } = render(<QuoteConversionChip status="none" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<QuoteConversionChip status="failed" />);
    expect(screen.getByText('Falha na conversão')).toBeInTheDocument();
  });
});

describe('QuotesTable', () => {
  it('skeleton first, then rows with party, total, validity and chips', async () => {
    mountStaff((h) => <QuotesTable hooks={h} parties={PARTIES} />, { 'GET /api/quotes': page([quote({ status: 'accepted', conversion_status: 'failed' })]) });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    const row = await screen.findByTestId('quote-row');
    expect(within(row).getByText('ORC-00001')).toBeInTheDocument();
    expect(within(row).getByText('Ana Souza')).toBeInTheDocument();
    expect(row.textContent).toContain('R$');
    expect(within(row).getByText('30/11/2026')).toBeInTheDocument();
    expect(within(row).getByText('Aceito')).toBeInTheDocument();
    expect(within(row).getByText('Falha na conversão')).toBeInTheDocument();
  });

  it('empty state vs filtered-empty state are different claims', async () => {
    const user = userEvent.setup();
    const api = mountStaff((h) => <QuotesTable hooks={h} />, { 'GET /api/quotes': page([]) });
    expect(await screen.findByText('Nenhum orçamento ainda.')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Situação'), 'sent');
    expect(await screen.findByText('Nenhum orçamento encontrado para esse filtro.')).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/quotes', expect.objectContaining({ status: 'sent' })));
  });

  it('error with retry (never a blank panel or an empty-list claim)', async () => {
    const user = userEvent.setup();
    let fail = true;
    mountStaff((h) => <QuotesTable hooks={h} />, { 'GET /api/quotes': () => { if (fail) throw new Error('rede caiu'); return page([quote()]); } });
    expect(await screen.findByText(/rede caiu/)).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByTestId('quote-row')).toBeInTheDocument();
  });

  it('a refetch over data keeps the table mounted', async () => {
    const api = mountStaff((h) => <QuotesTable hooks={h} />, { 'GET /api/quotes': page([quote()]) });
    await screen.findByTestId('quote-row');
    expect(api.get).toHaveBeenCalled();
    expect(screen.queryByTestId('list-loading')).not.toBeInTheDocument();
  });

  it('"Novo orçamento" only for writers', async () => {
    mountStaff((h) => <QuotesTable hooks={h} />, { 'GET /api/quotes': page([]) });
    await screen.findByText('Nenhum orçamento ainda.');
    expect(screen.queryByRole('button', { name: 'Novo orçamento' })).not.toBeInTheDocument();
    cleanup();
    mountStaff((h) => <QuotesTable hooks={h} canWrite />, { 'GET /api/quotes': page([]) });
    expect(await screen.findByRole('button', { name: 'Novo orçamento' })).toBeInTheDocument();
  });

  it('a row opens the editor (or the host override)', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    mountStaff((h) => <QuotesTable hooks={h} onSelect={onSelect} />, { 'GET /api/quotes': page([quote()]) });
    await user.click(await screen.findByTestId('quote-row'));
    expect(onSelect).toHaveBeenCalledWith('q1');
    cleanup();
    mountStaff((h) => <QuotesTable hooks={h} parties={PARTIES} />, { 'GET /api/quotes': page([quote()]), 'GET /api/quotes/q1': { data: quote() } });
    await user.click(await screen.findByTestId('quote-row'));
    expect(await screen.findByRole('dialog', { name: 'Orçamento ORC-00001 (v1)' })).toBeInTheDocument();
  });
});

describe('QuoteEditor', () => {
  it('creates: live server-rounded totals, money as cents, qty as a decimal string, then the payload', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const api = mountStaff(
      (h) => <QuoteEditor hooks={h} open quoteId={null} onClose={onClose} canWrite parties={PARTIES} items={ITEMS} />,
      { 'POST /api/quotes': { data: quote() } },
    );
    await user.selectOptions(screen.getByLabelText(/Cliente/), 'p1');
    await user.selectOptions(screen.getByLabelText('Item do catálogo'), 'i1');
    expect((screen.getByLabelText('Descrição') as HTMLInputElement).value).toBe('Cadeira');
    expect((screen.getByLabelText(/Preço unit/) as HTMLInputElement).value).toBe('150,00');
    await user.clear(screen.getByLabelText('Qtd.'));
    await user.type(screen.getByLabelText('Qtd.'), '2,5');
    expect(screen.getByTestId('quote-total')).toHaveTextContent('R$ 375,00');
    await user.type(screen.getByLabelText(/Desconto geral/), '25');
    expect(screen.getByTestId('quote-total')).toHaveTextContent('R$ 350,00');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const body = api.post.mock.calls[0][1];
    expect(body).toMatchObject({
      party_id: 'p1', discount_cents: 2500, valid_until: null, convert_to: null,
      lines: [{ item_id: 'i1', description: 'Cadeira', kind: 'goods', qty: '2.5', unit_price_cents: 15000, discount_cents: 0 }],
    });
    expect(JSON.stringify(body)).not.toMatch(/total_cents|subtotal/);        // the client never sends a total
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('refuses an incomplete form locally and says why', async () => {
    const user = userEvent.setup();
    const api = mountStaff((h) => <QuoteEditor hooks={h} open quoteId={null} onClose={() => undefined} canWrite parties={PARTIES} />, {});
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Escolha o cliente');
    await user.selectOptions(screen.getByLabelText(/Cliente/), 'p1');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Revise os itens');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('shows the server refusal in pt-BR and keeps the dialog open', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    mountStaff(
      (h) => <QuoteEditor hooks={h} open quoteId={null} onClose={onClose} canWrite parties={PARTIES} />,
      { 'POST /api/quotes': () => { throw new ApiError(422, 'x', { error: { code: 'cliente_invalido' } }); } },
    );
    await user.selectOptions(screen.getByLabelText(/Cliente/), 'p1');
    await user.type(screen.getByLabelText('Descrição'), 'Algo');
    await user.type(screen.getByLabelText(/Preço unit/), '10');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText('Cliente não encontrado ou arquivado.')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('edits a draft (PATCH) and offers send / delete to writers', async () => {
    const user = userEvent.setup();
    const api = mountStaff(
      (h) => <QuoteEditor hooks={h} open quoteId="q1" onClose={() => undefined} canWrite parties={PARTIES} />,
      { 'GET /api/quotes/q1': { data: quote() }, 'PATCH /api/quotes/q1': { data: quote() }, 'GET /api/quotes': page([quote()]) },
    );
    expect(await screen.findByDisplayValue('Reforma')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enviar ao cliente' })).toBeInTheDocument();
    await user.clear(screen.getByLabelText('Título'));
    await user.type(screen.getByLabelText('Título'), 'Reforma 2');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/quotes/q1', expect.objectContaining({ title: 'Reforma 2', party_id: 'p1' })));
  });

  it('a draft is deleted only after a second, explicit click', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const api = mountStaff((h) => <QuoteEditor hooks={h} open quoteId="q1" onClose={onClose} canWrite />, { 'GET /api/quotes/q1': { data: quote() }, 'DELETE /api/quotes/q1': null, 'GET /api/quotes': page([]) });
    await user.click(await screen.findByRole('button', { name: 'Excluir rascunho' }));
    expect(api.delete).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Sim, excluir' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.delete).toHaveBeenCalledWith('/api/quotes/q1');
  });

  it('a sent quote is FROZEN: fields disabled, no Save, "Nova versão" offered and followed', async () => {
    const user = userEvent.setup();
    const onOpenQuote = vi.fn();
    const sent = quote({ status: 'sent' });
    const api = mountStaff(
      (h) => <QuoteEditor hooks={h} open quoteId="q1" onClose={() => undefined} onOpenQuote={onOpenQuote} canWrite parties={PARTIES} />,
      { 'GET /api/quotes/q1': { data: sent }, 'GET /api/quotes': page([sent]), 'POST /api/quotes/q1/versions': { data: quote({ id: 'q2', version: 2 }) } },
    );
    expect(await screen.findByText(/já foi enviado e não pode ser editado/)).toBeInTheDocument();
    expect(screen.getByLabelText('Título')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Salvar' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Nova versão' }));
    await waitFor(() => expect(onOpenQuote).toHaveBeenCalledWith('q2'));
    expect(api.post).toHaveBeenCalledWith('/api/quotes/q1/versions', {});
  });

  it('an accepted quote offers no new version; a failed conversion offers a retry', async () => {
    const user = userEvent.setup();
    const acc = quote({ status: 'accepted', accepted_at: '2026-10-10T12:00:00Z', conversion_status: 'failed', conversion_error: 'ConnectionError: down' });
    const api = mountStaff(
      (h) => <QuoteEditor hooks={h} open quoteId="q1" onClose={() => undefined} canWrite />,
      { 'GET /api/quotes/q1': { data: acc }, 'GET /api/quotes': page([acc]), 'POST /api/quotes/q1/convert': { data: acc } },
    );
    expect(await screen.findByText('Falha na conversão')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Nova versão' })).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('ConnectionError: down');
    await user.click(screen.getByRole('button', { name: 'Tentar converter novamente' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/quotes/q1/convert', {}));
  });

  it('read-only users see the quote but no write controls', async () => {
    mountStaff((h) => <QuoteEditor hooks={h} open quoteId="q1" onClose={() => undefined} />, { 'GET /api/quotes/q1': { data: quote() } });
    expect(await screen.findByText(/apenas administradores editam/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Salvar' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Enviar ao cliente' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Excluir rascunho' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Baixar PDF' })).toHaveAttribute('href', '/api/quotes/q1/pdf');
  });

  it('records an offline decision for an open quote', async () => {
    const user = userEvent.setup();
    const sent = quote({ status: 'viewed' });
    const api = mountStaff(
      (h) => <QuoteEditor hooks={h} open quoteId="q1" onClose={() => undefined} canWrite />,
      { 'GET /api/quotes/q1': { data: sent }, 'GET /api/quotes': page([sent]), 'POST /api/quotes/q1/accept': { data: sent } },
    );
    const accept = await screen.findByRole('button', { name: 'Registrar aceite' });
    expect(accept).toBeDisabled();
    await user.type(screen.getByLabelText('Nome de quem decidiu'), 'Ana Souza');
    await user.click(accept);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/quotes/q1/accept', { signer_name: 'Ana Souza' }));
  });

  it('load error is retryable; skeleton first', async () => {
    mountStaff((h) => <QuoteEditor hooks={h} open quoteId="q1" onClose={() => undefined} canWrite />, { 'GET /api/quotes/q1': () => { throw new Error('rede caiu'); } });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(await screen.findByText(/rede caiu/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });

  it('lists the versions of the same quote', async () => {
    const v1 = quote({ id: 'q1', status: 'superseded', is_current: false });
    const v2 = quote({ id: 'q2', version: 2, status: 'draft' });
    mountStaff(
      (h) => <QuoteEditor hooks={h} open quoteId="q2" onClose={() => undefined} onOpenQuote={() => undefined} canWrite />,
      { 'GET /api/quotes/q2': { data: v2 }, 'GET /api/quotes': page([v2, v1]) },
    );
    const region = await screen.findByRole('region', { name: 'Versões' });
    expect(within(region).getAllByRole('listitem')).toHaveLength(2);
    expect(within(region).getByText('atual')).toBeInTheDocument();
  });
});

describe('QuoteSendDialog', () => {
  it('emails with the customer address prefilled and reports who it went to', async () => {
    const user = userEvent.setup();
    const onSent = vi.fn();
    const sent = { quote: quote({ status: 'sent' }), channel: 'email', url: 'https://app/orc/tok', sent_to: 'ana@cliente.com' };
    const api = mountStaff((h) => <QuoteSendDialog hooks={h} open quoteId="q1" defaultTo="ana@cliente.com" onClose={() => undefined} onSent={onSent} />, { 'POST /api/quotes/q1/send': { data: sent } });
    expect((screen.getByLabelText('E-mail do destinatário') as HTMLInputElement).value).toBe('ana@cliente.com');
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    expect(await screen.findByText('Enviado para ana@cliente.com.')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/quotes/q1/send', { channel: 'email', to: 'ana@cliente.com' });
    expect(onSent).toHaveBeenCalled();
  });

  it('link channel: shows the link and copies it; a failed copy is announced, never silent', async () => {
    const user = userEvent.setup();
    const sent = { quote: quote({ status: 'sent' }), channel: 'link', url: 'https://app/orc/tok', sent_to: null };
    const api = mountStaff((h) => <QuoteSendDialog hooks={h} open quoteId="q1" onClose={() => undefined} />, { 'POST /api/quotes/q1/send': { data: sent } });
    await user.click(screen.getByLabelText('Só gerar o link'));
    expect(screen.queryByLabelText('E-mail do destinatário')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    expect(await screen.findByDisplayValue('https://app/orc/tok')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/quotes/q1/send', { channel: 'link' });
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) }, configurable: true });
    await user.click(screen.getByRole('button', { name: 'Copiar link' }));
    expect(await screen.findByText(/Não foi possível copiar/)).toBeInTheDocument();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true });
    await user.click(screen.getByRole('button', { name: 'Copiar link' }));
    expect(await screen.findByText('Link copiado.')).toBeInTheDocument();
  });

  it('a refusal is shown in pt-BR and the form stays', async () => {
    const user = userEvent.setup();
    mountStaff((h) => <QuoteSendDialog hooks={h} open quoteId="q1" onClose={() => undefined} />, {
      'POST /api/quotes/q1/send': () => { throw new ApiError(422, 'x', { error: { code: 'orcamento_vazio' } }); },
    });
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    expect(await screen.findByText('Adicione ao menos um item antes de enviar.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeInTheDocument();
  });
});

describe('QuoteAcceptPage (public, no login)', () => {
  function mountPublic(routes: Record<string, unknown>) {
    const api = makeApi(routes);
    const Wrapper = wrapperFor();
    render(<Wrapper><QuoteAcceptPage hooks={createQuotesPublicHooks(api, { apiBase: 'https://api.test' })} token="tok" /></Wrapper>);
    return api;
  }

  it('skeleton, then the offer: lines, totals, terms, PDF link', async () => {
    mountPublic({ 'GET /api/public/quotes/tok': { data: publicView() } });
    expect(screen.getByLabelText('Carregando orçamento…')).toHaveAttribute('aria-busy', 'true');
    expect(await screen.findByRole('heading', { name: 'Orçamento ORC-00001' })).toBeInTheDocument();
    expect(screen.getByText('Para: Ana Souza')).toBeInTheDocument();
    expect(screen.getByText('De: Acme Ltda')).toBeInTheDocument();
    expect(screen.getByTestId('public-line')).toHaveTextContent('Instalação');
    expect(screen.getByTestId('public-total')).toHaveTextContent('R$ 195,00');
    expect(screen.getByText('30 dias de garantia')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Baixar PDF' })).toHaveAttribute('href', 'https://api.test/api/public/quotes/tok/pdf');
  });

  it('consent is explicit: Accept stays disabled until a name AND the tick; the recorded sentence is shown', async () => {
    const user = userEvent.setup();
    const accepted = publicView({ status: 'accepted', can_decide: false, consent_template: null, decision: { decision: 'accepted', decided_at: '2026-10-14T15:00:00Z' } });
    const api = mountPublic({ 'GET /api/public/quotes/tok': { data: publicView() }, 'POST /api/public/quotes/tok/accept': { data: accepted } });
    const button = await screen.findByRole('button', { name: 'Aceitar orçamento' });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText(/Seu nome completo/), 'Ana Souza');
    expect(button).toBeDisabled();
    await user.click(screen.getByLabelText('Li e aceito os termos deste orçamento.'));
    expect(screen.getByText(/Eu, Ana Souza, li e aceito o orçamento ORC-00001/)).toBeInTheDocument();
    expect(button).toBeEnabled();
    await user.click(button);
    expect(await screen.findByText(/Orçamento aceito em/)).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/public/quotes/tok/accept', { name: 'Ana Souza', agree: true });
    expect(screen.queryByRole('button', { name: 'Aceitar orçamento' })).not.toBeInTheDocument();       // no lying button after deciding
  });

  it('reject with an optional reason', async () => {
    const user = userEvent.setup();
    const rejected = publicView({ status: 'rejected', can_decide: false, consent_template: null, decision: { decision: 'rejected', decided_at: '2026-10-14T15:00:00Z' } });
    const api = mountPublic({ 'GET /api/public/quotes/tok': { data: publicView() }, 'POST /api/public/quotes/tok/reject': { data: rejected } });
    await user.click(await screen.findByRole('button', { name: 'Recusar este orçamento' }));
    await user.type(screen.getByLabelText('Motivo (opcional)'), 'Muito caro');
    await user.click(screen.getByRole('button', { name: 'Recusar' }));
    expect(await screen.findByText(/Você recusou este orçamento/)).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/public/quotes/tok/reject', { reason: 'Muito caro' });
  });

  it('a server refusal at decision time is shown (e.g. it expired meanwhile) and the form stays', async () => {
    const user = userEvent.setup();
    mountPublic({
      'GET /api/public/quotes/tok': { data: publicView() },
      'POST /api/public/quotes/tok/accept': () => { throw new ApiError(409, 'x', { error: { code: 'orcamento_expirado' } }); },
    });
    await user.type(await screen.findByLabelText(/Seu nome completo/), 'Ana Souza');
    await user.click(screen.getByLabelText('Li e aceito os termos deste orçamento.'));
    await user.click(screen.getByRole('button', { name: 'Aceitar orçamento' }));
    expect(await screen.findByText('A validade do orçamento já passou.')).toBeInTheDocument();
  });

  it.each([
    ['expired', 'Este orçamento expirou'],
    ['superseded', 'substituída por uma mais recente'],
  ] as const)('%s: says so and offers NO decision form', async (status, text) => {
    mountPublic({ 'GET /api/public/quotes/tok': { data: publicView({ status, can_decide: false, consent_template: null }) } });
    expect(await screen.findByRole('alert')).toHaveTextContent(text);
    expect(screen.queryByRole('button', { name: 'Aceitar orçamento' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Seu nome completo/)).not.toBeInTheDocument();
  });

  it('a bad link is a plain answer with no retry button; other failures are retryable', async () => {
    mountPublic({ 'GET /api/public/quotes/tok': () => { throw new ApiError(404, 'x', { error: { code: 'link_invalido' } }); } });
    expect(await screen.findByText(/Link inválido ou expirado/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Tentar novamente' })).not.toBeInTheDocument();
    cleanup();
    mountPublic({ 'GET /api/public/quotes/tok': () => { throw new ApiError(500, 'boom', {}); } });
    // a 5xx IS transient: the hook retries with backoff before surfacing the error + retry button
    expect(await screen.findByRole('button', { name: 'Tentar novamente' }, { timeout: 8000 })).toBeInTheDocument();
  }, 12000);

  it('renders only the allow-listed view: nothing outside it can appear', async () => {
    const leaky = { ...publicView(), party_email: 'segredo@x.com', party_doc: '52998224725', org_id: 'ORG-SECRET' };
    mountPublic({ 'GET /api/public/quotes/tok': { data: leaky } });
    await screen.findByRole('heading', { name: 'Orçamento ORC-00001' });
    expect(document.body.textContent).not.toMatch(/segredo@x\.com|52998224725|ORG-SECRET/);
  });
});
