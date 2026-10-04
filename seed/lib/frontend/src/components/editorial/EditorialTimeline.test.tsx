/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { EditorialTimeline } from './EditorialTimeline';
import { mkEvent } from './fixtures';

afterEach(cleanup);

describe('EditorialTimeline', () => {
  it('loading: busy only when there is no data', () => {
    render(<EditorialTimeline events={undefined} isPending />);
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it('does not unmount events while refreshing; shows indicator', () => {
    render(<EditorialTimeline events={[mkEvent(1)]} isPending isRefreshing />);
    expect(document.querySelector('[aria-busy="true"]')).toBeNull();
    expect(screen.getByRole('status', { name: 'Atualizando' })).toBeInTheDocument();
    expect(screen.getByText(/enviou para revisão/)).toBeInTheDocument();
  });

  it('error with retry', async () => {
    const onRetry = vi.fn();
    render(<EditorialTimeline events={undefined} error={new Error('falhou')} onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('falhou');
    await userEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(onRetry).toHaveBeenCalled();
  });

  it('empty', () => {
    render(<EditorialTimeline events={[]} />);
    expect(screen.getByText('Nenhum evento registrado ainda.')).toBeInTheDocument();
  });

  it('success: who, what, when, version, motivo, transition; chronological', () => {
    render(
      <EditorialTimeline
        actorName={(id) => (id === 'u2' ? 'Mônica' : id)}
        events={[
          mkEvent(2, {
            actor_id: 'u2',
            action: 'send_back',
            from_state: 'revisao_editorial',
            to_state: 'rascunho',
            version_n: 2,
            motivo: 'Falta fonte',
            grant: 'editorial:revisar',
          }),
          mkEvent(1),
        ]}
      />,
    );
    const items = screen.getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('enviou para revisão');
    expect(items[1]).toHaveTextContent('Mônica');
    expect(items[1]).toHaveTextContent('devolveu para rascunho');
    expect(items[1]).toHaveTextContent('v2');
    expect(items[1]).toHaveTextContent('Motivo: Falta fonte');
    expect(items[1]).toHaveTextContent('Revisão editorial →');
  });
});
