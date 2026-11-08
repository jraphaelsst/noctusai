/**
 * Funnel organ — one board + card, two product contexts (an SW-like and a NoctusAI-like schema) against
 * a FAKE client that speaks the funnel contract. Reads like a user: roles and labels, `user-event`.
 */
/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FileText, Globe, Users } from 'lucide-react';
import * as React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '../../../design-system/ui/tooltip';
import type { PipelineApi, PipelineColumn, PipelineStage } from '../types';
import { createFunnelHooks } from './createFunnelHooks';
import { defineFunnel } from './defineFunnel';
import { FunnelBoard } from './FunnelBoard';
import { formatFunnelValue } from './format';
import type { FunnelCard, FunnelMeta } from './types';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

// ─── Fake server ────────────────────────────────────────────────────────────

const stage = (id: string, label: string, posicao: number, papel: string | null = null): PipelineStage => ({
  id,
  slug: id,
  label,
  cor: 'secondary',
  posicao,
  papel,
  ativo: true,
});
const STAGES = [stage('e1', 'Novo', 0), stage('e2', 'Proposta', 1, 'proposta_aceite'), stage('e3', 'Fechado', 2, 'final')];

const META: FunnelMeta = {
  pipeline: 'teste',
  papeis: ['proposta_aceite', 'final'],
  lost_reasons: [
    { codigo: 'preco', label: 'Preço', exige_texto: false },
    { codigo: 'outro', label: 'Outro', exige_texto: true },
  ],
  gates: { final: { codigo: 'cpf', inputs: [], mensagem: 'Faltam dados' } },
  acoes: [],
  campos_editaveis: ['observacao'],
};

function card(over: Partial<FunnelCard> = {}): FunnelCard {
  return {
    id: 'c1',
    etapa_id: 'e1',
    kanban_pos: 'a0',
    status: 'aberto',
    titulo: 'Ana Souza',
    subtitulo: '(11) 99999-0000',
    valor: 0,
    responsavel: { id: 'u1', nome: 'Rafa Lima' },
    badges: [{ label: 'Campanha', variant: 'default' }],
    motivo_perda_codigo: null,
    motivo_perda: null,
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-01T10:00:00Z',
    hub_entity_id: null,
    campos: { valor_unico: 18000, valor_mensal: 794, observacao: 'ligar amanhã' },
    ...over,
  };
}

function refusal(status: number, body: Record<string, unknown>) {
  return Object.assign(new Error(`[${status}] ${String(body.mensagem)}`), { status, body });
}

interface Fake {
  api: PipelineApi;
  cards: FunnelCard[];
  post: ReturnType<typeof vi.fn>;
  failMoveTo?: { etapa: string; error: Error };
}

function makeFake(initial: FunnelCard[]): Fake {
  const fake: Fake = { cards: initial, post: vi.fn(), api: undefined as unknown as PipelineApi };
  const columns = (status: string): PipelineColumn<FunnelCard>[] =>
    STAGES.map((s) => {
      const cards = fake.cards.filter((c) => c.etapa_id === s.id && c.status === status);
      return { etapa: s.id, stage: s, total: cards.length, valorTotal: 0, cards };
    });
  fake.api = {
    get: vi.fn(async (path: string, params?: Record<string, any>) => {
      if (path.endsWith('/meta')) return META;
      if (path.endsWith('/board')) return columns(params?.status ?? 'aberto');
      const m = path.match(/\/cards\/([^/]+)$/);
      if (m) return fake.cards.find((c) => c.id === m[1]) ?? null;
      if (path.endsWith('/movimentos')) return { items: [], total: 0, next_cursor: null };
      throw new Error(`unexpected GET ${path}`);
    }) as unknown as PipelineApi['get'],
    post: fake.post.mockImplementation(async (path: string, body: any) => {
      const m = path.match(/\/cards\/([^/]+)\/(.+)$/)!;
      const target = fake.cards.find((c) => c.id === m[1])!;
      if (m[2] === 'mover-etapa') {
        const fail = fake.failMoveTo;
        if (fail && fail.etapa === body.para_etapa_id) throw fail.error;
        Object.assign(target, { etapa_id: body.para_etapa_id });
        return target;
      }
      if (m[2] === 'perder') {
        Object.assign(target, { status: 'perdido', motivo_perda_codigo: body.motivo_codigo, motivo_perda: body.motivo_texto ?? null });
        return target;
      }
      throw new Error(`unexpected POST ${path}`);
    }) as unknown as PipelineApi['post'],
    patch: vi.fn() as unknown as PipelineApi['patch'],
    delete: vi.fn() as unknown as PipelineApi['delete'],
  };
  return fake;
}

// ─── Two product contexts: same organ, different schemas ────────────────────

const swLike = defineFunnel<FunnelCard>({
  id: 'sw',
  entityLabel: 'atendimento',
  face: {
    avatar: (c) => ({ label: c.titulo }),
    roleAction: (c, { stage: s }) => (s?.papel === 'proposta_aceite' ? { code: 'aceitar_proposta', label: 'Aceitar proposta' } : null),
  },
  actions: [{ code: 'aceitar_proposta', label: 'Aceitar proposta', placement: 'face' }],
  tabs: [
    { id: 'geral', label: 'Geral', icon: FileText, section: { kind: 'fields', fields: [{ key: 'observacao', label: 'Observação' }] } },
    { id: 'compradores', label: 'Compradores', icon: Users, order: 5, section: { kind: 'custom', render: () => <p>lista de compradores</p> } },
  ],
});

const nocLike = defineFunnel<FunnelCard>({
  id: 'noc',
  entityLabel: 'lead',
  face: { value: () => null, owner: () => null, chips: () => [] },
  tabs: [
    { id: 'origem', label: 'Origem', icon: Globe, section: { kind: 'fields', fields: [{ key: 'utm', label: 'UTM' }] } },
  ],
});

let qc: QueryClient;
let fake: Fake;

function mount(schema: typeof swLike, cards: FunnelCard[] = [card()]) {
  fake = makeFake(cards);
  const hooks = createFunnelHooks<FunnelCard>({ queryKey: `funil-${schema.schema.id}`, prefix: '/api/funil', entityLabel: schema.schema.entityLabel }, fake.api);
  render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <FunnelBoard funnel={schema} hooks={hooks} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return hooks;
}

const column = (id: string) => document.querySelector(`[data-kanban-column-id="${id}"]`) as HTMLElement;

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('funnel organ — one component, different contexts', () => {
  it('renders the same card differently per schema', async () => {
    mount(swLike);
    const face = await screen.findByTestId('funnel-card-c1');
    expect(within(face).getByText('Ana Souza')).toBeInTheDocument();
    expect(within(face).getByText('(11) 99999-0000')).toBeInTheDocument();
    expect(within(face).getByText('Campanha')).toBeInTheDocument();
    expect(within(face).getByText('Rafa Lima')).toBeInTheDocument();
    // one-off + monthly
    expect(face.textContent).toMatch(/R\$\s18\.000,00 \+ R\$\s794,00\/mês/);
    cleanup();

    mount(nocLike);
    const bare = await screen.findByTestId('funnel-card-c1');
    expect(within(bare).queryByText('Campanha')).not.toBeInTheDocument();
    expect(within(bare).queryByText('Rafa Lima')).not.toBeInTheDocument();
    expect(bare.textContent).not.toMatch(/R\$/);
  });

  it('declares tabs per context in the detail dialog', async () => {
    const user = userEvent.setup();
    mount(swLike);
    await user.click(await screen.findByRole('button', { name: 'Ana Souza' }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('ligar amanhã')).toBeInTheDocument();
    // rail items are labelled; the product-declared tab exists in SW's context only
    expect(within(dialog).getByRole('button', { name: /Compradores/ })).toBeInTheDocument();
    cleanup();
    mount(nocLike);
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Ana Souza' }));
    const d2 = await screen.findByRole('dialog');
    expect(within(d2).queryByRole('button', { name: /Compradores/ })).not.toBeInTheDocument();
    // a missing value is "—", never 0
    expect(await within(d2).findByText('—')).toBeInTheDocument();
  });

  it('opens a card from the keyboard (the title is a button)', async () => {
    const user = userEvent.setup();
    mount(swLike);
    const title = await screen.findByRole('button', { name: 'Ana Souza' });
    title.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('gives every icon-only control an accessible name', async () => {
    mount(swLike);
    await screen.findByTestId('funnel-card-c1');
    for (const b of screen.getAllByRole('button')) {
      expect((b.textContent ?? '').trim() || b.getAttribute('aria-label')).toBeTruthy();
    }
  });
});

describe('moving without drag', () => {
  it('moves through the "Mover para…" menu and lands in the new column', async () => {
    const user = userEvent.setup();
    mount(swLike);
    await user.click(await screen.findByRole('button', { name: 'Mover Ana Souza para…' }));
    await user.click(await screen.findByRole('button', { name: 'Proposta' }));
    expect(fake.post).toHaveBeenCalledWith(
      '/api/funil/cards/c1/mover-etapa',
      expect.objectContaining({ para_etapa_id: 'e2' }),
    );
    await waitFor(() => expect(within(column('e2')).getByText('Ana Souza')).toBeInTheDocument());
    expect(within(column('e1')).queryByText('Ana Souza')).not.toBeInTheDocument();
    // role action appears in the stage that declares it
    expect(await screen.findByRole('button', { name: 'Aceitar proposta' })).toBeInTheDocument();
  });

  it('moves through the "Etapa" select in the card header', async () => {
    const user = userEvent.setup();
    mount(swLike);
    await user.click(await screen.findByRole('button', { name: 'Ana Souza' }));
    const dialog = await screen.findByRole('dialog');
    await user.selectOptions(await within(dialog).findByLabelText('Etapa'), 'e2');
    await waitFor(() =>
      expect(fake.post).toHaveBeenCalledWith('/api/funil/cards/c1/mover-etapa', expect.objectContaining({ para_etapa_id: 'e2' })),
    );
    await waitFor(() => expect(within(column('e2')).getByText('Ana Souza')).toBeInTheDocument());
  });

  it('a refused gate snaps the card back and says what is missing', async () => {
    const user = userEvent.setup();
    mount(swLike);
    fake.failMoveTo = {
      etapa: 'e3',
      error: refusal(409, {
        code: 'gate_refused',
        mensagem: 'Faltam dados para fechar.',
        gate: 'cpf',
        pendencias: [{ codigo: 'cpf', label: 'CPF do comprador' }],
      }),
    };
    await user.click(await screen.findByRole('button', { name: 'Mover Ana Souza para…' }));
    await user.click(await screen.findByRole('button', { name: 'Fechado' }));
    const alert = await screen.findByTestId('funnel-board-refusal');
    expect(alert).toHaveTextContent('Faltam dados para fechar.');
    expect(alert).toHaveTextContent('CPF do comprador');
    await waitFor(() => expect(within(column('e1')).getByText('Ana Souza')).toBeInTheDocument());
    expect(within(column('e3')).queryByText('Ana Souza')).not.toBeInTheDocument();
  });
});

describe('lose flow', () => {
  it('requires the text for "Outro", then removes the card from the open board', async () => {
    const user = userEvent.setup();
    mount(swLike);
    await user.click(await screen.findByRole('button', { name: 'Mover Ana Souza para…' }));
    await user.click(await screen.findByRole('button', { name: 'Marcar como perdido…' }));
    const dialog = await screen.findByRole('dialog', { name: /Marcar como perdido/ });

    // nothing chosen
    await user.click(within(dialog).getByRole('button', { name: 'Marcar como perdido' }));
    expect(await within(dialog).findByText('Escolha um motivo.')).toBeInTheDocument();
    expect(fake.post).not.toHaveBeenCalledWith(expect.stringContaining('/perder'), expect.anything());

    // "Outro" without text
    await user.click(within(dialog).getByRole('radio', { name: 'Outro' }));
    await user.click(within(dialog).getByRole('button', { name: 'Marcar como perdido' }));
    expect(await within(dialog).findByText(/o texto é obrigatório/)).toBeInTheDocument();
    expect(fake.post).not.toHaveBeenCalledWith(expect.stringContaining('/perder'), expect.anything());

    // with text
    await user.type(within(dialog).getByLabelText(/Detalhes/), 'Comprou do concorrente');
    await user.click(within(dialog).getByRole('button', { name: 'Marcar como perdido' }));
    await waitFor(() =>
      expect(fake.post).toHaveBeenCalledWith('/api/funil/cards/c1/perder', {
        motivo_codigo: 'outro',
        motivo_texto: 'Comprou do concorrente',
      }),
    );
    await waitFor(() => expect(screen.queryByTestId('funnel-card-c1')).not.toBeInTheDocument());
  });
});

describe('helpers', () => {
  it('formats one-off + monthly, single value, and nothing', () => {
    expect(formatFunnelValue({ valor: 0, campos: {} })).toBeNull();
    expect(formatFunnelValue({ valor: 500, campos: {} })).toMatch(/R\$\s500,00/);
    expect(formatFunnelValue({ valor: 0, campos: { valor_mensal: 794 } })).toMatch(/^R\$\s794,00\/mês$/);
  });

  it('defineFunnel refuses a duplicate tab id', () => {
    expect(() =>
      defineFunnel({
        id: 'x',
        entityLabel: 'x',
        tabs: [
          { id: 'a', label: 'A', icon: FileText, section: { kind: 'geral' } },
          { id: 'a', label: 'B', icon: FileText, section: { kind: 'geral' } },
        ],
      }),
    ).toThrow(/duplicado/);
  });
});
