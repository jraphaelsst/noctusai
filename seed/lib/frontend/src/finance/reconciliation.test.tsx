import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReconciliationPage, parseColumn } from './ReconciliationPage';
import { ExportsPanel } from './ExportsPanel';
import { ApiError } from '../api';
import { ACC_GW, baseRoutes, entry, hooksFor, makeRoutedApi, ok, page, wrapperFor } from './testUtils';
import type { StatementImport, StatementLine } from './types';

afterEach(cleanup);

const IMP: StatementImport = { id: 'imp1', account_id: 'acc-bank', format: 'ofx', filename: 'out.ofx', sha256: 'x', period_start: '2026-10-01', period_end: '2026-10-31', at: '2026-10-31T10:00:00Z' };
const line = (over: Partial<StatementLine> = {}): StatementLine => ({
  id: 'l1', import_id: 'imp1', account_id: 'acc-bank', posted_on: '2026-10-05', amount_cents: 10000, description: 'PIX MARIA',
  fitid: 'f1', match_status: 'suggested', ledger_id: null, suggested_entry_id: 'e1', ...over,
});

function routes(over: Record<string, unknown> = {}) {
  return {
    ...baseRoutes(),
    'GET /api/finance/statements': page([IMP]),
    'GET /api/finance/statements/imp1/lines': page([
      line(),
      line({ id: 'l2', description: 'TARIFA', amount_cents: -990, match_status: 'unmatched', suggested_entry_id: null }),
      line({ id: 'l3', description: 'JA FEITA', match_status: 'matched', suggested_entry_id: null }),
    ], { page_size: 50 }),
    'GET /api/finance/entries/e1': ok({ ...entry(), settlements: [], attachments: [] }),
    'GET /api/finance/entries': page([entry({ id: 'e9', description: 'Mensalidade' })]),
    ...over,
  };
}

async function openImport(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Ver linhas' }));
}

describe('ReconciliationPage', () => {
  it('lists imports → lines with status, signed amounts and the suggestion', async () => {
    const user = userEvent.setup();
    render(<ReconciliationPage hooks={hooksFor(makeRoutedApi(routes()))} isAdmin />, { wrapper: wrapperFor() });
    await openImport(user);
    expect(await screen.findByText(/PIX MARIA/)).toBeInTheDocument();
    expect(await screen.findByText(/Sugestão:/)).toBeInTheDocument();
    expect(screen.getByText('Pedido #100', { selector: 'strong' })).toBeInTheDocument();
    expect(within(screen.getByText(/JA FEITA/).closest('li')!).getByText('Conciliada')).toBeInTheDocument();
    expect(screen.getByText(/TARIFA/)).toBeInTheDocument();
  });

  it('accept suggestion → POST match; ignore → POST ignore; matched lines have no actions', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi(routes({
      'POST /api/finance/statement-lines/l1/match': ok({ line: line({ match_status: 'matched' }), entry: entry(), ledger_id: 'x', settlement_id: 's', created_settlement: true }),
      'POST /api/finance/statement-lines/l2/ignore': ok(line({ id: 'l2', match_status: 'ignored' })),
    }));
    render(<ReconciliationPage hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    await openImport(user);
    const l1 = (await screen.findByText(/PIX MARIA/)).closest('li')!;
    await user.click(within(l1).getByRole('button', { name: 'Conciliar com a sugestão' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/finance/statement-lines/l1/match', { entry_id: 'e1' }));
    const l2 = screen.getByText(/TARIFA/).closest('li')!;
    await user.click(within(l2).getByRole('button', { name: 'Ignorar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/finance/statement-lines/l2/ignore', {}));
    expect(within(screen.getByText(/JA FEITA/).closest('li')!).queryByRole('button')).not.toBeInTheDocument();
  });

  it('manual pick: a line with no suggestion is matched to a chosen entry (direction follows the sign)', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi(routes({ 'POST /api/finance/statement-lines/l2/match': ok({ line: line(), entry: entry(), ledger_id: 'x', settlement_id: 's', created_settlement: true }) }));
    render(<ReconciliationPage hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    await openImport(user);
    const l2 = (await screen.findByText(/TARIFA/)).closest('li')!;
    await user.click(within(l2).getByRole('button', { name: 'Escolher lançamento' }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText(/Mensalidade/)).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/finance/entries', expect.objectContaining({ direction: 'payable' }));
    await user.click(within(dialog).getByRole('button', { name: 'Conciliar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/finance/statement-lines/l2/match', { entry_id: 'e9' }));
  });

  it('a refused match shows the server message', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi(routes({ 'POST /api/finance/statement-lines/l1/match': () => Promise.reject(new ApiError(409, 'O lançamento já está baixado')) }));
    render(<ReconciliationPage hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    await openImport(user);
    await user.click(await screen.findByRole('button', { name: 'Conciliar com a sugestão' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('O lançamento já está baixado');
  });

  it('staff can read but not import / match / ignore / sync', async () => {
    const user = userEvent.setup();
    render(<ReconciliationPage hooks={hooksFor(makeRoutedApi(routes()))} />, { wrapper: wrapperFor() });
    await openImport(user);
    await screen.findByText(/PIX MARIA/);
    for (const name of ['Importar extrato', 'Ignorar', 'Conciliar com a sugestão', 'Escolher lançamento', 'Sincronizar agora']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
  });

  it('empty imports / skeleton / error', async () => {
    render(<ReconciliationPage hooks={hooksFor(makeRoutedApi(routes({ 'GET /api/finance/statements': page([]) })))} isAdmin />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Nenhum extrato importado/)).toBeInTheDocument();
    cleanup();
    render(<ReconciliationPage hooks={hooksFor(makeRoutedApi(routes({ 'GET /api/finance/statements': () => new Promise(() => {}) })))} />, { wrapper: wrapperFor() });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    cleanup();
    render(<ReconciliationPage hooks={hooksFor(makeRoutedApi(routes({ 'GET /api/finance/statements': () => Promise.reject(new ApiError(500, 'x')) })))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });

  describe('import', () => {
    it('OFX: needs an account and a file, then uploads and opens the new import', async () => {
      const user = userEvent.setup();
      const api = makeRoutedApi(routes({
        'UPLOAD /api/finance/statements': ok({ import: IMP, lines: 3, duplicates_skipped: 1, skipped_zero: 0, suggested: 2 }),
      }));
      render(<ReconciliationPage hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
      const form = await screen.findByRole('form', { name: 'Importar extrato' });
      await user.click(within(form).getByRole('button', { name: 'Importar extrato' }));
      expect(await within(form).findByText('Escolha primeiro a conta do extrato.')).toBeInTheDocument();
      await user.selectOptions(screen.getByLabelText('Conta'), 'acc-bank');
      await user.click(within(form).getByRole('button', { name: 'Importar extrato' }));
      expect(await within(form).findByText('Escolha o arquivo do extrato.')).toBeInTheDocument();
      await user.upload(within(form).getByLabelText('Escolher arquivo do extrato'), new File(['OFXHEADER'], 'out.ofx'));
      expect(within(form).queryByLabelText('Mapa das colunas do CSV')).not.toBeInTheDocument();
      await user.click(within(form).getByRole('button', { name: 'Importar extrato' }));
      await waitFor(() => expect(api.upload).toHaveBeenCalled());
      const f = api.upload.mock.calls[0][1] as FormData;
      expect(f.get('account_id')).toBe('acc-bank');
      expect(f.get('column_map')).toBeNull();
      expect(await screen.findByText(/3 linha\(s\) nova\(s\), 1 repetida\(s\) ignorada\(s\), 2 com sugestão/)).toBeInTheDocument();
      expect(await screen.findByText(/PIX MARIA/)).toBeInTheDocument();
    });

    it('CSV: asks for the column map, validates amount-xor-debit/credit, sends the map', async () => {
      const user = userEvent.setup();
      const api = makeRoutedApi(routes({ 'UPLOAD /api/finance/statements': ok({ import: IMP, lines: 1, duplicates_skipped: 0, skipped_zero: 0, suggested: 0 }) }));
      render(<ReconciliationPage hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
      await screen.findByRole('option', { name: 'Itaú' });
      await user.selectOptions(screen.getByLabelText('Conta'), 'acc-bank');
      const form = screen.getByRole('form', { name: 'Importar extrato' });
      await user.upload(within(form).getByLabelText('Escolher arquivo do extrato'), new File(['a;b'], 'extrato.csv'));
      const map = within(form).getByLabelText('Mapa das colunas do CSV');
      await user.click(within(form).getByRole('button', { name: 'Importar extrato' }));
      expect(await within(form).findByText('Informe as colunas de data e de descrição.')).toBeInTheDocument();
      await user.type(within(map).getByLabelText(/^Coluna da data/), 'Data');
      await user.type(within(map).getByLabelText(/^Coluna da descrição/), '1');
      await user.click(within(form).getByRole('button', { name: 'Importar extrato' }));
      expect(await within(form).findByText(/Informe a coluna de valor/)).toBeInTheDocument();
      await user.type(within(map).getByLabelText('Coluna do valor'), 'Valor');
      await user.type(within(map).getByLabelText('Coluna de débito'), 'Débito');
      await user.click(within(form).getByRole('button', { name: 'Importar extrato' }));
      expect(await within(form).findByText(/não os dois/)).toBeInTheDocument();
      expect(api.upload).not.toHaveBeenCalled();
      await user.clear(within(map).getByLabelText('Coluna de débito'));
      await user.click(within(form).getByRole('button', { name: 'Importar extrato' }));
      await waitFor(() => expect(api.upload).toHaveBeenCalled());
      const f = api.upload.mock.calls[0][1] as FormData;
      expect(f.get('format')).toBe('csv');
      expect(JSON.parse(f.get('column_map') as string)).toEqual({
        date: 'Data', description: 1, amount: 'Valor', delimiter: ';', date_format: 'dmy', decimal: 'comma', has_header: true, skip_rows: 0,
      });
    });

    it('surfaces a server refusal (duplicate statement)', async () => {
      const user = userEvent.setup();
      const api = makeRoutedApi(routes({ 'UPLOAD /api/finance/statements': () => Promise.reject(new ApiError(409, 'Este extrato já foi importado')) }));
      render(<ReconciliationPage hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
      await screen.findByRole('option', { name: 'Itaú' });
      await user.selectOptions(screen.getByLabelText('Conta'), 'acc-bank');
      const form = screen.getByRole('form', { name: 'Importar extrato' });
      await user.upload(within(form).getByLabelText('Escolher arquivo do extrato'), new File(['x'], 'a.ofx'));
      await user.click(within(form).getByRole('button', { name: 'Importar extrato' }));
      expect(await within(form).findByRole('alert')).toHaveTextContent('Este extrato já foi importado');
    });

    it('parseColumn: digits are indexes, text are header names', () => {
      expect(parseColumn(' 3 ')).toBe(3);
      expect(parseColumn('Data')).toBe('Data');
      expect(parseColumn('')).toBeUndefined();
    });
  });

  describe('gateway sync', () => {
    it('syncs a gateway account and lists what needs review; 202 partial asks to continue', async () => {
      const user = userEvent.setup();
      const api = makeRoutedApi(routes({
        'POST /api/finance/accounts/acc-gw/gateway-sync': ok({
          account_id: 'acc-gw', status: 'partial', pages: 5, fetched: 120, booked_fees: 40, booked_transfers: 3, already_booked: 70,
          review: [{ id: 'bt1', kind: 'chargeback', occurred_on: '2026-10-03', amount_cents: 5000, charge_id: 'c1', description: 'Contestação', reason: 'cobrança sem pedido' }],
          review_total: 1, error: null,
        }),
      }));
      render(<ReconciliationPage hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
      await user.click(await screen.findByRole('button', { name: 'Sincronizar agora' }));
      const result = await screen.findByText(/Buscadas 120 movimentações: 40 tarifa\(s\) e 3 repasse\(s\)/);
      expect(api.post).toHaveBeenCalledWith('/api/finance/accounts/acc-gw/gateway-sync', {});
      const box = result.closest('[role="status"]') as HTMLElement;
      expect(within(box).getByText(/Ainda há movimentações/)).toBeInTheDocument();
      expect(within(box).getByText(/Contestação .* cobrança sem pedido/)).toBeInTheDocument();
    });
    it('a failed sync shows the error and no result', async () => {
      const user = userEvent.setup();
      const api = makeRoutedApi(routes({ 'POST /api/finance/accounts/acc-gw/gateway-sync': () => Promise.reject(new ApiError(502, 'Gateway indisponível')) }));
      render(<ReconciliationPage hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
      await user.click(await screen.findByRole('button', { name: 'Sincronizar agora' }));
      expect(await screen.findByText(/Gateway indisponível/)).toBeInTheDocument();
    });
    it('is not offered without a gateway account', async () => {
      render(<ReconciliationPage hooks={hooksFor(makeRoutedApi(routes({ 'GET /api/finance/accounts': ok([{ ...ACC_GW, kind: 'checking', gateway: null }]) })))} isAdmin />, { wrapper: wrapperFor() });
      await screen.findByText(/Nenhum extrato|Extratos importados/);
      expect(screen.queryByRole('button', { name: 'Sincronizar agora' })).not.toBeInTheDocument();
    });
  });
});

describe('ExportsPanel', () => {
  it('staff: explains it is admin-only and offers no download', async () => {
    render(<ExportsPanel hooks={hooksFor(makeRoutedApi(baseRoutes()))} />, { wrapper: wrapperFor() });
    expect(screen.getByText(/Somente administradores/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Baixar/ })).not.toBeInTheDocument();
  });

  it('admin: downloads entries CSV, ledger OFX (account required) and DRE CSV with the period', async () => {
    const user = userEvent.setup();
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:y'), revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const api = makeRoutedApi(baseRoutes());
    render(<ExportsPanel hooks={hooksFor(api)} isAdmin now={new Date(2026, 9, 14)} />, { wrapper: wrapperFor() });
    const buttons = screen.getAllByRole('button', { name: /^Baixar/ });
    expect(buttons).toHaveLength(3);

    await user.click(buttons[0]);
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/entries.csv?from=2026-10-01&to=2026-10-14'));
    expect(await screen.findByText('Arquivo baixado.')).toBeInTheDocument();

    await user.click(buttons[1]);
    expect(await screen.findByText('Escolha a conta do razão.')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Conta'), 'acc-bank');
    await user.click(buttons[1]);
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/ledger.ofx?account_id=acc-bank&from=2026-10-01&to=2026-10-14'));

    await user.click(buttons[2]);
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/dre.csv?from=2026-10-01&to=2026-10-14'));
    expect(click).toHaveBeenCalledTimes(3);
    click.mockRestore();
  });

  it('shows a download failure', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi(baseRoutes());
    api.download.mockRejectedValueOnce(new ApiError(403, 'Sem permissão'));
    render(<ExportsPanel hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    await user.click(screen.getAllByRole('button', { name: /^Baixar/ })[0]);
    expect(await screen.findByRole('alert')).toHaveTextContent('Sem permissão');
  });
});
