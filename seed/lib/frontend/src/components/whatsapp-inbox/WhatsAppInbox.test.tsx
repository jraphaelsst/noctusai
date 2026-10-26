/**
 * <WhatsAppInbox/>: chat list (search, unread badge) + thread + reply on the seed ChatWindow.
 *
 * Coverage: skeleton on first load only · empty · error · list+badge · open a chat (messages, mark read) ·
 * send (optimistic, then the server's message) · debounced server-side search · deep link
 * (in the list AND outside the loaded pages) · header slot · load-more · polling fallback.
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { createWhatsAppInboxHooks, type InboxChat, type InboxMessage } from '../../whatsapp-inbox';
import { WhatsAppInbox, toChatMessage, toThread } from './WhatsAppInbox';
import type { ApiClient } from '../../api';

let streamStatus: 'open' | 'closed' = 'open';
vi.mock('../../realtime', async (orig) => {
  const actual = await orig<typeof import('../../realtime')>();
  return { ...actual, useRealtimeStream: () => ({ status: streamStatus, lastEventId: null }) };
});

beforeEach(() => { streamStatus = 'open'; });
afterEach(cleanup);

const chat = (id: string, over: Partial<InboxChat> = {}): InboxChat => ({
  chat_id: id, name: `Contato ${id}`, phone: null, is_group: false, last_message_preview: `prévia ${id}`,
  last_message_at: '2026-10-26T10:00:00+00:00', last_message_from_me: false, unread_count: 0, ...over,
});
const msg = (id: string, over: Partial<InboxMessage> = {}): InboxMessage => ({
  id, chat_id: 'a@c.us', from_me: false, body: `texto ${id}`, type: 'chat', media_url: null, ack: null,
  timestamp: '2026-10-26T10:00:00+00:00', sender_name: null, ...over,
});

function makeApi(opts: { chats?: InboxChat[]; byQuery?: Record<string, InboxChat[]>; messages?: InboxMessage[]; hasNext?: boolean } = {}) {
  // Stateful like the real server: a write changes what the settle refetch returns.
  let chats = opts.chats ?? [chat('a@c.us', { unread_count: 3 }), chat('b@c.us')];
  let messages = opts.messages ?? [msg('m1')];
  return {
    get: vi.fn(async (path: string, params?: Record<string, any>) => {
      if (path.endsWith('/messages')) return { items: [...messages], has_more: false };
      if (params?.q && opts.byQuery?.[params.q]) return { items: opts.byQuery[params.q], next_cursor: null };
      if (params?.cursor) return { items: [chat('z@c.us')], next_cursor: null };
      return { items: [...chats], next_cursor: opts.hasNext ? 'next' : null };
    }),
    post: vi.fn(async (path: string, body?: any) => {
      if (path.endsWith('/read')) {
        chats = chats.map((c) => ({ ...c, unread_count: 0 }));
        return null;
      }
      const saved = msg('srv-1', { from_me: true, body: body.text });
      messages = [...messages, saved];
      return saved;
    }),
  } as unknown as ApiClient & { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> };
}

function renderInbox(api: ApiClient, props: Partial<React.ComponentProps<typeof WhatsAppInbox>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const hooks = createWhatsAppInboxHooks(api, { getAuthToken: async () => 'tok' });
  return render(
    <QueryClientProvider client={qc}>
      <div style={{ display: 'flex', height: 600 }}>
        <WhatsAppInbox hooks={hooks} connectionId="conn-1" {...props} />
      </div>
    </QueryClientProvider>,
  );
}

describe('adapters', () => {
  it('maps chats and messages to the ChatWindow shapes', () => {
    expect(toThread(chat('a@c.us', { last_message_from_me: true, unread_count: 2 }))).toMatchObject({
      id: 'a@c.us', title: 'Contato a@c.us', lastDirection: 'outbound', unreadCount: 2,
    });
    expect(toChatMessage(msg('m', { from_me: true })).direction).toBe('outbound');
    expect(toChatMessage(msg('m', { body: '', type: 'image', media_url: 'http://x' })).body).toBe('[image]');
    expect(toChatMessage(msg('m', { body: '', type: 'chat', media_url: 'http://x' })).body).toBe('[mídia]');
  });
});

describe('WhatsAppInbox: list states', () => {
  it('skeleton while the first page loads', () => {
    const api = { get: vi.fn((): Promise<any> => new Promise(() => {})), post: vi.fn() } as unknown as ApiClient;
    renderInbox(api);
    expect(screen.getByTestId('chat-thread-list-skeleton')).toBeInTheDocument();
  });

  it('empty and error states', async () => {
    renderInbox(makeApi({ chats: [] }));
    expect(await screen.findByText('Nenhuma conversa ainda.')).toBeInTheDocument();
    cleanup();
    const failing = { get: vi.fn(async () => { throw new Error('boom'); }), post: vi.fn() } as unknown as ApiClient;
    renderInbox(failing);
    expect(await screen.findByText('Erro ao carregar conversas.')).toBeInTheDocument();
  });

  it('lists chats with their unread badge and preview', async () => {
    renderInbox(makeApi());
    expect(await screen.findByText('Contato a@c.us')).toBeInTheDocument();
    expect(screen.getByText('prévia b@c.us')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });
});

describe('WhatsAppInbox: conversation', () => {
  it('opens a chat: loads its messages and marks it read once', async () => {
    const api = makeApi();
    renderInbox(api);
    fireEvent.click(await screen.findByText('Contato a@c.us'));
    expect(await screen.findByText('texto m1')).toBeInTheDocument();
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/chats/a%40c.us/read'));
    expect((api.post as any).mock.calls.filter(([p]: [string]) => p.endsWith('/read'))).toHaveLength(1);
    await waitFor(() => expect(screen.queryByText('3')).not.toBeInTheDocument()); // badge cleared at once
  });

  it('sends a reply: the composer posts the text and the server message lands in the thread', async () => {
    const api = makeApi();
    renderInbox(api);
    fireEvent.click(await screen.findByText('Contato a@c.us'));
    await screen.findByText('texto m1');
    const composer = screen.getByPlaceholderText(/mensagem/i);
    fireEvent.change(composer, { target: { value: 'Bom dia!' } });
    fireEvent.keyDown(composer, { key: 'Enter' });
    expect(await screen.findByText('Bom dia!')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/chats/a%40c.us/messages', { text: 'Bom dia!' });
  });

  it('a failed send shows the server message inline and does not keep the stand-in', async () => {
    const api = makeApi();
    (api.post as any).mockImplementation(async (path: string) => {
      if (path.endsWith('/read')) return null;
      throw new Error('A sessão do WhatsApp não está pronta');
    });
    renderInbox(api);
    fireEvent.click(await screen.findByText('Contato a@c.us'));
    await screen.findByText('texto m1');
    const composer = screen.getByPlaceholderText(/mensagem/i);
    fireEvent.change(composer, { target: { value: 'x1' } });
    fireEvent.keyDown(composer, { key: 'Enter' });
    expect(await screen.findByText(/A sessão do WhatsApp não está pronta/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('x1')).not.toBeInTheDocument());
  });

  it('renders the header slot with the open chat', async () => {
    renderInbox(makeApi(), { renderChatHeaderExtra: (c) => <a href={`/leads?chat=${c.chat_id}`}>ver lead</a> });
    fireEvent.click(await screen.findByText('Contato b@c.us'));
    const link = await screen.findByText('ver lead');
    expect(link).toHaveAttribute('href', '/leads?chat=b@c.us');
  });
});

describe('WhatsAppInbox: search', () => {
  it('searches on the server, debounced, with the typed text', async () => {
    const api = makeApi({ byQuery: { maria: [chat('m@c.us', { name: 'Maria' })] } });
    renderInbox(api);
    await screen.findByText('Contato a@c.us');
    fireEvent.change(screen.getByTestId('inbox-search'), { target: { value: 'ma' } });
    fireEvent.change(screen.getByTestId('inbox-search'), { target: { value: 'maria' } });
    expect(await screen.findByText('Maria')).toBeInTheDocument();
    const qs = (api.get as any).mock.calls.map(([, p]: [string, any]) => p?.q).filter(Boolean);
    expect(qs).toEqual(['maria']); // the intermediate keystroke never became a request
    expect(screen.queryByText('Contato a@c.us')).not.toBeInTheDocument();
  });

  it('says so when nothing matches', async () => {
    renderInbox(makeApi({ byQuery: { zzz: [] } }));
    await screen.findByText('Contato a@c.us');
    fireEvent.change(screen.getByTestId('inbox-search'), { target: { value: 'zzz' } });
    expect(await screen.findByText('Nenhuma conversa encontrada.')).toBeInTheDocument();
  });
});

describe('WhatsAppInbox: deep link', () => {
  it('initialChatId opens that conversation', async () => {
    renderInbox(makeApi(), { initialChatId: 'b@c.us' });
    expect(await screen.findByTestId('chat-thread-panel')).toBeInTheDocument();
    expect(within(screen.getByTestId('chat-thread-panel')).getByText('Contato b@c.us')).toBeInTheDocument();
  });

  it('a chat outside the loaded pages is looked up by id and still opens', async () => {
    const far = chat('far@c.us', { name: 'Longe' });
    const api = makeApi({ byQuery: { 'far@c.us': [far] } });
    renderInbox(api, { initialChatId: 'far@c.us' });
    const panel = await screen.findByTestId('chat-thread-panel');
    expect(within(panel).getByText('Longe')).toBeInTheDocument();
    expect((api.get as any).mock.calls.some(([, p]: [string, any]) => p?.q === 'far@c.us')).toBe(true);
  });

  it('reports selection changes', async () => {
    const onSelectChat = vi.fn();
    renderInbox(makeApi(), { onSelectChat });
    fireEvent.click(await screen.findByText('Contato a@c.us'));
    expect(onSelectChat).toHaveBeenCalledWith('a@c.us');
  });
});

describe('WhatsAppInbox: paging and polling', () => {
  it('"Carregar mais conversas" fetches the next page with the cursor', async () => {
    const api = makeApi({ hasNext: true });
    renderInbox(api);
    fireEvent.click(await screen.findByTestId('inbox-load-more-chats'));
    expect(await screen.findByText('Contato z@c.us')).toBeInTheDocument();
    expect((api.get as any).mock.calls.some(([, p]: [string, any]) => p?.cursor === 'next')).toBe(true);
  });

  it('polls only while the realtime stream is not open', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      streamStatus = 'closed';
      const api = makeApi();
      renderInbox(api, { fallbackPollMs: 1000 });
      await screen.findByText('Contato a@c.us');
      const before = (api.get as any).mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
      expect((api.get as any).mock.calls.length).toBeGreaterThan(before);
      cleanup();
      streamStatus = 'open';
      const quiet = makeApi();
      renderInbox(quiet, { fallbackPollMs: 1000 });
      await screen.findByText('Contato a@c.us');
      const quietBefore = (quiet.get as any).mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
      expect((quiet.get as any).mock.calls.length).toBe(quietBefore);
    } finally {
      vi.useRealTimers();
    }
  });
});
