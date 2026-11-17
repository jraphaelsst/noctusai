/**
 * Julia › Agente card "Aviso de privacidade": read-only for org admins, editable for NoctusAI platform admins
 * (owner 2026-11-17). `@/lib/api` is the seam. Fictitious data only.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useMeAccess: () => ({ data: undefined }) }));

import { AvisoPrivacidadeCard, NOTA_AVISO_NOCTUS } from "./AvisoPrivacidadeCard";
import { textoParaBlocos } from "@/lib/juliaAviso";

const AVISO = {
  slug: "exemplo",
  titulo: "Aviso Exemplo",
  empresa_nome: "Imobiliária Exemplo",
  contato_email: "contato@exemplo.test",
  contato_whatsapp: "+5511900000000",
  mensagem_inicial: "Olá! Nosso aviso: {link}",
  secoes: [{ n: "1", title: "Dados", blocks: [{ p: "Coletamos nome." }, { ul: ["a", "b"] }] }],
  versao: 3,
  atualizado_em: null,
  incompleto: false,
};

function renderCard(isPlatformAdmin: boolean) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AvisoPrivacidadeCard isPlatformAdmin={isPlatformAdmin} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockResolvedValue({ data: AVISO });
});
afterEach(cleanup);

describe("AvisoPrivacidadeCard", () => {
  it("non-admin keeps the read-only view and the support copy", async () => {
    renderCard(false);
    expect(await screen.findByTestId("aviso-leitura")).toBeTruthy();
    expect(screen.getByTestId("aviso-nota-suporte").textContent).toBe(NOTA_AVISO_NOCTUS);
    expect(screen.queryByTestId("aviso-editar")).toBeNull();
  });

  it("platform admin sees Editar aviso instead of the support copy", async () => {
    renderCard(true);
    expect(await screen.findByTestId("aviso-editar")).toBeTruthy();
    expect(screen.queryByTestId("aviso-nota-suporte")).toBeNull();
    expect(screen.getByTestId("aviso-versao").textContent).toContain("3");
  });

  it("saves the edited notice via PUT and shows the new versão", async () => {
    api.put.mockResolvedValue({ data: { ...AVISO, titulo: "Novo título", versao: 4 } });
    renderCard(true);
    fireEvent.click(await screen.findByTestId("aviso-editar"));
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Novo título" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar seção" }));
    fireEvent.change(screen.getByLabelText("Título da seção", { selector: "#aviso-s-t-1" }), { target: { value: "Contato" } });
    fireEvent.click(screen.getByTestId("aviso-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    const [url, body] = api.put.mock.calls[0];
    expect(url).toBe("/api/julia/agente/aviso");
    expect(body.titulo).toBe("Novo título");
    expect(body.secoes).toHaveLength(2);
    expect(body.secoes[0].blocks).toEqual([{ p: "Coletamos nome." }, { ul: ["a", "b"] }]);
    expect((await screen.findByTestId("aviso-salvo")).textContent).toContain("4");
    expect(screen.getByTestId("aviso-titulo").textContent).toBe("Novo título");
  });

  it("shows the link_obrigatorio refusal and stays in the editor", async () => {
    api.put.mockRejectedValue(
      Object.assign(new Error("[422] x"), { status: 422, body: { error: { code: "link_obrigatorio", message: "m" } } }),
    );
    renderCard(true);
    fireEvent.click(await screen.findByTestId("aviso-editar"));
    fireEvent.click(screen.getByTestId("aviso-salvar"));
    const erro = await screen.findByTestId("aviso-erro-salvar");
    expect(erro.textContent).toContain("{link}");
    expect(screen.getByTestId("aviso-editor")).toBeTruthy();
  });
});

describe("textoParaBlocos", () => {
  it("round-trips paragraphs and lists", () => {
    expect(textoParaBlocos("Um.\n\n- a\n- b\n\nDois.")).toEqual([{ p: "Um." }, { ul: ["a", "b"] }, { p: "Dois." }]);
  });
});
