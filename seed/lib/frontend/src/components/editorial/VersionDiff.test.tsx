/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { VersionDiff } from './VersionDiff';
import { FakeEditorialDataSource } from './dataSource';
import { mkItem, mkVersion } from './fixtures';

afterEach(cleanup);

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('VersionDiff', () => {
  it('empty: prompts to pick versions', () => {
    wrap(<VersionDiff />);
    expect(screen.getByText('Selecione duas versões para comparar.')).toBeInTheDocument();
  });

  it('identical versions say so', () => {
    wrap(<VersionDiff before={mkVersion(1, { a: 1 })} after={mkVersion(2, { a: 1 })} />);
    expect(screen.getByText(/mesmo conteúdo/)).toBeInTheDocument();
  });

  it('shows only changed fields with kinds; markdown fields render as markdown', () => {
    wrap(
      <VersionDiff
        before={mkVersion(1, { titulo: 'A', corpo: '## Velho', fixo: 1, gone: 1 })}
        after={mkVersion(2, { titulo: 'B', corpo: '## Novo', fixo: 1, extra: true })}
      />,
    );
    expect(screen.getByText('titulo')).toBeInTheDocument();
    expect(screen.queryByText('fixo')).not.toBeInTheDocument();
    expect(screen.getAllByText('Alterado')).toHaveLength(2);
    expect(screen.getByText('Adicionado')).toBeInTheDocument();
    expect(screen.getByText('Removido')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Velho' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Novo' })).toBeInTheDocument();
  });

  it('fetch mode: skeleton, then diff', async () => {
    const ds = new FakeEditorialDataSource({
      details: {
        i1: {
          item: mkItem(),
          versions: [mkVersion(1, { t: 'x' }), mkVersion(2, { t: 'y' })],
          events: [],
        },
      },
    });
    wrap(<VersionDiff dataSource={ds} itemId="i1" fromN={1} toN={2} />);
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(await screen.findByText('Alterado')).toBeInTheDocument();
  });

  it('fetch mode: error with retry', async () => {
    const ds = new FakeEditorialDataSource();
    wrap(<VersionDiff dataSource={ds} itemId="nope" fromN={1} toN={2} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Item não encontrado.');
    expect(screen.getByRole('button', { name: /tentar novamente/i })).toBeInTheDocument();
  });
});
