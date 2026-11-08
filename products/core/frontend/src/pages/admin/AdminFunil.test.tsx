/**
 * Admin > Funil: the page mounts the seed funnel organ on `/api/admin/funnel` with core's declared tabs; the nav
 * lists it under Comercial; the Oferta tab saves one-off + monthly apart and shows a server refusal inline.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

const { api } = vi.hoisted(() => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    download: vi.fn(),
  },
}));
vi.mock('../../lib/api', () => ({ api }));
vi.mock('../../lib/auth-context', () => ({ useAuth: () => ({ isAdmin: true }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { NAV_GROUPS } from '../../components/layout/Layout';
import { AdminFunil } from './AdminFunil';
import { OfertaSection, parseMoney } from './funil/OfertaSection';
import type { NocCard } from './funil/hooks';

const stage = (id: string, label: string, posicao: number) => ({
  id,
  slug: id,
  label,
  cor: 'secondary',
  posicao,
  papel: null,
  ativo: true,
});
const STAGES = [stage('e1', 'Novo', 0), stage('e2', 'Contatado', 1)];
const CARD: NocCard = {
  id: 'c1',
  etapa_id: 'e1',
  kanban_pos: '0',
  status: 'aberto',
  titulo: 'Ana Souza',
  subtitulo: 'Acme',
  valor: 0,
  responsavel: null,
  badges: [{ label: 'Contato', variant: 'secondary' }],
  motivo_perda_codigo: null,
  motivo_perda: null,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:00Z',
  hub_entity_id: null,
  campos: { oferta_tipo: null, valor_unico: null, valor_mensal: null, oferta_descricao: null },
};
const META = {
  pipeline: 'funil_noc',
  papeis: ['novo', 'contatado'],
  lost_reasons: [{ codigo: 'preco', label: 'Achou caro', exige_texto: false }],
  gates: {},
  acoes: [{ codigo: 'ganhar', label: 'Marcar como ganho', papeis: [] }],
  campos_editaveis: ['valor_unico', 'valor_mensal', 'oferta_tipo', 'oferta_descricao'],
};

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('nav', () => {
  it('lists Funil first under Administração > Comercial', () => {
    const admin = NAV_GROUPS.find((g) => g.key === 'admin')!;
    const comercial = admin.groups!.find((g) => g.key === 'comercial')!;
    expect(comercial.items[0]).toMatchObject({ name: 'Funil', href: '/admin/funil' });
  });
});

describe('AdminFunil page', () => {
  it('renders the board from /api/admin/funnel with one column per stage', async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path === '/api/admin/funnel/meta') return META;
      if (path === '/api/admin/funnel/board') {
        return STAGES.map((s, i) => ({ etapa: s.id, stage: s, total: i === 0 ? 1 : 0, valorTotal: 0, cards: i === 0 ? [CARD] : [] }));
      }
      throw new Error(`unexpected GET ${path}`);
    });
    wrap(<AdminFunil />);
    expect(screen.getByRole('heading', { level: 1, name: 'Funil' })).toBeInTheDocument();
    expect(await screen.findByText('Ana Souza')).toBeInTheDocument();
    expect(screen.getByText('Contatado')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Novo contato' })).toBeInTheDocument();
    expect(api.get.mock.calls.every(([p]) => String(p).startsWith('/api/admin/funnel/'))).toBe(true);
  });
});

describe('parseMoney', () => {
  it('reads pt-BR and plain numbers, empty as null, junk as NaN', () => {
    expect(parseMoney('1.234,50')).toBe(1234.5);
    expect(parseMoney('18000')).toBe(18000);
    expect(parseMoney('  ')).toBeNull();
    expect(parseMoney('abc')).toBeNaN();
    expect(parseMoney('-5')).toBeNaN();
  });
});

describe('OfertaSection', () => {
  it('refuses a non-number before any request, in pt-BR', async () => {
    wrap(<OfertaSection card={CARD} />);
    fireEvent.change(screen.getByLabelText('Valor único (R$)'), { target: { value: 'abc' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar oferta' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Informe os valores como número positivo');
    expect(api.patch).not.toHaveBeenCalled();
  });

  it('saves the one-off and the monthly value apart', async () => {
    api.patch.mockResolvedValue({ data: { ...CARD, campos: { ...CARD.campos, valor_unico: 18000, valor_mensal: 794.9 } } });
    wrap(<OfertaSection card={CARD} />);
    fireEvent.change(screen.getByLabelText('O que está sendo oferecido'), { target: { value: 'projeto' } });
    fireEvent.change(screen.getByLabelText('Valor único (R$)'), { target: { value: '18000' } });
    fireEvent.change(screen.getByLabelText('Valor mensal (R$/mês)'), { target: { value: '794,90' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar oferta' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch).toHaveBeenCalledWith('/api/admin/funnel/cards/c1', {
      oferta_tipo: 'projeto',
      oferta_descricao: null,
      valor_unico: 18000,
      valor_mensal: 794.9,
    });
  });

  it('shows the server refusal inline', async () => {
    api.patch.mockRejectedValue(
      Object.assign(new Error('[409] Contato já fechado'), {
        status: 409,
        body: { error: { code: 'card_fechado', message: 'Este contato já está fechado.', details: null } },
      }),
    );
    wrap(<OfertaSection card={CARD} />);
    fireEvent.change(screen.getByLabelText('Valor único (R$)'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar oferta' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Este contato já está fechado.');
  });
});
