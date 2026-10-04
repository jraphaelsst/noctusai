/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ReviewQueue } from './ReviewQueue';
import { FakeEditorialDataSource } from './dataSource';
import { mkItem } from './fixtures';
import type { EditorialDataSource } from './types';

afterEach(cleanup);

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const items = [
  mkItem({ id: 'a', ref: 'A', title: 'Atividade A', state: 'rascunho' }),
  mkItem({ id: 'b', ref: 'B', title: 'Atividade B', state: 'revisao_editorial' }),
  mkItem({ id: 'c', ref: 'C', title: 'Atividade C', state: 'revisao_editorial' }),
];

describe('ReviewQueue', () => {
  it('shows a busy skeleton while there is no data', () => {
    const ds: EditorialDataSource = { ...new FakeEditorialDataSource(), listQueue: () => new Promise(() => {}) } as any;
    wrap(<ReviewQueue dataSource={ds} />);
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it('shows error with retry', async () => {
    const ds = new FakeEditorialDataSource();
    ds.listQueue = async () => {
      throw new Error('boom');
    };
    wrap(<ReviewQueue dataSource={ds} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
    expect(screen.getByRole('button', { name: /tentar novamente/i })).toBeInTheDocument();
  });

  it('shows the empty state', async () => {
    wrap(<ReviewQueue dataSource={new FakeEditorialDataSource()} />);
    expect(await screen.findByText('Nenhum item editorial ainda.')).toBeInTheDocument();
  });

  it('renders items with per-state counts and filters by state', async () => {
    const ds = new FakeEditorialDataSource({ items });
    wrap(<ReviewQueue dataSource={ds} />);
    expect(await screen.findByText('Atividade A')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Todos (3)' })).toBeInTheDocument();
    const btn = screen.getByRole('button', { name: 'Revisão editorial (2)' });
    await userEvent.click(btn);
    await waitFor(() => expect(screen.queryByText('Atividade A')).not.toBeInTheDocument());
    expect(screen.getByText('Atividade B')).toBeInTheDocument();
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    expect(ds.calls[ds.calls.length - 1]).toMatchObject({ state: 'revisao_editorial', page: 1 });
  });

  it('awaiting-me filter narrows items and counts', async () => {
    const ds = new FakeEditorialDataSource({ items, awaitingMe: ['b'] });
    wrap(<ReviewQueue dataSource={ds} />);
    await screen.findByText('Atividade A');
    await userEvent.click(screen.getByLabelText('Aguardando minha ação'));
    await waitFor(() => expect(screen.queryByText('Atividade A')).not.toBeInTheDocument());
    expect(screen.getByText('Atividade B')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Todos (1)' })).toBeInTheDocument();
  });

  it('keeps content mounted while a filter change refetches (no skeleton over data)', async () => {
    const ds = new FakeEditorialDataSource({ items });
    const orig = ds.listQueue.bind(ds);
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    wrap(<ReviewQueue dataSource={ds} />);
    await screen.findByText('Atividade A');
    ds.listQueue = async (p) => {
      await gate;
      return orig(p);
    };
    await userEvent.click(screen.getByRole('button', { name: /^Revisão editorial \(/ }));
    expect(screen.getByText('Atividade A')).toBeInTheDocument();
    expect(document.querySelector('[aria-busy="true"]')).toBeNull();
    release();
    await waitFor(() => expect(screen.queryByText('Atividade A')).not.toBeInTheDocument());
  });

  it('calls onSelect and pages', async () => {
    const ds = new FakeEditorialDataSource({ items });
    let picked = '';
    wrap(<ReviewQueue dataSource={ds} pageSize={2} onSelect={(i) => (picked = i.id)} />);
    await userEvent.click(await screen.findByText('Atividade A'));
    expect(picked).toBe('a');
    await userEvent.click(screen.getByRole('button', { name: 'Próxima' }));
    expect(await screen.findByText('Atividade C')).toBeInTheDocument();
    expect(screen.getByText('Página 2 de 2')).toBeInTheDocument();
  });
});
