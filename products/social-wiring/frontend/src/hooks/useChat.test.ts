/** YouTube upload chat hook: errors reach the user as readable text, never a raw body. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { PENDING_POLL_MS, useChat } from "./useChat";

const CLOUDFLARE_PAGE =
  '<!DOCTYPE html><html><head><title>noctusai.com | 502: Bad gateway</title></head><body>cf</body></html>';

function htmlResponse(status: number, body: string): Response {
  return new Response(body, { status, headers: { "Content-Type": "text/html" } });
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("useChat.sendMessage errors", () => {
  it("never renders an edge HTML page (2026-10-26 regression)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => htmlResponse(502, CLOUDFLARE_PAGE)));
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage("ONE10874 https://drive.google.com/drive/folders/x");
    });

    expect(result.current.error).toBe("Erro HTTP 502");
    expect(result.current.error).not.toContain("<");
  });

  it("shows the backend's own message from the seed error envelope", async () => {
    const message =
      "Créditos da API Openai esgotados. Recarregue a conta do provedor ou troque a chave em Configurações.";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(503, { error: { code: "LLM_QUOTA_EXHAUSTED", message } }),
      ),
    );
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage("ONE10874");
    });

    expect(result.current.error).toBe(message);
  });
});

describe("useChat.reset", () => {
  it("keeps the conversation on screen when the server refuses the reset", async () => {
    window.localStorage.setItem("ytcrawler:chat:session_id", "web:abc");
    const fetchMock = vi.fn(async (url: string) =>
      String(url).includes("/history/")
        ? jsonResponse(200, { session_id: "web:abc", messages: [{ role: "user", content: "oi" }] })
        : jsonResponse(503, { detail: "redis unavailable" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useChat());
    await act(async () => {});
    expect(result.current.messages).toHaveLength(1);

    await act(async () => {
      await result.current.reset();
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.error).toBe("redis unavailable");
  });
});

describe("useChat pending-upload follow-up", () => {
  it("polls the history while an upload is pending and stops when it ends", async () => {
    vi.useFakeTimers();
    try {
      window.localStorage.setItem("ytcrawler:chat:session_id", "web:abc");
      let historyCalls = 0;
      const fetchMock = vi.fn(async (url: string) => {
        if (String(url).includes("/history/")) {
          historyCalls += 1;
          // 1st load: upload in progress. 2nd: the video was published.
          return historyCalls === 1
            ? jsonResponse(200, {
                session_id: "web:abc",
                messages: [{ role: "assistant", content: "🚀 Upload iniciado!" }],
                pending: { found: true, state: "processing" },
              })
            : jsonResponse(200, {
                session_id: "web:abc",
                messages: [
                  { role: "assistant", content: "🚀 Upload iniciado!" },
                  { role: "assistant", content: "✅ Vídeo publicado!" },
                ],
                pending: null,
              });
        }
        return jsonResponse(404, {});
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useChat());
      await act(async () => {});
      expect(result.current.pending?.state).toBe("processing");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(PENDING_POLL_MS);
      });
      expect(result.current.messages.at(-1)?.content).toBe("✅ Vídeo publicado!");
      expect(result.current.pending).toBeNull();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(PENDING_POLL_MS * 3);
      });
      expect(historyCalls).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });
});
