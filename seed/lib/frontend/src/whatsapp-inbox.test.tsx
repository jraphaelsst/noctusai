/**
 * createWhatsAppInboxHooks: pure cache ops, the read hooks' loading signals, the
 * send/read cache writes (optimistic -> server answer -> rollback), and the realtime
 * patching (transport mocked: `realtime.test.ts` owns the SSE wire).
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  createWhatsAppInboxHooks,
  flattenMessages,
  inboxCacheOps,
  olderCursor,
  type InboxChat,
  type InboxChatsData,
  type InboxMessage,
  type InboxMessagesData,
} from './whatsapp-inbox';
import type { ApiClient } from './api';

let captured: { onEvent?: (e: any) => void; url?: string | null; enabled?: boolean } = {};
vi.mock('./realtime', async (orig) => {
  const actual = await orig<typeof import('./realtime')>();
  return {
    ...actual,
    useRealtimeStream: (url: string | null, opts: any) => {
      captured = { onEvent: opts.onEvent, url, enabled: opts.enabled };
      return { status: 'open', lastEventId: null };
    },
  };
});

afterEach(() => {
  cleanup();
  captured = {};
});

const CONN = 'conn-1';
const chat = (id: string, over: Partial<InboxChat> = {}): InboxChat => ({
  chat_id: id, name: id, phone: null, is_group: false, last_message_preview: '',
  last_message_at: '2026-10-26T10:00:00+00:00', last_message_from_me: false, unread_count: 0, ...over,
});
const msg = (id: string, over: Partial<InboxMessage> = {}): InboxMessage => ({
  id, chat_id: 'a@c.us', from_me: false, body: id, type: 'chat', media_url: null, ack: null,
  timestamp: '2026-10-26T10:00:00+00:00', sender_name: null, ...over,
});
const chatsData = (...pages: InboxChat[][]): InboxChatsData => ({
  pages: pages.map((items, i) => ({ items, next_cursor: i < pages.length - 1 ? 'c' : null })),
  pageParams: pages.map(() => null),
});
const msgsData = (...pages: InboxMessage[][]): InboxMessagesData => ({
  pages: pages.map((items) => ({ items, has_more: false })),
  pageParams: pages.map(() => null),
});

describe('inboxCacheOps (pure)', () => {
  it('uncached in -> uncached out, for every op', () => {
    expect(inboxCacheOps.patchChat(undefined, 'a', {})).toBeUndefined();
    expect(inboxCacheOps.bumpChat(undefined, chat('a'))).toBeUndefined();
    expect(inboxCacheOps.bumpChatWith(undefined, 'a', {})).toBeUndefined();
    expect(inboxCacheOps.appendMessage(undefined, msg('m'))).toBeUndefined();
    expect(inboxCacheOps.patchMessage(undefined, 'm', {})).toBeUndefined();
    expect(inboxCacheOps.settleSent(undefined, 't', msg('m'))).toBeUndefined();
  });

  it('bumpChat moves an existing chat to the top and inserts an unknown one', () => {
    const old = chatsData([chat('a'), chat('b')], [chat('c')]);
    const moved = inboxCacheOps.bumpChat(old, chat('c', { unread_count: 2 }))!;
    expect(moved.pages[0].items.map((c) => c.chat_id)).toEqual(['c', 'a', 'b']);
    expect(moved.pages[1].items).toEqual([]);
    expect(moved.pages[0].items[0].unread_count).toBe(2);
    const inserted = inboxCacheOps.bumpChat(old, chat('z'))!;
    expect(inserted.pages[0].items.map((c) => c.chat_id)).toEqual(['z', 'a', 'b']);
  });

  it('patchChat edits in place and returns the SAME object when nothing matches', () => {
    const old = chatsData([chat('a'), chat('b')]);
    expect(inboxCacheOps.patchChat(old, 'b', { unread_count: 0 })!.pages[0].items[1].unread_count).toBe(0);
    expect(inboxCacheOps.patchChat(old, 'nope', { unread_count: 9 })).toBe(old);
  });

  it('appendMessage is idempotent by id and lands on the newest page', () => {
    const old = msgsData([msg('m2')], [msg('m1')]);
    const once = inboxCacheOps.appendMessage(old, msg('m3'))!;
    expect(once.pages[0].items.map((m) => m.id)).toEqual(['m2', 'm3']);
    expect(inboxCacheOps.appendMessage(once, msg('m3'))).toBe(once);
    expect(flattenMessages(once).map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
  });

  it('settleSent swaps the stand-in for the server message, never leaving two copies', () => {
    const withTemp = msgsData([msg('optimistic:1', { body: 'oi' })]);
    expect(inboxCacheOps.settleSent(withTemp, 'optimistic:1', msg('srv'))!.pages[0].items.map((m) => m.id)).toEqual(['srv']);
    const streamWonTheRace = msgsData([msg('srv'), msg('optimistic:1')]);
    expect(inboxCacheOps.settleSent(streamWonTheRace, 'optimistic:1', msg('srv'))!.pages[0].items.map((m) => m.id)).toEqual(['srv']);
  });

  it('olderCursor is "<iso>|<id>" of the oldest message, only while there is more', () => {
    expect(olderCursor({ items: [msg('m1')], has_more: true })).toBe('2026-10-26T10:00:00+00:00|m1');
    expect(olderCursor({ items: [msg('m1')], has_more: false })).toBeUndefined();
  });
});

/** A tiny stateful server: writes change what the next GET returns (as the real one would). */
function fakeServer() {
  const state = {
    chats: [chat('a@c.us', { unread_count: 1 })],
    messages: [msg('m1', { body: 'oi' })],
  };
  return {
    state,
    get: vi.fn(async (path: string) =>
      path.endsWith('/messages')
        ? { items: [...state.messages], has_more: false }
        : { items: [...state.chats], next_cursor: null }),
    post: vi.fn(async (path: string, body?: any) => {
      if (path.endsWith('/read')) {
        state.chats = state.chats.map((c) => ({ ...c, unread_count: 0 }));
        return null;
      }
      const saved = msg('srv-1', { from_me: true, body: body.text, chat_id: 'a@c.us', timestamp: '2026-10-26T11:00:00+00:00' });
      state.messages = [...state.messages, saved];
      state.chats = [{ ...state.chats[0], last_message_preview: body.text, last_message_at: saved.timestamp }];
      return saved;
    }),
  };
}

function setup(apiOver: Partial<Record<keyof ApiClient, any>> = {}, options = {}) {
  const server = fakeServer();
  const api = { get: server.get, post: server.post, ...apiOver } as unknown as ApiClient;
  const hooks = createWhatsAppInboxHooks(api, options);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { api, hooks, qc, wrapper, server };
}

describe('read hooks: loading signals', () => {
  it('chats: showSkeleton on first load only, isRefreshing afterwards - never a bare isLoading', async () => {
    const { hooks, wrapper, qc, server } = setup();
    const { result } = renderHook(() => hooks.useInboxChats(CONN), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.chats).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);
    let release!: () => void;
    server.get.mockImplementationOnce(() => new Promise((resolve) => {
      release = () => resolve({ items: [chat('a@c.us')], next_cursor: null });
    }));
    act(() => { void qc.invalidateQueries(); });
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.showSkeleton).toBe(false); // data stays on screen during the refetch
    expect(result.current.chats).toHaveLength(1);
    await act(async () => { release(); });
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
  });

  it('chats: sends q + limit, and is disabled without a connection', async () => {
    const { hooks, wrapper, api } = setup();
    renderHook(() => hooks.useInboxChats(CONN, { q: ' maria ', pageSize: 10 }), { wrapper });
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(api.get).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/chats', { limit: 10, q: 'maria' });
    const idle = setup();
    renderHook(() => idle.hooks.useInboxChats(null), { wrapper: idle.wrapper });
    expect(idle.api.get).not.toHaveBeenCalled();
  });

  it('messages: URL-encodes the JID and pages with the before cursor', async () => {
    const get = vi.fn()
      .mockResolvedValueOnce({ items: [msg('m2', { timestamp: '2026-10-26T10:05:00+00:00' })], has_more: true })
      .mockResolvedValueOnce({ items: [msg('m1')], has_more: false });
    const { hooks, wrapper } = setup({ get });
    const { result } = renderHook(() => hooks.useInboxMessages(CONN, 'a@c.us'), { wrapper });
    await waitFor(() => expect(result.current.messages).toHaveLength(1));
    expect(get.mock.calls[0][0]).toBe('/api/whatsapp/connections/conn-1/chats/a%40c.us/messages');
    expect(result.current.hasNextPage).toBe(true);
    await act(async () => { await result.current.fetchNextPage(); });
    expect(get.mock.calls[1][1]).toEqual({ limit: 50, before: '2026-10-26T10:05:00+00:00|m2' });
    await waitFor(() => expect(result.current.messages.map((m) => m.id)).toEqual(['m1', 'm2'])); // oldest first
  });
});

describe('writes go through the cache', () => {
  async function loaded() {
    const s = setup();
    const chats = renderHook(() => s.hooks.useInboxChats(CONN), { wrapper: s.wrapper });
    const thread = renderHook(() => s.hooks.useInboxMessages(CONN, 'a@c.us'), { wrapper: s.wrapper });
    await waitFor(() => expect(chats.result.current.chats).toHaveLength(1));
    await waitFor(() => expect(thread.result.current.messages).toHaveLength(1));
    return { ...s, chats, thread };
  }

  it('send: stand-in drawn at once, replaced by the server message, preview follows', async () => {
    const s = await loaded();
    const send = renderHook(() => s.hooks.useSendInboxMessage(CONN, 'a@c.us'), { wrapper: s.wrapper });
    const real = s.server.post.getMockImplementation()!;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    s.server.post.mockImplementationOnce(async (path: string, body?: any) => { await gate; return real(path, body); });
    let pending: Promise<unknown>;
    act(() => { pending = send.result.current.mutateAsync('Olá!'); });
    await waitFor(() => expect(s.thread.result.current.messages.map((m) => m.body)).toEqual(['oi', 'Olá!']));
    expect(s.thread.result.current.messages[1].id).toMatch(/^optimistic:/);
    expect(s.thread.result.current.showSkeleton).toBe(false);
    await waitFor(() => expect(s.chats.result.current.chats[0].last_message_preview).toBe('Olá!'));
    await act(async () => { release(); await pending; });
    await waitFor(() => expect(s.thread.result.current.messages.map((m) => m.id)).toEqual(['m1', 'srv-1']));
    await waitFor(() => expect(s.chats.result.current.chats[0].last_message_at).toBe('2026-10-26T11:00:00+00:00'));
    expect(s.api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/chats/a%40c.us/messages', { text: 'Olá!' });
  });

  it('send failure rolls the stand-in back and surfaces the server message', async () => {
    const post = vi.fn(async () => { throw new Error('WhatsApp session is not ready'); });
    const s = setup({ post });
    const thread = renderHook(() => s.hooks.useInboxMessages(CONN, 'a@c.us'), { wrapper: s.wrapper });
    await waitFor(() => expect(thread.result.current.messages).toHaveLength(1));
    const send = renderHook(() => s.hooks.useSendInboxMessage(CONN, 'a@c.us'), { wrapper: s.wrapper });
    await act(async () => {
      await expect(send.result.current.mutateAsync('x')).rejects.toThrow('WhatsApp session is not ready');
    });
    await waitFor(() => expect(thread.result.current.messages.map((m) => m.id)).toEqual(['m1']));
  });

  it('mark read clears the badge optimistically', async () => {
    const s = await loaded();
    const read = renderHook(() => s.hooks.useMarkChatRead(CONN), { wrapper: s.wrapper });
    await act(async () => { await read.result.current.mutateAsync('a@c.us'); });
    await waitFor(() => expect(s.chats.result.current.chats[0].unread_count).toBe(0));
    expect(s.api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/chats/a%40c.us/read');
  });
});

describe('useInboxEvents: realtime patches the caches', () => {
  async function live() {
    const s = setup({}, { getAuthToken: async () => 'tok', getBaseUrl: () => 'https://api.example.com' });
    const chats = renderHook(() => s.hooks.useInboxChats(CONN), { wrapper: s.wrapper });
    const thread = renderHook(() => s.hooks.useInboxMessages(CONN, 'a@c.us'), { wrapper: s.wrapper });
    renderHook(() => s.hooks.useInboxEvents(CONN), { wrapper: s.wrapper });
    await waitFor(() => expect(chats.result.current.chats).toHaveLength(1));
    await waitFor(() => expect(thread.result.current.messages).toHaveLength(1));
    return { ...s, chats, thread };
  }

  it('subscribes to the connection stream with the token provider', async () => {
    await live();
    expect(captured.url).toBe('https://api.example.com/api/whatsapp/connections/conn-1/events');
    expect(captured.enabled).toBe(true);
  });

  it('without a token provider there is no stream (the organ polls instead)', async () => {
    const s = setup();
    renderHook(() => s.hooks.useInboxEvents(CONN), { wrapper: s.wrapper });
    expect(captured.url).toBeNull();
    expect(captured.enabled).toBe(false);
  });

  it('message.new + chat.upsert append the message and bump the chat; replays are idempotent', async () => {
    const s = await live();
    const incoming = msg('m2', { body: 'chegou', timestamp: '2026-10-26T12:00:00+00:00' });
    const upsert = chat('a@c.us', { last_message_preview: 'chegou', unread_count: 2 });
    for (let i = 0; i < 2; i += 1) {
      act(() => {
        captured.onEvent!({ id: '1', event: 'message.new', payload: { chat_id: 'a@c.us', message: incoming } });
        captured.onEvent!({ id: '2', event: 'chat.upsert', payload: { chat: upsert } });
      });
    }
    await waitFor(() => expect(s.thread.result.current.messages.map((m) => m.id)).toEqual(['m1', 'm2']));
    await waitFor(() => expect(s.chats.result.current.chats[0]).toMatchObject({ last_message_preview: 'chegou', unread_count: 2 }));
    expect(s.chats.result.current.chats).toHaveLength(1);
  });

  it('message.ack and chat.read patch in place', async () => {
    const s = await live();
    act(() => {
      captured.onEvent!({ id: '1', event: 'message.ack', payload: { chat_id: 'a@c.us', id: 'm1', ack: 3 } });
      captured.onEvent!({ id: '2', event: 'chat.read', payload: { chat_id: 'a@c.us', unread_count: 0 } });
    });
    await waitFor(() => expect(s.thread.result.current.messages[0].ack).toBe(3));
    await waitFor(() => expect(s.chats.result.current.chats[0].unread_count).toBe(0));
  });

  it('a chat.upsert does not insert into a filtered (search) list', async () => {
    const s = setup({}, { getAuthToken: async () => 'tok' });
    const filtered = renderHook(() => s.hooks.useInboxChats(CONN, { q: 'maria' }), { wrapper: s.wrapper });
    renderHook(() => s.hooks.useInboxEvents(CONN), { wrapper: s.wrapper });
    await waitFor(() => expect(filtered.result.current.chats).toHaveLength(1));
    act(() => { captured.onEvent!({ id: '1', event: 'chat.upsert', payload: { chat: chat('z@c.us') } }); });
    await new Promise((r) => setTimeout(r, 20));
    expect(filtered.result.current.chats.map((c) => c.chat_id)).toEqual(['a@c.us']);
  });
});
