/** "Adicionar por link": allowlist pre-check, every outcome and every refusal code rendered. */
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

const m = vi.hoisted(() => ({ add: vi.fn() }));
vi.mock("@/hooks/geracao/useEstruturas", () => ({
  useAdicionarVideoPorLink: () => ({ mutateAsync: (u: string) => m.add(u), isPending: false, reset: vi.fn() }),
}));

import { PorLinkDialog } from "./PorLinkDialog";

const apiErr = (code: string, status: number) => Object.assign(new Error(`[${status}] x`), { code, status });
const viral = { id: "v9", codigo: 9, perfil: { id: "p9", handle: "novo.perfil" } };

function abrir() {
  const onOpenChange = vi.fn();
  rtl.render(
    <MemoryRouter>
      <PorLinkDialog open onOpenChange={onOpenChange} />
    </MemoryRouter>,
  );
  return { onOpenChange };
}
const colar = (v: string) => userEvent.type(rtl.screen.getByLabelText("Link do post do Instagram"), v);
const enviar = () => userEvent.click(rtl.screen.getByRole("button", { name: "Adicionar" }));

beforeEach(() => vi.clearAllMocks());

describe("PorLinkDialog", () => {
  it("rejects a non-Instagram link locally, with the contract's sentence, without a request", async () => {
    abrir();
    await colar("https://evil.com/reel/AbC123/");
    await enviar();
    expect((await rtl.screen.findByRole("alert")).textContent).toContain("Cole o link de um post do Instagram");
    expect(m.add).not.toHaveBeenCalled();
  });

  it("posts the normalised URL and reports a new video (+ the auto-created profile)", async () => {
    m.add.mockResolvedValue({ viral, perfil_criado: true, ja_existia: false });
    abrir();
    await colar("instagram.com/reel/AbC123/");
    await enviar();
    await rtl.waitFor(() => expect(m.add).toHaveBeenCalledWith("https://instagram.com/reel/AbC123/"));
    const r = await rtl.screen.findByTestId("por-link-resultado");
    expect(r.textContent).toContain("Vídeo adicionado");
    expect(r.textContent).toContain("@novo.perfil foi criado");
    expect(rtl.screen.getByRole("link", { name: "Abrir o vídeo" }).getAttribute("href")).toBe("/media-creation/biblioteca?viral=v9");
  });

  it("ja_existia says it was already there and that nothing changed", async () => {
    m.add.mockResolvedValue({ viral, perfil_criado: false, ja_existia: true });
    abrir();
    await colar("https://www.instagram.com/p/AbC123/");
    await enviar();
    expect((await rtl.screen.findByTestId("por-link-resultado")).textContent).toContain("já estava na biblioteca");
  });

  it.each([
    ["post_nao_encontrado", 404, "Não encontramos este post (privado ou removido)."],
    ["perfil_optout", 409, "Este criador pediu para não ser monitorado."],
    ["fonte_nao_suporta_link", 409, "A fonte de ingestão atual não consegue buscar um post avulso."],
    ["link_invalido", 422, "Cole o link de um post do Instagram (instagram.com/p/…, /reel/… ou /tv/…)."],
    ["ingestao_sem_org_plataforma", 503, "A organização de ingestão da biblioteca não está configurada."],
  ])("renders the %s refusal inline", async (code, status, texto) => {
    m.add.mockRejectedValue(apiErr(code, status));
    abrir();
    await colar("https://www.instagram.com/reel/AbC123/");
    await enviar();
    expect((await rtl.screen.findByRole("alert")).textContent).toBe(texto);
  });
});
