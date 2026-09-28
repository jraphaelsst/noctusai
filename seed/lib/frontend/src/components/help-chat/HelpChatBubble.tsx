/**
 * `<HelpChatBubble/>` — the reusable "AI specialist" chat organ.
 *
 * A floating, always-available round button (bottom-right, safe-area
 * aware) that opens a chat panel where the signed-in user talks to an AI
 * specialist scoped to the HOST product's own knowledge — see the backend
 * counterpart `noctusai_lib.domain.help_chat` for the knowledge-only
 * contract and the streaming/error shape this component consumes.
 *
 * Layout: a ~400×600 anchored panel on `sm:` and up; a full-screen sheet
 * below `sm` (640px) — same breakpoint `useSheetLayout` already
 * standardizes for the card-hub organ, reused here rather than a second
 * ad-hoc media query.
 *
 * Auth: takes `getBaseUrl` / `getAuthToken` directly — the exact same two
 * callbacks `createApiClient` takes (`Pick<CreateApiClientOptions, ...>`)
 * — because streaming needs a raw `fetch` + `ReadableStream`, which the
 * generic `ApiClient.post()` (JSON in, JSON out) cannot express. Reusing
 * the same auth-token seam a product already wires for `createApiClient`
 * means a consumer passes the SAME two callbacks it already has, not a
 * new auth mechanism.
 *
 * State: an in-memory conversation, mirrored to `sessionStorage` (capped,
 * try/catch — private-mode/quota failures degrade to "no history persisted"
 * rather than crashing the bubble) so a reload during the same tab session
 * doesn't lose the thread. Conversation content NEVER reaches any other
 * storage — see the backend module's "never persists" contract.
 */
import * as React from "react";
import { MessageCircle, Plus, Send, X } from "lucide-react";

import { cn } from "../../utils";
import { useSheetLayout } from "../card-hub/useSheetLayout";
import { MarkdownRenderer } from "../markdown";
import { extractErrorMessage } from "../../api";
import type { CreateApiClientOptions } from "../../api";

export interface HelpChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface HelpChatBubbleProps
  extends Pick<CreateApiClientOptions, "getBaseUrl" | "getAuthToken"> {
  /** Shown in the panel header, e.g. "Assistente IgIg". */
  title: string;
  /** POST endpoint, relative to `getBaseUrl()`. Matches the seed router's default. */
  endpoint?: string;
  /** Starter-question chips shown when the conversation is empty. */
  starters?: string[];
  /**
   * `sessionStorage` key for the persisted transcript. Defaults to
   * `"noctus-help-chat:" + title` — override when a product mounts more
   * than one bubble instance (unusual) to avoid the two sharing history.
   */
  storageKey?: string;
  /** Max messages kept in memory / sessionStorage / sent as history. */
  maxHistoryMessages?: number;
  className?: string;
}

const DEFAULT_ENDPOINT = "/api/ajuda/chat";
const DEFAULT_MAX_HISTORY = 20;

//: Error codes the backend router can return — see
//: `noctusai_lib.domain.help_chat.service` for the canonical list.
const ERROR_MESSAGES: Record<string, string> = {
  ia_nao_configurada: "O assistente de IA ainda não foi configurado para este produto.",
  orcamento_ia_excedido: "O limite de uso de IA da organização foi atingido. Tente novamente mais tarde.",
  limite_de_mensagens: "Você enviou mensagens rápido demais. Aguarde um instante e tente novamente.",
  ia_indisponivel: "O assistente não respondeu. Tente novamente em instantes.",
};

function friendlyError(code: string | undefined, fallback: string): string {
  if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code];
  return fallback;
}

function loadHistory(storageKey: string): HelpChatMessage[] {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (m): m is HelpChatMessage =>
        m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string",
    );
  } catch {
    return [];
  }
}

function saveHistory(storageKey: string, messages: HelpChatMessage[], cap: number): void {
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(messages.slice(-cap)));
  } catch {
    // Private mode / quota exceeded — degrade to "no history persisted",
    // never throw (this is a nice-to-have, not the feature's core contract).
  }
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-2" aria-label="Assistente digitando" role="status">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}

export function HelpChatBubble({
  title,
  getBaseUrl,
  getAuthToken,
  endpoint = DEFAULT_ENDPOINT,
  starters,
  storageKey,
  maxHistoryMessages = DEFAULT_MAX_HISTORY,
  className,
}: HelpChatBubbleProps) {
  const resolvedStorageKey = storageKey ?? `noctus-help-chat:${title}`;
  const isSheet = useSheetLayout();

  const [open, setOpen] = React.useState(false);
  const [messages, setMessages] = React.useState<HelpChatMessage[]>(() => loadHistory(resolvedStorageKey));
  const [input, setInput] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [configured, setConfigured] = React.useState(true);

  const messagesRef = React.useRef(messages);
  messagesRef.current = messages;

  const listRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const panelRef = React.useRef<HTMLDivElement>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  // Auto-scroll to the newest content as it streams in.
  React.useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streaming]);

  // Focus the composer on open; Esc closes (mirrors `Dialog`'s contract).
  React.useEffect(() => {
    if (!open) return;
    textareaRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const persist = React.useCallback(
    (next: HelpChatMessage[]) => saveHistory(resolvedStorageKey, next, maxHistoryMessages),
    [resolvedStorageKey, maxHistoryMessages],
  );

  const applyDelta = React.useCallback((delta: string) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      next[next.length - 1] = { ...last, content: last.content + delta };
      return next;
    });
  }, []);

  const send = React.useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;

      setError(null);
      const history = [...messagesRef.current, { role: "user" as const, content: trimmed }];
      const withPlaceholder: HelpChatMessage[] = [...history, { role: "assistant" as const, content: "" }];
      setMessages(withPlaceholder);
      setInput("");
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const token = await getAuthToken();
        const res = await fetch(`${getBaseUrl()}${endpoint}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            messages: history.slice(-maxHistoryMessages),
            pagina_atual: typeof window !== "undefined" ? window.location.pathname : null,
          }),
          signal: controller.signal,
        });

        if (!res.ok) {
          const data = await res.json().catch(() => null);
          const code = data?.code as string | undefined;
          setError(friendlyError(code, extractErrorMessage(data, res.status)));
          if (code === "ia_nao_configurada") setConfigured(false);
          setMessages((prev) => {
            const next = prev.slice(0, -1); // drop the empty assistant placeholder
            persist(next);
            return next;
          });
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          throw new Error("Streaming não é suportado neste navegador.");
        }
        const decoder = new TextDecoder();
        let buffer = "";
        let sawError: { code?: string; message: string } | null = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const line = frame.trim();
            if (!line.startsWith("data: ")) continue;
            let payload: any;
            try {
              payload = JSON.parse(line.slice("data: ".length));
            } catch {
              continue; // a malformed frame is dropped, not fatal to the stream
            }
            if (typeof payload?.delta === "string") {
              applyDelta(payload.delta);
            } else if (payload?.error) {
              sawError = payload.error;
            }
            // `payload.done` needs no handling — the loop's own end is the signal.
          }
        }

        if (sawError) {
          setError(friendlyError(sawError.code, sawError.message));
          if (sawError.code === "ia_nao_configurada") setConfigured(false);
        }
        persist(messagesRef.current);
      } catch (err: any) {
        if (err?.name === "AbortError") return;
        setError("Falha de conexão com o assistente. Verifique sua internet e tente novamente.");
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [streaming, getAuthToken, getBaseUrl, endpoint, maxHistoryMessages, applyDelta, persist],
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  };

  const handleNovaConversa = () => {
    abortRef.current?.abort();
    setMessages([]);
    setError(null);
    persist([]);
  };

  const retryLast = () => {
    const lastUser = [...messagesRef.current].reverse().find((m) => m.role === "user");
    if (lastUser) void send(lastUser.content);
  };

  const showStarters = messages.length === 0 && !!starters?.length;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? `Fechar ${title}` : `Abrir ${title}`}
        aria-expanded={open}
        className={cn(
          "fixed z-40 flex h-12 w-12 items-center justify-center rounded-full",
          "bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105",
          "bottom-[calc(1rem+env(safe-area-inset-bottom))] right-[calc(1rem+env(safe-area-inset-right))]",
          className,
        )}
      >
        {open ? <X className="h-5 w-5" /> : <MessageCircle className="h-5 w-5" />}
      </button>

      {open && (
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-label={title}
          data-layout={isSheet ? "sheet" : "panel"}
          className={cn(
            "fixed z-50 flex flex-col overflow-hidden border-border bg-card text-card-foreground shadow-2xl",
            isSheet
              ? "inset-0"
              : cn(
                  "bottom-[calc(5rem+env(safe-area-inset-bottom))] right-[calc(1rem+env(safe-area-inset-right))]",
                  "h-[min(600px,calc(100vh-6rem))] w-[400px] max-w-[calc(100vw-2rem)] rounded-lg border",
                ),
          )}
        >
          <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
            <h2 className="truncate text-sm font-semibold">{title}</h2>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleNovaConversa}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                aria-label="Nova conversa"
              >
                <Plus className="h-3.5 w-3.5" />
                Nova conversa
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Fechar"
                className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {messages.length === 0 && !showStarters && (
              <p className="text-sm text-muted-foreground">
                Olá! Envie uma pergunta sobre o {title.replace(/^Assistente\s+/i, "")} e eu ajudo.
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div
                  className={cn(
                    "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-foreground",
                  )}
                >
                  {m.role === "assistant" ? (
                    m.content ? (
                      <MarkdownRenderer content={m.content} className="[&_p]:mt-0 [&_p]:text-sm" />
                    ) : streaming && i === messages.length - 1 ? (
                      <TypingIndicator />
                    ) : null
                  ) : (
                    <span className="whitespace-pre-wrap">{m.content}</span>
                  )}
                </div>
              </div>
            ))}
            {showStarters && (
              <div className="flex flex-col gap-2">
                <p className="text-sm text-muted-foreground">
                  Olá! Envie uma pergunta ou escolha um exemplo:
                </p>
                {starters!.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void send(s)}
                    className="rounded-md border border-border bg-background px-3 py-2 text-left text-sm hover:bg-accent"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          {error && (
            <div className="mx-4 mb-2 flex items-center justify-between gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <span>{error}</span>
              <button type="button" onClick={retryLast} className="shrink-0 font-medium underline underline-offset-2">
                Tentar de novo
              </button>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex items-end gap-2 border-t border-border p-3">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!configured}
              placeholder={configured ? "Digite sua pergunta..." : "Assistente indisponível no momento"}
              rows={1}
              className="min-h-[40px] max-h-32 flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!configured || streaming || !input.trim()}
              aria-label="Enviar"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
