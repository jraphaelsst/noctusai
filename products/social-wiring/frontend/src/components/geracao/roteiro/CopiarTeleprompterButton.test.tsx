/** Versão Teleprompter button: copies the spoken words only, confirms in place for 3 s, then reverts. */
import * as rtl from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { COPIADO_MS, CopiarTeleprompterButton } from "./RoteiroEdicao";

const writeText = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  writeText.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => {
  rtl.cleanup();
  vi.useRealTimers();
});

describe("CopiarTeleprompterButton", () => {
  it("copies the teleprompter text and shows Copiado! for 3 seconds", async () => {
    rtl.render(<CopiarTeleprompterButton conteudo={"## Headline (capa)\nNinguém prepara uma mãe.\n\n## CTA\nSalva."} />);
    await rtl.act(async () => {
      rtl.fireEvent.click(rtl.screen.getByRole("button", { name: /Versão Teleprompter/ }));
    });
    expect(writeText).toHaveBeenCalledWith("Ninguém prepara uma mãe.\n\nSalva.");
    expect(rtl.screen.getByRole("button", { name: /Copiado!/ })).toBeTruthy();

    rtl.act(() => {
      vi.advanceTimersByTime(COPIADO_MS - 1);
    });
    expect(rtl.screen.queryByRole("button", { name: /Copiado!/ })).toBeTruthy();
    rtl.act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(rtl.screen.getByRole("button", { name: /Versão Teleprompter/ })).toBeTruthy();
  });

  it("keeps its label when the clipboard refuses", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    rtl.render(<CopiarTeleprompterButton conteudo="## H\nTexto." />);
    await rtl.act(async () => {
      rtl.fireEvent.click(rtl.screen.getByRole("button", { name: /Versão Teleprompter/ }));
    });
    expect(rtl.screen.queryByRole("button", { name: /Copiado!/ })).toBeNull();
  });
});
