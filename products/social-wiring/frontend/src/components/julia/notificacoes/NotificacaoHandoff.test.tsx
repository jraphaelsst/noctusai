/** The hand-off notification (julia-v2 0.4): profile + atendimento summary + MASKED identity; never a raw CPF/RG. */
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";

import { NotificacaoCard } from "./NotificacaoCard";

const MENSAGEM = [
  "Julia passou a conversa com Ana &amp; Cia para atendimento humano. Motivo: visita pedida",
  "Resumo do atendimento: Quer apartamento de 3 quartos no Centro; pediu visita no sábado.",
  "Perfil: operacao: compra; bairro: Centro; orcamento: 450000",
  "Identificação (mascarada): nome: Ana Souza; cpf: ***.***.***-09; rg: ******78; email: a***@x.com",
  "Em aberto: financiamento",
  "Combinado com o lead: retorno amanhã",
].join("\n");

const N = (mensagem: string, extra: object = {}) => ({
  id: "n1", tipo: "handoff", titulo: "Atendimento humano solicitado", mensagem,
  is_read: false, link: "/julia/conversas?chat=5511%40c.us", created_at: "2026-10-20T10:00:00Z", ...extra,
});
afterEach(cleanup);

function abrir() {
  const onLer = vi.fn();
  render(<ul><NotificacaoCard notificacao={N(MENSAGEM)} onLer={onLer} /></ul>);
  fireEvent.click(screen.getByLabelText("Expandir"));
  return onLer;
}

describe("handoff notification", () => {
  it("renders profile, summary and masked identity as labelled blocks", () => {
    const onLer = abrir();
    expect(onLer).toHaveBeenCalledWith("n1");
    expect(screen.getByTestId("handoff-resumo").textContent).toContain("3 quartos");
    expect(screen.getByTestId("handoff-perfil").textContent).toContain("bairro: Centro");
    const id = screen.getByTestId("handoff-identificacao").textContent!;
    expect(id).toContain("***.***.***-09");
    expect(id).toContain("rg: ******78");
    expect(screen.getByTestId("handoff-aberto").textContent).toContain("financiamento");
    expect(screen.getByTestId("handoff-combinado")).toBeTruthy();
    expect(screen.getByText("Abrir").getAttribute("href")).toBe("/julia/conversas?chat=5511%40c.us");
  });

  it("decodes the server's html entities for display", () => {
    abrir();
    expect(screen.getByTestId("handoff-detalhe").textContent).toContain("Ana & Cia");
  });

  it("NEVER renders a raw CPF/RG, even if an upstream build sends one", () => {
    render(
      <ul>
        <NotificacaoCard
          onLer={() => {}}
          notificacao={N("Julia passou a conversa.\nIdentificação (mascarada): cpf: 123.456.789-09; rg: 12.345.678-9")}
        />
      </ul>,
    );
    fireEvent.click(screen.getByLabelText("Expandir"));
    const t = document.body.textContent!;
    expect(t).not.toMatch(/123\.456\.789|12\.345\.678/);
    expect(t).toMatch(/cpf: \*+09/);
  });

  it("a non-handoff card still masks identity in free text", () => {
    render(<ul><NotificacaoCard onLer={() => {}} notificacao={N("Lead com CPF 12345678909", { tipo: "novo_lead", titulo: "Novo lead" })} /></ul>);
    fireEvent.click(screen.getByLabelText("Expandir"));
    expect(document.body.textContent).not.toContain("12345678909");
  });
});
