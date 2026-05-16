/**
 * Chat hooks — wrap the /api/chat/* endpoints.
 *
 * The chat surface drives the OpenAI tool-calling chatbot from the
 * platform UI. Same backend service as the WhatsApp inbound flow; the
 * difference is the session_id shape (`web:<uuid>` here vs the phone
 * JID on WhatsApp).
 *
 * No auth header for now — the chat endpoint is intentionally open per
 * the current product brief. When auth lands, the backend will derive
 * org_id from the JWT and this hook will gain the supabase token like
 * useUpload does.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { apiUrl } from "@/lib/apiBase";

export interface ChatHistoryItem {
  role: "user" | "assistant";
  content: string;
}

export interface ChatPending {
  found: boolean;
  state?: string;
  product_code?: string;
  drive_url?: string | null;
  file_id?: string | null;
  video_filename?: string | null;
  video_size_bytes?: number | null;
  title?: string | null;
  privacy_status?: string;
}

export interface ChatReply {
  session_id: string;
  reply: string;
  file_id?: string | null;
  pending?: ChatPending | null;
}

const SESSION_STORAGE_KEY = "ytcrawler:chat:session_id";

function loadSessionId(): string {
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function persistSessionId(value: string): void {
  try {
    window.localStorage.setItem(SESSION_STORAGE_KEY, value);
  } catch {
    /* ignore */
  }
}

export function useChat() {
  const [sessionId, setSessionId] = useState<string>(loadSessionId);
  const [messages, setMessages] = useState<ChatHistoryItem[]>([]);
  const [pending, setPending] = useState<ChatPending | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initialFetch = useRef(false);

  const fetchHistory = useCallback(async (sid: string) => {
    if (!sid) return;
    try {
      const res = await fetch(
        apiUrl(`/api/chat/history/${encodeURIComponent(sid)}`)
      );
      if (!res.ok) return;
      const data = await res.json();
      setMessages(Array.isArray(data.messages) ? data.messages : []);
    } catch {
      /* leave messages as-is on transient failures */
    }
  }, []);

  useEffect(() => {
    if (initialFetch.current) return;
    initialFetch.current = true;
    if (sessionId) {
      fetchHistory(sessionId);
    }
  }, [sessionId, fetchHistory]);

  const sendMessage = useCallback(
    async (text: string, file?: File | null): Promise<ChatReply | null> => {
      if (!text.trim() && !file) return null;
      setSending(true);
      setError(null);

      const optimisticUser: ChatHistoryItem = {
        role: "user",
        content: file ? `${text || "[arquivo]"} \u{1F4CE} ${file.name}` : text,
      };
      setMessages((prev) => [...prev, optimisticUser]);

      try {
        const form = new FormData();
        form.append("text", text || "");
        form.append("session_id", sessionId || "");
        if (file) {
          form.append("file", file);
        }
        const res = await fetch(apiUrl("/api/chat/message"), {
          method: "POST",
          body: form,
        });
        if (!res.ok) {
          const body = await res.text();
          throw new Error(body || `chat HTTP ${res.status}`);
        }
        const data: ChatReply = await res.json();
        if (data.session_id && data.session_id !== sessionId) {
          setSessionId(data.session_id);
          persistSessionId(data.session_id);
        }
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.reply || "" },
        ]);
        setPending(data.pending ?? null);
        return data;
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : String(exc));
        return null;
      } finally {
        setSending(false);
      }
    },
    [sessionId]
  );

  const reset = useCallback(async () => {
    if (!sessionId) {
      setMessages([]);
      setPending(null);
      return;
    }
    await fetch(
      apiUrl(`/api/chat/reset/${encodeURIComponent(sessionId)}`),
      { method: "POST" }
    );
    setMessages([]);
    setPending(null);
  }, [sessionId]);

  return {
    sessionId,
    messages,
    pending,
    sending,
    error,
    sendMessage,
    reset,
  };
}
