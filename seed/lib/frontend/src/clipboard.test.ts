/**
 * Tests for `copyRichText` — the ABNT formatting project's one shared
 * clipboard helper (`projects/abnt-formatting-CONTRACT.md` § 6).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const ORIGINAL_CLIPBOARD_ITEM = (globalThis as any).ClipboardItem;

function installRichClipboard() {
  const write = vi.fn().mockResolvedValue(undefined);
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { write, writeText },
  });

  class FakeClipboardItem {
    parts: Record<string, Blob>;
    constructor(parts: Record<string, Blob>) {
      this.parts = parts;
    }
  }
  (globalThis as any).ClipboardItem = FakeClipboardItem;

  return { write, writeText, FakeClipboardItem };
}

function installPlainOnlyClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  delete (globalThis as any).ClipboardItem;
  return { writeText };
}

afterEach(() => {
  vi.restoreAllMocks();
  if (ORIGINAL_CLIPBOARD_ITEM) {
    (globalThis as any).ClipboardItem = ORIGINAL_CLIPBOARD_ITEM;
  } else {
    delete (globalThis as any).ClipboardItem;
  }
});

describe("copyRichText", () => {
  it("writes both text/html and text/plain via ClipboardItem when available", async () => {
    const { write, writeText, FakeClipboardItem } = installRichClipboard();
    const { copyRichText } = await import("./clipboard");

    const result = await copyRichText("<p><b>bold</b></p>", "bold");

    expect(result).toEqual({ rich: true });
    expect(writeText).not.toHaveBeenCalled();
    expect(write).toHaveBeenCalledTimes(1);
    const [items] = write.mock.calls[0];
    expect(items).toHaveLength(1);
    expect(items[0]).toBeInstanceOf(FakeClipboardItem);
    const parts = (items[0] as InstanceType<typeof FakeClipboardItem>).parts;
    expect(parts["text/html"]).toBeInstanceOf(Blob);
    expect(parts["text/plain"]).toBeInstanceOf(Blob);
    expect(parts["text/html"].type).toBe("text/html");
    expect(parts["text/plain"].type).toBe("text/plain");
  });

  it("🔴 falls back to writeText — OBSERVABLY, via { rich: false } — when ClipboardItem is unavailable", async () => {
    const { writeText } = installPlainOnlyClipboard();
    const { copyRichText } = await import("./clipboard");

    const result = await copyRichText("<p><b>bold</b></p>", "bold");

    expect(result).toEqual({ rich: false });
    expect(writeText).toHaveBeenCalledWith("bold");
  });

  it("falls back to writeText when clipboard.write is missing even though ClipboardItem exists", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }, // no `write`
    });
    class FakeClipboardItem {}
    (globalThis as any).ClipboardItem = FakeClipboardItem;
    const { copyRichText } = await import("./clipboard");

    const result = await copyRichText("<p>x</p>", "x");

    expect(result).toEqual({ rich: false });
    expect(writeText).toHaveBeenCalledWith("x");
  });

  it("propagates a real write failure instead of masking it as a plain-text fallback", async () => {
    const { write } = installRichClipboard();
    write.mockRejectedValueOnce(new Error("permission denied"));
    const { copyRichText } = await import("./clipboard");

    await expect(copyRichText("<p>x</p>", "x")).rejects.toThrow("permission denied");
  });
});
