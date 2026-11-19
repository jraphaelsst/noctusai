/** PropostaCard: headline vs roteiro card (contract §16.7): label per tipo, collapsed script, same disabled mechanics. */
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PropostaCard } from "./PropostaCard";

afterEach(() => rtl.cleanup());

const base = {
  id: "p1", ordem: 1, texto: "Você erra isso", gatilho_tag: "curiosidade",
  estruturas: [{ id: "e1", codigo: 7, perfil: { id: "pf", handle: "elias", nome: null }, principal: true }],
  status: "proposta", headline_id: null,
} as const;
const roteiro = { ...base, tipo: "roteiro", titulo: "O erro do preço", formato: "reels", texto: "Linha 1\nLinha 2\nLinha 3", roteiro_id: null } as const;

function renderCard(p: any, extra: Record<string, unknown> = {}) {
  const onEscolher = vi.fn();
  rtl.render(
    <MemoryRouter>
      <ul>
        <PropostaCard proposta={p} escolhendo={false} bloqueada={false} onEscolher={onEscolher} {...extra} />
      </ul>
    </MemoryRouter>,
  );
  return onEscolher;
}

describe("PropostaCard", () => {
  it("headline (sem tipo ou tipo headline) mantém o rótulo atual e o texto", () => {
    const on = renderCard(base);
    expect(rtl.screen.getByText("Você erra isso")).toBeTruthy();
    expect(rtl.screen.queryByText("Ver roteiro completo")).toBeNull();
    return userEvent.click(rtl.screen.getByRole("button", { name: "Criar roteiro" })).then(() => expect(on).toHaveBeenCalledWith("p1"));
  });

  it("roteiro: título, formato, chips, script recolhido e botão 'Usar este roteiro'", async () => {
    const on = renderCard(roteiro);
    expect(rtl.screen.getByText("O erro do preço")).toBeTruthy();
    expect(rtl.screen.getByText("Reels")).toBeTruthy();
    expect(rtl.screen.getByRole("link", { name: /estrutura #7 de @elias/ })).toBeTruthy();
    expect(rtl.screen.getByTestId("roteiro-script").className).toMatch(/line-clamp-6/);
    await userEvent.click(rtl.screen.getByRole("button", { name: "Usar este roteiro" }));
    expect(on).toHaveBeenCalledWith("p1");
  });

  it("expande e recolhe o script", async () => {
    renderCard(roteiro);
    const ver = rtl.screen.getByRole("button", { name: "Ver roteiro completo" });
    expect(ver.getAttribute("aria-expanded")).toBe("false");
    await userEvent.click(ver);
    expect(rtl.screen.getByTestId("roteiro-script").className).not.toMatch(/line-clamp/);
    expect(rtl.screen.getByRole("button", { name: "Recolher" }).getAttribute("aria-expanded")).toBe("true");
    await userEvent.click(rtl.screen.getByRole("button", { name: "Recolher" }));
    expect(rtl.screen.getByTestId("roteiro-script").className).toMatch(/line-clamp-6/);
  });

  it("pendente, escolhida e bloqueada desabilitam o botão", () => {
    renderCard(roteiro, { escolhendo: true });
    expect((rtl.screen.getByRole("button", { name: /Salvando roteiro/ }) as HTMLButtonElement).disabled).toBe(true);
    rtl.cleanup();
    renderCard({ ...roteiro, status: "escolhida" });
    expect((rtl.screen.getByRole("button", { name: /Roteiro escolhido/ }) as HTMLButtonElement).disabled).toBe(true);
    rtl.cleanup();
    renderCard(roteiro, { bloqueada: true });
    expect((rtl.screen.getByRole("button", { name: "Usar este roteiro" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
