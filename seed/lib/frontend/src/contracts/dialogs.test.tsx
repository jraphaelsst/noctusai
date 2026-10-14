import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContractSuspendDialog } from './ContractSuspendDialog';
import { ContractTerminateDialog } from './ContractTerminateDialog';
import { ContractTimeline } from './ContractTimeline';
import { ContractBillingPreview } from './ContractBillingPreview';
import { ApiError } from '../api';
import { contract, ok, setup, version } from './testUtils';

afterEach(cleanup);

describe('ContractSuspendDialog', () => {
  it('requires a reason, then suspends and reports', async () => {
    const user = userEvent.setup();
    const s = setup({ 'POST /api/contracts/c1/suspend': ok(contract({ status: 'suspended' })) });
    const done = vi.fn();
    const close = vi.fn();
    render(<s.Wrapper><ContractSuspendDialog hooks={s.hooks} contractId="c1" open onClose={close} onDone={done} /></s.Wrapper>);
    await user.click(screen.getByRole('button', { name: 'Suspender' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Informe o motivo.');
    expect(s.api.post).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('Motivo da suspensão'), ' inadimplência ');
    await user.click(screen.getByRole('button', { name: 'Suspender' }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(s.api.post).toHaveBeenCalledWith('/api/contracts/c1/suspend', { reason: 'inadimplência' });
    expect(close).toHaveBeenCalled();
  });
});

describe('ContractTerminateDialog', () => {
  const c = contract({ notice_days: 30, terminable_from: '2026-12-01', penalty_cents: 100000, penalty_bp: 1000 });

  it('explains the notice and sends the default effective date', async () => {
    const user = userEvent.setup();
    const s = setup({ 'POST /api/contracts/c1/terminate': ok(contract({ status: 'terminated' })) });
    render(<s.Wrapper><ContractTerminateDialog hooks={s.hooks} contract={c} open onClose={() => undefined} /></s.Wrapper>);
    expect(screen.getByText('Aviso prévio de 30 dias: encerramento a partir de 01/12/2026.')).toBeInTheDocument();
    expect(screen.queryByText('Dispensar aviso prévio (encerrar antes)')).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Motivo do encerramento'), 'Fim do projeto');
    await user.click(screen.getByRole('button', { name: 'Encerrar contrato' }));
    await waitFor(() => expect(s.api.post).toHaveBeenCalledWith('/api/contracts/c1/terminate', {
      reason: 'Fim do projeto', effective_on: '2026-12-01', waive_notice: false, waive_penalty: false,
    }));
  });

  it('an earlier date reveals the waiver + the penalty, and sends the waivers', async () => {
    const user = userEvent.setup();
    const s = setup({ 'POST /api/contracts/c1/terminate': ok(contract({ status: 'terminated' })) });
    render(<s.Wrapper><ContractTerminateDialog hooks={s.hooks} contract={c} open onClose={() => undefined} /></s.Wrapper>);
    const date = screen.getByLabelText('Data de encerramento');
    await user.clear(date);
    await user.type(date, '2026-11-15');
    await user.click(screen.getByLabelText('Dispensar aviso prévio (encerrar antes)'));
    expect(screen.getByText(/multa de R\$\s*1\.000,00 \+ 10,00% do saldo/)).toBeInTheDocument();
    await user.click(screen.getByLabelText('Dispensar a multa rescisória'));
    await user.type(screen.getByLabelText('Motivo do encerramento'), 'x');
    await user.click(screen.getByRole('button', { name: 'Encerrar contrato' }));
    await waitFor(() => expect(s.api.post).toHaveBeenCalledWith('/api/contracts/c1/terminate', expect.objectContaining({ effective_on: '2026-11-15', waive_notice: true, waive_penalty: true })));
  });

  it('the server notice refusal is shown in pt-BR and the dialog stays', async () => {
    const user = userEvent.setup();
    const s = setup({ 'POST /api/contracts/c1/terminate': () => { throw new ApiError(409, 'x', { error: { code: 'aviso_previo_nao_cumprido', message: 'x' } }); } });
    const close = vi.fn();
    render(<s.Wrapper><ContractTerminateDialog hooks={s.hooks} contract={c} open onClose={close} /></s.Wrapper>);
    await user.type(screen.getByLabelText('Motivo do encerramento'), 'x');
    await user.click(screen.getByRole('button', { name: 'Encerrar contrato' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('O aviso prévio não foi cumprido');
    expect(close).not.toHaveBeenCalled();
  });
});

describe('ContractTimeline', () => {
  it('lists versions newest first with the changes diff formatted (money, percent, dates)', async () => {
    const s = setup({ 'GET /api/contracts/c1/versions': ok([
      version(),
      version({ id: 'v2', version_n: 2, kind: 'readjustment', summary: 'Reajuste IPCA de 4,50%', changes: { amount_cents: { from: 150000, to: 156750 }, percent_bp: { from: null, to: 450 } } }),
      version({ id: 'v3', version_n: 3, kind: 'amendment', summary: 'Prorrogação', changes: { end_date: { from: '2026-12-31', to: '2027-12-31' } } }),
    ]) });
    render(<s.Wrapper><ContractTimeline hooks={s.hooks} contractId="c1" /></s.Wrapper>);
    const items = Array.from((await screen.findByRole('list', { name: 'Histórico de versões' })).children);
    expect(items[0]).toHaveTextContent('Aditivo');
    expect(items[0]).toHaveTextContent('Fim: 31/12/2026 → 31/12/2027');
    expect(items[1]).toHaveTextContent(/Valor: R\$\s*1\.500,00 → R\$\s*1\.567,50/);
    expect(items[1]).toHaveTextContent('Percentual: — → 4,50%');
    expect(items[2]).toHaveTextContent('Termos iniciais');
  });

  it('empty and error states are honest', async () => {
    const s = setup({ 'GET /api/contracts/c1/versions': ok([]), 'GET /api/contracts/c2/versions': () => { throw new ApiError(500, 'x', {}); } });
    render(<s.Wrapper><ContractTimeline hooks={s.hooks} contractId="c1" /></s.Wrapper>);
    expect(await screen.findByText('Sem versões registradas.')).toBeInTheDocument();
    cleanup();
    render(<s.Wrapper><ContractTimeline hooks={s.hooks} contractId="c2" /></s.Wrapper>);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});

describe('ContractBillingPreview', () => {
  it('lists the upcoming receivables and the running retainer month', async () => {
    const s = setup({ 'GET /api/contracts/c1/billing-preview': ok({
      items: [{ period_key: 'i2', kind: 'fixed', due_date: '2026-12-10', competence_month: '2026-12-01', amount_cents: 33333, description: 'Contrato (parcela 2/3)' }],
      billed: 1, running_month: { month: '2026-11', minutes: 660, included_minutes: 600, excess_cents: 12000 },
    }) });
    render(<s.Wrapper><ContractBillingPreview hooks={s.hooks} contractId="c1" count={3} /></s.Wrapper>);
    expect(await screen.findByText('Contrato (parcela 2/3)')).toBeInTheDocument();
    expect(screen.getByText('10/12/2026')).toBeInTheDocument();
    expect(screen.getByText(/R\$\s*333,33/)).toBeInTheDocument();
    expect(screen.getByText('1 já faturadas')).toBeInTheDocument();
    expect(screen.getByText(/Mês corrente: 11h de 10h — excedente estimado R\$\s*120,00/)).toBeInTheDocument();
    expect(s.api.get).toHaveBeenCalledWith('/api/contracts/c1/billing-preview', { count: 3 });
  });

  it('nothing to bill is stated', async () => {
    const s = setup({ 'GET /api/contracts/c1/billing-preview': ok({ items: [], billed: 0 }) });
    render(<s.Wrapper><ContractBillingPreview hooks={s.hooks} contractId="c1" /></s.Wrapper>);
    expect(await screen.findByText('Nenhuma cobrança futura prevista.')).toBeInTheDocument();
  });
});
