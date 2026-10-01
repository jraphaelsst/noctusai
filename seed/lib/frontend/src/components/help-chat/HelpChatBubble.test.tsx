/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { HelpChatBubble } from './HelpChatBubble';

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

const BASE_URL = 'https://api.example.com';

function sseResponse(frames: string[], opts: { status?: number } = {}): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(`data: ${frame}\n\n`));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status: opts.status ?? 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function jsonErrorResponse(status: number, code: string, detail: string): Response {
  return new Response(JSON.stringify({ detail, code }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function setup(props: Partial<React.ComponentProps<typeof HelpChatBubble>> = {}) {
  const getAuthToken = vi.fn().mockResolvedValue('token-123');
  const getBaseUrl = vi.fn().mockReturnValue(BASE_URL);
  const view = render(
    <HelpChatBubble title="Assistente IgIg" getBaseUrl={getBaseUrl} getAuthToken={getAuthToken} {...props} />,
  );
  return { ...view, getAuthToken, getBaseUrl };
}

async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /abrir assistente igig/i }));
}

describe('HelpChatBubble — open/close', () => {
  it('renders a closed bubble by default and opens the panel on click', async () => {
    const user = userEvent.setup();
    setup();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await openPanel(user);
    expect(screen.getByRole('dialog', { name: 'Assistente IgIg' })).toBeInTheDocument();
  });

  it('closes on the close button', async () => {
    const user = userEvent.setup();
    setup();
    await openPanel(user);
    await user.click(screen.getByRole('button', { name: 'Fechar' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    const user = userEvent.setup();
    setup();
    await openPanel(user);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('HelpChatBubble — starters', () => {
  it('shows starter chips when the conversation is empty, and sending one streams a reply', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(sseResponse(['{"delta":"Ola"}', '{"delta":" mundo"}', '{"done":true}'])),
    );
    setup({ starters: ['Como crio um negócio?'] });
    await openPanel(user);

    expect(screen.getByText('Como crio um negócio?')).toBeInTheDocument();
    await user.click(screen.getByText('Como crio um negócio?'));

    await waitFor(() => expect(screen.getByText('Ola mundo')).toBeInTheDocument());
  });
});

describe('HelpChatBubble — send + stream', () => {
  it('sends the typed message on Enter and renders streamed deltas', async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(sseResponse(['{"delta":"Para criar"}', '{"delta":" um negócio..."}', '{"done":true}']));
    vi.stubGlobal('fetch', fetchMock);
    const { getAuthToken, getBaseUrl } = setup();
    await openPanel(user);

    const textarea = screen.getByPlaceholderText('Digite sua pergunta...');
    await user.type(textarea, 'Como crio um negócio?');
    await user.keyboard('{Enter}');

    expect(screen.getByText('Como crio um negócio?')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Para criar um negócio...')).toBeInTheDocument());

    expect(getAuthToken).toHaveBeenCalled();
    expect(getBaseUrl).toHaveBeenCalled();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/ajuda/chat`);
    expect(init.headers.Authorization).toBe('Bearer token-123');
    const body = JSON.parse(init.body);
    expect(body.messages).toEqual([{ role: 'user', content: 'Como crio um negócio?' }]);
  });

  it('sends pagina_atual as the current pathname', async () => {
    window.history.pushState({}, '', '/comercial/negocios');
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(['{"done":true}']));
    vi.stubGlobal('fetch', fetchMock);
    setup();
    await openPanel(user);
    await user.type(screen.getByPlaceholderText('Digite sua pergunta...'), 'oi');
    await user.keyboard('{Enter}');

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.pagina_atual).toBe('/comercial/negocios');
  });

  it('Shift+Enter inserts a newline instead of sending', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(['{"done":true}']));
    vi.stubGlobal('fetch', fetchMock);
    setup();
    await openPanel(user);
    const textarea = screen.getByPlaceholderText('Digite sua pergunta...') as HTMLTextAreaElement;
    await user.type(textarea, 'linha 1{Shift>}{Enter}{/Shift}linha 2');

    expect(fetchMock).not.toHaveBeenCalled();
    expect(textarea.value).toBe('linha 1\nlinha 2');
  });
});

describe('HelpChatBubble — errors', () => {
  it('shows a pt-BR error and a retry action on a pre-flight 503', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonErrorResponse(503, 'ia_nao_configurada', 'A IA não está configurada.')),
    );
    setup();
    await openPanel(user);
    await user.type(screen.getByPlaceholderText('Digite sua pergunta...'), 'oi');
    await user.keyboard('{Enter}');

    await waitFor(() =>
      expect(screen.getByText(/assistente de ia ainda não foi configurado/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: 'Tentar de novo' })).toBeInTheDocument();
    // ia_nao_configurada disables the composer until the product fixes config.
    expect(screen.getByPlaceholderText('Assistente indisponível no momento')).toBeDisabled();
  });

  it('shows a pt-BR error on a mid-stream error event, without disabling the composer', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          sseResponse(['{"delta":"Comec"}', '{"error":{"code":"ia_indisponivel","message":"falhou"}}']),
        ),
    );
    setup();
    await openPanel(user);
    await user.type(screen.getByPlaceholderText('Digite sua pergunta...'), 'oi');
    await user.keyboard('{Enter}');

    await waitFor(() => expect(screen.getByText(/não respondeu/i)).toBeInTheDocument());
    expect(screen.getByPlaceholderText('Digite sua pergunta...')).not.toBeDisabled();
  });

  it('retries the last user message', async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonErrorResponse(502, 'ia_indisponivel', 'falhou'))
      .mockResolvedValueOnce(sseResponse(['{"delta":"ok agora"}', '{"done":true}']));
    vi.stubGlobal('fetch', fetchMock);
    setup();
    await openPanel(user);
    await user.type(screen.getByPlaceholderText('Digite sua pergunta...'), 'oi');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Tentar de novo' })).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'Tentar de novo' }));
    await waitFor(() => expect(screen.getByText('ok agora')).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe('HelpChatBubble — long answers', () => {
  it('tells the user a cut-off answer was interrupted and continues it on click', async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse(['{"delta":"Passo 1"}', '{"truncated":true}', '{"done":true}']))
      .mockResolvedValueOnce(sseResponse(['{"delta":"Passo 2"}', '{"done":true}']));
    vi.stubGlobal('fetch', fetchMock);
    setup();
    await openPanel(user);
    await user.type(screen.getByPlaceholderText('Digite sua pergunta...'), 'como faço?');
    await user.keyboard('{Enter}');

    await waitFor(() => expect(screen.getByText(/foi interrompida/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Continuar resposta' }));

    await waitFor(() => expect(screen.getByText('Passo 2')).toBeInTheDocument());
    const sent = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(sent.messages.at(-1)).toEqual({ role: 'user', content: 'Continue a resposta de onde parou.' });
    expect(sent.messages.at(-2)).toEqual({ role: 'assistant', content: 'Passo 1' });
    expect(screen.queryByText(/foi interrompida/i)).not.toBeInTheDocument();
  });

  it('shows no interruption notice for a complete answer', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(['{"delta":"Tudo"}', '{"done":true}'])));
    setup();
    await openPanel(user);
    await user.type(screen.getByPlaceholderText('Digite sua pergunta...'), 'oi');
    await user.keyboard('{Enter}');

    await waitFor(() => expect(screen.getByText('Tudo')).toBeInTheDocument());
    expect(screen.queryByText(/foi interrompida/i)).not.toBeInTheDocument();
  });
});

describe('HelpChatBubble — sessionStorage', () => {
  it('persists the transcript and reloads it on remount', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(['{"delta":"resposta"}', '{"done":true}'])));
    const { unmount } = setup();
    await openPanel(user);
    await user.type(screen.getByPlaceholderText('Digite sua pergunta...'), 'pergunta persistida');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(screen.getByText('resposta')).toBeInTheDocument());
    unmount();

    const user2 = userEvent.setup();
    setup();
    await openPanel(user2);
    expect(screen.getByText('pergunta persistida')).toBeInTheDocument();
    expect(screen.getByText('resposta')).toBeInTheDocument();
  });

  it('"Nova conversa" clears the transcript and sessionStorage', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(['{"delta":"resposta"}', '{"done":true}'])));
    setup();
    await openPanel(user);
    await user.type(screen.getByPlaceholderText('Digite sua pergunta...'), 'oi');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(screen.getByText('resposta')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'Nova conversa' }));
    expect(screen.queryByText('oi')).not.toBeInTheDocument();
    expect(screen.queryByText('resposta')).not.toBeInTheDocument();
  });

  it('degrades gracefully when sessionStorage throws (private mode)', async () => {
    const spy = vi.spyOn(window.sessionStorage, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked');
    });
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(['{"delta":"resposta"}', '{"done":true}'])));
    setup();
    await openPanel(user);
    await expect(
      (async () => {
        await user.type(screen.getByPlaceholderText('Digite sua pergunta...'), 'oi');
        await user.keyboard('{Enter}');
        await waitFor(() => expect(screen.getByText('resposta')).toBeInTheDocument());
      })(),
    ).resolves.not.toThrow();
    spy.mockRestore();
  });
});
