/**
 * RetryableError / QueryErrorState — the button shown after the automatic
 * attempts, wired end-to-end through the seed QueryClient (real paced retries,
 * fake timers).
 */
import { QueryClientProvider, useQuery } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const toastError = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a) } }));

import { ApiError } from '../api';
import { createQueryClient } from '../query-client';
import { QueryErrorState, RetryableError, toastRetryableError } from './RetryableError';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  toastError.mockClear();
});

describe('RetryableError', () => {
  it('shows title, reason class (not server text), auto-attempt count, and a focusable retry button', () => {
    const onRetry = vi.fn();
    render(
      <RetryableError
        error={new ApiError(502, 'Bad Gateway <html>nginx</html>')}
        attempts={4}
        onRetry={onRetry}
      />,
    );
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Não foi possível carregar.');
    expect(alert.textContent).toContain('O servidor está instável no momento.');
    expect(alert.textContent).toContain('Tentamos 4 vezes automaticamente.');
    expect(alert.textContent).not.toContain('nginx');
    const button = screen.getByRole('button', { name: /Tentar novamente/ });
    button.focus();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('omits the auto-attempt line for a non-transient failure', () => {
    render(<RetryableError error={new ApiError(404, 'x')} attempts={1} onRetry={() => {}} />);
    expect(screen.queryByText(/automaticamente/)).toBeNull();
    expect(screen.getByText('Não encontrado.')).toBeTruthy();
  });

  it('while retrying: spinner copy, disabled + aria-busy button', () => {
    render(<RetryableError error={new ApiError(503, 'x')} attempts={4} onRetry={() => {}} isRetrying />);
    const button = screen.getByRole('button', { name: /Tentando/ });
    expect(button.hasAttribute('disabled')).toBe(true);
    expect(button.getAttribute('aria-busy')).toBe('true');
    expect(screen.queryByText(/automaticamente/)).toBeNull();
  });

  it('inline variant renders custom title + extra actions', () => {
    render(
      <RetryableError
        variant="inline"
        title="Falhou o envio."
        error={new ApiError(null, 'x', undefined, null, 'network')}
        onRetry={() => {}}
        actions={<a href="/voltar">Voltar</a>}
        data-testid="meu-erro"
      />,
    );
    expect(screen.getByTestId('meu-erro').textContent).toContain('Falhou o envio.');
    expect(screen.getByText('Sem conexão com o servidor.')).toBeTruthy();
    expect(screen.getByText('Voltar')).toBeTruthy();
  });
});

describe('toastRetryableError', () => {
  it('toasts the reason class + attempts with a retry action', () => {
    const onRetry = vi.fn();
    toastRetryableError({ title: 'Não foi possível enviar.', error: new ApiError(503, 'raw'), attempts: 4, onRetry });
    const [title, opts] = toastError.mock.calls[0];
    expect(title).toBe('Não foi possível enviar.');
    expect(opts.description).toContain('Tentamos 4 vezes automaticamente.');
    expect(opts.description).not.toContain('raw');
    opts.action.onClick();
    expect(onRetry).toHaveBeenCalled();
  });
});

function Probe({ queryFn }: { queryFn: () => Promise<string> }) {
  const q = useQuery({ queryKey: ['probe'], queryFn });
  if (q.isPending && !q.data && !q.isError) return <p>carregando</p>;
  if (q.isError && !q.data) return <QueryErrorState query={q} />;
  return <p>dados: {q.data}</p>;
}

describe('QueryErrorState through the seed QueryClient', () => {
  it('auto-attempts paced, then shows the button; clicking it refetches and recovers', async () => {
    vi.useFakeTimers();
    const queryFn = vi.fn<() => Promise<string>>().mockRejectedValue(new ApiError(503, 'x'));
    const qc = createQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <Probe queryFn={queryFn} />
      </QueryClientProvider>,
    );

    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(queryFn).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).toBeNull(); // still auto-retrying

    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(queryFn).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(queryFn).toHaveBeenCalledTimes(3);
    await act(async () => { await vi.advanceTimersByTimeAsync(9000); });
    expect(queryFn).toHaveBeenCalledTimes(4);
    await act(async () => { await vi.advanceTimersByTimeAsync(50); }); // settle + notify

    expect(screen.getByRole('alert').textContent).toContain('Tentamos 4 vezes automaticamente.');
    expect(toastError).toHaveBeenCalledTimes(1); // once, after the last attempt

    queryFn.mockResolvedValueOnce('ok');
    fireEvent.click(screen.getByRole('button', { name: /Tentar novamente/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    vi.useRealTimers();
    await waitFor(() => expect(screen.getByText('dados: ok')).toBeTruthy());
    expect(queryFn).toHaveBeenCalledTimes(5);
  });

  it('never auto-retries a 404', async () => {
    const queryFn = vi.fn<() => Promise<string>>().mockRejectedValue(new ApiError(404, 'x'));
    render(
      <QueryClientProvider client={createQueryClient()}>
        <Probe queryFn={queryFn} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(queryFn).toHaveBeenCalledTimes(1);
  });

  it('renders nothing while the query still has data', () => {
    const { container } = render(
      <QueryErrorState
        query={{ isError: true, error: new ApiError(500, 'x'), isFetching: false, failureCount: 4, data: 'kept', refetch: () => {} }}
      />,
    );
    expect(container.innerHTML).toBe('');
  });
});
