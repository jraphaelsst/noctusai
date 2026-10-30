/**
 * Admin > Operação — a recording fake HTTP client behind the real
 * `createOperationsApi`, injected with `OperationsApiProvider` (no module
 * mocking of our own code). Each tab: loading never shows an empty state,
 * the data renders, the empty and error states are explicit.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AdminOperacao } from './AdminOperacao';
import { OperationsApiProvider, createOperationsApi } from '../../lib/operations';
import { deferred, fakeHttp, type FakeHttp } from '../../test/billing-harness';

afterEach(() => cleanup());

function renderAt(http: FakeHttp, path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OperationsApiProvider value={createOperationsApi(http)}>
        <MemoryRouter initialEntries={[path]}>
          <AdminOperacao />
        </MemoryRouter>
      </OperationsApiProvider>
    </QueryClientProvider>,
  );
}

const ROUTINES = {
  generated_at: '2026-10-29T10:00:00+00:00',
  timezone: 'America/Sao_Paulo',
  window_hours: 24,
  brief: { job: 'core_owner_daily_brief', last_ok_at: null, last_generated_at: null, missing: true, deadman_hours: 26 },
  totals: { jobs: 2, runs_24h: 5, errors_24h: 1, overdue: 1 },
  products: [
    {
      product: 'social-wiring',
      active: true,
      failing: 2,
      jobs: [
        {
          job: 'sw_tick', cron: null, interval_seconds: 300, timezone: 'America/Sao_Paulo', last_seen_at: null,
          registered: true, runs_24h: 5, errors_24h: 1, overdue: false, expected_at: null,
          last_run: { started_at: '2026-10-29T09:58:00+00:00', status: 'error', error: 'RuntimeError: waha 502', duration_ms: 20 },
        },
        {
          job: 'sw_nightly', cron: '0 3 * * *', interval_seconds: null, timezone: 'America/Sao_Paulo', last_seen_at: null,
          registered: true, runs_24h: 0, errors_24h: 0, overdue: true, expected_at: '2026-10-29T06:00:00+00:00',
          last_run: null,
        },
      ],
    },
  ],
};

const BRIEF = {
  id: 'b-1', generated_at: '2026-10-29T10:00:00+00:00', trigger: 'schedule',
  text_body: '[NoctusAI] Brief diário 29/10 — 2 exceção(ões)\n\n## Rotinas\n- FALHOU · social-wiring / sw_tick',
  exceptions_count: 2, in_app_sent: 1, email_status: 'sent',
};

describe('AdminOperacao — Rotinas', () => {
  it('shows a skeleton while loading, then failures and the missing brief', async () => {
    const pending = deferred<unknown>();
    renderAt(fakeHttp({ 'GET /api/admin/operations/routines': () => pending.promise }), '/admin/operacao');
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0);
    expect(screen.queryByText(/Nenhuma rotina/)).toBeNull();
    pending.resolve({ data: ROUTINES });
    expect(await screen.findByText('sw_tick')).toBeTruthy();
    expect(screen.getByText('RuntimeError: waha 502')).toBeTruthy();
    expect(screen.getByText(/Faltando \(esperada/)).toBeTruthy();
    expect(screen.getByText('2 com problema')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('Brief diário ausente');
  });

  it('opens a job history on demand', async () => {
    const http = fakeHttp({
      'GET /api/admin/operations/routines': () => ({ data: ROUTINES }),
      'GET /api/admin/operations/runs': () => ({
        data: [{ product: 'social-wiring', job: 'sw_tick', started_at: '2026-10-29T09:58:00+00:00', status: 'ok', duration_ms: 7 }],
      }),
    });
    renderAt(http, '/admin/operacao/rotinas');
    const [button] = await screen.findAllByRole('button', { name: 'Histórico' });
    fireEvent.click(button);
    expect(await screen.findByText('7 ms')).toBeTruthy();
    expect(http.calls.some((c) => c.path.includes('job=sw_tick'))).toBe(true);
  });

  it('says so when nothing is registered', async () => {
    const empty = { ...ROUTINES, products: [], totals: { jobs: 0, runs_24h: 0, errors_24h: 0, overdue: 0 } };
    renderAt(fakeHttp({ 'GET /api/admin/operations/routines': () => ({ data: empty }) }), '/admin/operacao/rotinas');
    expect(await screen.findByText(/Nenhuma rotina registrada ainda/)).toBeTruthy();
  });

  it('surfaces a load error with a retry', async () => {
    renderAt(
      fakeHttp({ 'GET /api/admin/operations/routines': () => { throw new Error('[403] Restrito'); } }),
      '/admin/operacao/rotinas',
    );
    expect(await screen.findByRole('button', { name: /tentar novamente/i })).toBeTruthy();
  });
});

describe('AdminOperacao — Saúde', () => {
  it('lists containers and flags a stopped one', async () => {
    renderAt(
      fakeHttp({
        'GET /api/fleet': () => ({
          products: [
            { slug: 'core', container: 'noctus-core', display: 'Core', state: 'running', health: 'healthy', running: true },
            { slug: 'igig', container: 'noctus-igig', display: 'iGig', state: 'exited', health: 'none', running: false },
          ],
        }),
      }),
      '/admin/operacao/saude',
    );
    expect(await screen.findByText('iGig')).toBeTruthy();
    expect(screen.getByText('exited')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Fleet Control' }).getAttribute('href')).toBe('/admin/fleet');
  });
});

describe('AdminOperacao — Modelos de IA', () => {
  it('groups the catalog by provider', async () => {
    renderAt(
      fakeHttp({
        'GET /api/admin/operations/models': () => ({
          data: [
            { id: 'gpt-4o-mini', label: 'GPT-4o mini', provider: 'openai', kind: 'chat', stub: false, description: '',
              cost_per_1m_input_tokens: 0.15, cost_per_1m_output_tokens: 0.6, supports_batch: true, tag_performance: null, priced: true },
          ],
        }),
      }),
      '/admin/operacao/modelos',
    );
    expect(await screen.findByText('GPT-4o mini')).toBeTruthy();
    expect(screen.getByText('openai')).toBeTruthy();
    expect(screen.getByText('$0.15')).toBeTruthy();
  });
});

describe('AdminOperacao — Custos', () => {
  it('shows LLM spend and the cost ledger, and an unavailable source honestly', async () => {
    const ledger = { per_org: [{ org_id: 'o1', org_name: 'Imobiliária X', amount_brl: 12.5, pending_fx: 0, by_category: {} }], total_brl: 12.5, pending_fx: 0 };
    renderAt(
      fakeHttp({
        'GET /api/admin/operations/costs': () => ({
          data: {
            timezone: 'America/Sao_Paulo',
            yesterday: { from: '', to: '' },
            llm_yesterday: { available: false, error: 'TypeError: x', per_product: [], total_usd: null, calls: null },
            cost_ledger_yesterday: ledger,
            cost_ledger_month: { per_org: [], total_brl: 0, pending_fx: 0 },
          },
        }),
      }),
      '/admin/operacao/custos',
    );
    expect(await screen.findByText(/Fonte de uso de IA indisponível/)).toBeTruthy();
    expect(screen.getByText('Imobiliária X')).toBeTruthy();
    expect(screen.getByText('Nenhum custo registrado.')).toBeTruthy();
  });
});

describe('AdminOperacao — Brief', () => {
  it('renders the latest brief and prepends a generated one', async () => {
    const stored: unknown[] = [BRIEF];
    const http = fakeHttp({
      'GET /api/admin/operations/briefs': () => ({ data: [...stored] }),
      'POST /api/admin/operations/briefs': () => {
        const brief = { ...BRIEF, id: 'b-2', trigger: 'manual', text_body: 'Prévia manual', exceptions_count: 0, email_status: 'not_sent' };
        stored.unshift(brief);
        return { data: brief };
      },
    });
    renderAt(http, '/admin/operacao/brief');
    expect(await screen.findByText(/FALHOU · social-wiring \/ sw_tick/)).toBeTruthy();
    expect(screen.getByText('e-mail enviado')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Gerar agora (prévia)' }));
    expect(await screen.findByText('Prévia manual')).toBeTruthy();
    await waitFor(() => expect(http.calls.filter((c) => c.method === 'POST')).toHaveLength(1));
  });

  it('has an explicit empty state', async () => {
    renderAt(fakeHttp({ 'GET /api/admin/operations/briefs': () => ({ data: [] }) }), '/admin/operacao/brief');
    expect(await screen.findByText('Nenhum brief gerado ainda.')).toBeTruthy();
  });
});
