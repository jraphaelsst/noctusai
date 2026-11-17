/** FluxoCard: state per roteiro status, preview per formato, links, retry, messages refresh at terminal. */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(() => rtl.cleanup());

const rot = vi.hoisted(() => ({ q: vi.fn() }));
vi.mock("@/hooks/geracao/useRoteiros", () => ({ useRoteiro: (id: string | null) => rot.q(id) }));

import { FluxoCard } from "./FluxoCard";

const fluxo = (over: Record<string, unknown> = {}) => ({
  proposta_id: "p1",
  etapa: "roteiro_gerando",
  headline: { id: "h1", texto: "Você erra isso" },
  roteiro: { id: "r1", nome: "Roteiro 1", status: "processando", formato: "carrossel", duracao: "auto", ordem_cta: "cta_inicio", versao: 1 },
  post: { id: "post1", titulo: "Você erra isso", etapa_label: "Headline + roteiro" },
  estruturas: [{ id: "e1", codigo: 7, perfil: { id: "pf", handle: "elias", nome: null }, formula_trecho: "f", papel: "principal", blocos: [{ id: "b1", nome: "Gancho" }, { id: "b2", nome: "Prova" }] }],
  legenda: "pendente",
  erro_codigo: null,
  ...over,
});

let qc: QueryClient;
function renderCard(f: any, extra: Partial<React.ComponentProps<typeof FluxoCard>> = {}) {
  return rtl.render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <FluxoCard fluxo={f} onTentarDeNovo={vi.fn()} tentando={false} {...extra} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
const roteiroQ = (data: any, over: Record<string, unknown> = {}) => ({ data, showSkeleton: false, isError: false, refetch: vi.fn(), ...over });

beforeEach(() => {
  qc = new QueryClient();
  rot.q.mockReturnValue(roteiroQ({ id: "r1", status: "processando", conteudo: null }));
});

describe("FluxoCard", () => {
  it("escrevendo: badge, formato, estruturas usadas e links", () => {
    renderCard(fluxo());
    expect(rtl.screen.getByTestId("fluxo-etapa").textContent).toMatch(/Escrevendo o roteiro/);
    expect(rtl.screen.getByText("Carrossel")).toBeTruthy();
    expect(rtl.screen.getByText(/Gancho · Prova/)).toBeTruthy();
    expect(rtl.screen.getByRole("link", { name: /Abrir roteiro/ }).getAttribute("href")).toBe("/media-creation/chat/headlines-e-roteiros");
    expect(rtl.screen.getByRole("link", { name: /Ver card/ }).getAttribute("href")).toBe("/media-creation/esteira?post=post1");
    expect(rtl.screen.queryByTestId("roteiro-preview")).toBeNull();
  });

  it("segue o status vivo do roteiro: completo mostra o preview por formato e avisa o chat uma vez", async () => {
    rot.q.mockReturnValue(roteiroQ({ id: "r1", status: "completo", conteudo: "**Slide 1**\nCapa\n**Slide 2**\nFim" }));
    const inv = vi.spyOn(qc, "invalidateQueries");
    renderCard(fluxo());
    expect(rtl.screen.getByTestId("fluxo-etapa").textContent).toMatch(/Roteiro pronto/);
    expect(rtl.screen.getByTestId("roteiro-preview").getAttribute("data-formato")).toBe("carrossel");
    expect(rtl.screen.getAllByRole("listitem").some((li) => /Capa/.test(li.textContent ?? ""))).toBe(true);
    expect(inv).toHaveBeenCalledWith({ queryKey: ["sw", "geracao", "chat", "mensagens"] });
  });

  it("reels pronto mostra o roteiro falado", () => {
    rot.q.mockReturnValue(roteiroQ({ id: "r1", status: "completo", conteudo: "Texto falado do reels" }));
    renderCard(fluxo({ etapa: "roteiro_pronto", roteiro: { ...fluxo().roteiro, formato: "reels", status: "completo" } }));
    expect(rtl.screen.getByText("Texto falado do reels")).toBeTruthy();
  });

  it("falhou: mensagem em pt-BR e 'Tentar de novo' chama o reenvio da proposta", async () => {
    const onTentarDeNovo = vi.fn();
    rot.q.mockReturnValue(roteiroQ(undefined));
    renderCard(fluxo({ etapa: "falhou", roteiro: null, erro_codigo: "orcamento_ia_excedido" }), { onTentarDeNovo });
    expect(rtl.screen.getByRole("alert").textContent).toMatch(/orçamento de IA/);
    await userEvent.click(rtl.screen.getByRole("button", { name: "Tentar de novo" }));
    expect(onTentarDeNovo).toHaveBeenCalledWith("p1");
  });

  it("preview com erro de carga oferece Tentar novamente (nunca some em silêncio)", async () => {
    const refetch = vi.fn();
    rot.q.mockReturnValue(roteiroQ(undefined, { isError: true, refetch }));
    renderCard(fluxo({ etapa: "roteiro_pronto" }));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Tentar novamente" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("sem roteiro ainda (headline salva): não consulta nenhum roteiro", () => {
    rot.q.mockReturnValue(roteiroQ(undefined));
    renderCard(fluxo({ etapa: "headline_salva", roteiro: null, post: null }));
    expect(rot.q).toHaveBeenCalledWith(null);
    expect(rtl.screen.getByTestId("fluxo-etapa").textContent).toMatch(/Headline salva/);
    expect(rtl.screen.queryByRole("link", { name: /Ver card/ })).toBeNull();
  });
});
