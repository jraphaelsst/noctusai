/** Skills library pages: list, create (chave check), draft edit, publish confirmation, read-only versions, error mapping. */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ConfirmProvider } from "@noctusai/lib/components";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { ApiError, errorMessage } from "@/lib/errors";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});

import SkillsBiblioteca from "../SkillsBiblioteca";
import SkillBiblioteca from "../SkillBiblioteca";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderAt(route: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConfirmProvider>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path="/studio/biblioteca-skills" element={<SkillsBiblioteca />} />
            <Route path="/studio/biblioteca-skills/:chave" element={<SkillBiblioteca />} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider>
    </QueryClientProvider>,
  );
}

const L = "/api/skills-biblioteca";
const row = (over = {}) => ({ id: "s1", chave: "skill-um", nome: "Skill Um", descricao: "desc", versao_publicada: null, tem_rascunho: false, ...over });
const V_DRAFT = "00000000-0000-4000-8000-0000000000d1";
const V_PUB = "00000000-0000-4000-8000-0000000000a1";
const versao = (over = {}) => ({
  id: V_DRAFT, skill: "skill-um", versao: 2, status: "rascunho", notas: null, publicada_em: null,
  descricao_modelo: "quando abrir", corpo: "corpo do playbook", arquivos: [{ caminho: "ref/a.md", titulo: null, conteudo: "ref" }], ...over,
});

describe("SkillsBiblioteca list", () => {
  it("lists skills with published/draft state", async () => {
    installFetch([{ method: "GET", path: L, body: { items: [row({ versao_publicada: 3, tem_rascunho: true }), row({ id: "s2", chave: "skill-dois", nome: "Dois" })] } }]);
    renderAt("/studio/biblioteca-skills");
    const um = await screen.findByTestId("skill-skill-um");
    expect(um.textContent).toContain("Publicada v3");
    expect(um.textContent).toContain("rascunho em edição");
    expect(screen.getByTestId("skill-skill-dois").textContent).toContain("Sem versão publicada");
  });

  it("shows the empty state", async () => {
    installFetch([{ method: "GET", path: L, body: { items: [] } }]);
    renderAt("/studio/biblioteca-skills");
    expect(await screen.findByText("Nenhuma skill na biblioteca ainda.")).toBeTruthy();
  });

  it("shows the restricted notice on 403", async () => {
    installFetch([{ method: "GET", path: L, status: 403, body: { detail: { detail: "x", code: "platform_admin_required" } } }]);
    renderAt("/studio/biblioteca-skills");
    expect((await screen.findByTestId("studio-restrito")).textContent).toContain("Restrito a administradores");
  });

  it("validates the chave client-side and creates the skill", async () => {
    const listBody = { items: [] as object[] };
    const net = installFetch([
      { method: "GET", path: L, body: listBody },
      { method: "POST", path: L, status: 201, body: row({ chave: "nova-skill", nome: "Nova" }) },
      { method: "GET", path: `${L}/nova-skill/versoes`, body: { items: [] } },
    ]);
    renderAt("/studio/biblioteca-skills");
    fireEvent.click(await screen.findByTestId("skill-nova"));
    fireEvent.change(screen.getByLabelText("Chave"), { target: { value: "Nova Skill" } });
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Nova" } });
    expect((screen.getByTestId("skill-nova-salvar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Chave"), { target: { value: "nova-skill" } });
    listBody.items.push(row({ chave: "nova-skill", nome: "Nova" })); // the server's list after the create
    fireEvent.click(screen.getByTestId("skill-nova-salvar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "POST")).toBe(true));
    expect(net.calls.find((c) => c.method === "POST")!.body).toEqual({ chave: "nova-skill", nome: "Nova", descricao: null });
    await waitFor(() => expect(screen.getByTestId("skill-biblioteca")).toBeTruthy()); // navigated to the detail
  });

  it("maps a duplicate-chave conflict to the server's PT-BR text", async () => {
    installFetch([
      { method: "GET", path: L, body: { items: [] } },
      { method: "POST", path: L, status: 409, body: { detail: { detail: "Já existe uma skill com essa chave.", code: "chave_duplicada" } } },
    ]);
    renderAt("/studio/biblioteca-skills");
    fireEvent.click(await screen.findByTestId("skill-nova"));
    fireEvent.change(screen.getByLabelText("Chave"), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "X" } });
    fireEvent.click(screen.getByTestId("skill-nova-salvar"));
    expect((await screen.findByTestId("conteudo-erro")).textContent).toBe("Já existe uma skill com essa chave.");
  });
});

describe("SkillBiblioteca detail", () => {
  const base = (over: object[] = []) => [
    { method: "GET" as const, path: L, body: { items: [row({ tem_rascunho: true })] } },
    { method: "GET" as const, path: `${L}/skill-um/versoes`, body: { items: [{ id: V_DRAFT, versao: 2, status: "rascunho", notas: null, publicada_em: null }, { id: V_PUB, versao: 1, status: "publicada", notas: null, publicada_em: "2026-10-01T10:00:00Z" }] } },
    { method: "GET" as const, path: `${L}/versoes/${V_DRAFT}`, body: versao() },
    { method: "GET" as const, path: `${L}/versoes/${V_PUB}`, body: versao({ id: V_PUB, versao: 1, status: "publicada" }) },
    ...(over as never[]),
  ];

  it("edits the draft fields and saves them", async () => {
    const net = installFetch(base([{ method: "PATCH", path: `${L}/versoes/${V_DRAFT}`, body: versao({ corpo: "novo corpo" }) }]));
    renderAt("/studio/biblioteca-skills/skill-um");
    const corpo = (await screen.findByLabelText(/Corpo/)) as HTMLTextAreaElement;
    expect(screen.getByLabelText("Descrição para o modelo")).toBeTruthy();
    fireEvent.change(corpo, { target: { value: "novo corpo" } });
    fireEvent.click(screen.getByTestId("skill-salvar-rascunho"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(net.calls.find((c) => c.method === "PATCH")!.body).toMatchObject({ corpo: "novo corpo", descricao_modelo: "quando abrir" });
    await waitFor(() => expect((screen.getByTestId("skill-salvar-rascunho") as HTMLButtonElement).disabled).toBe(true));
  });

  it("adds and removes a reference file", async () => {
    const withB = versao({ arquivos: [{ caminho: "ref/a.md", titulo: null, conteudo: "ref" }, { caminho: "ref/b.md", titulo: "B", conteudo: "bb" }] });
    const current = versao();
    const net = installFetch([
      ...base().filter((r) => r.path !== `${L}/versoes/${V_DRAFT}`),
      { method: "GET", path: `${L}/versoes/${V_DRAFT}`, body: current },
      { method: "PUT", path: `${L}/versoes/${V_DRAFT}/arquivos/ref/b.md`, body: withB },
      { method: "DELETE", path: `${L}/versoes/${V_DRAFT}/arquivos/ref/a.md`, status: 204 },
    ]);
    renderAt("/studio/biblioteca-skills/skill-um");
    await screen.findByTestId("skill-arquivo-ref/a.md");
    fireEvent.change(screen.getByLabelText("Caminho do novo arquivo"), { target: { value: "ref/b.md" } });
    fireEvent.change(screen.getByLabelText("Título do novo arquivo"), { target: { value: "B" } });
    fireEvent.change(screen.getByLabelText("Conteúdo do novo arquivo"), { target: { value: "bb" } });
    Object.assign(current, withB); // the server's version after the PUT
    fireEvent.click(screen.getByTestId("skill-arquivo-adicionar"));
    expect(await screen.findByTestId("skill-arquivo-ref/b.md")).toBeTruthy();
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ titulo: "B", conteudo: "bb" });
    current.arquivos = [withB.arquivos[1]];
    fireEvent.click(screen.getByLabelText("Remover ref/a.md"));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Remover" }));
    await waitFor(() => expect(screen.queryByTestId("skill-arquivo-ref/a.md")).toBeNull());
    expect(net.calls.some((c) => c.method === "DELETE")).toBe(true);
  });

  it("asks for confirmation (agents keep their pin) before publishing, then shows it published", async () => {
    const publicada = versao({ status: "publicada", publicada_em: "2026-10-23T10:00:00Z" });
    const current = versao();
    const net = installFetch([
      ...base().filter((r) => r.path !== `${L}/versoes/${V_DRAFT}`),
      { method: "GET", path: `${L}/versoes/${V_DRAFT}`, body: current },
      { method: "POST", path: `${L}/versoes/${V_DRAFT}/publicar`, body: publicada },
    ]);
    renderAt("/studio/biblioteca-skills/skill-um");
    fireEvent.click(await screen.findByTestId("skill-publicar"));
    expect(await screen.findByText(/continuam nela até você fixar a nova/)).toBeTruthy();
    expect(net.calls.some((c) => c.method === "POST")).toBe(false);
    Object.assign(current, publicada);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Publicar" }));
    await waitFor(() => expect(net.calls.some((c) => c.method === "POST")).toBe(true));
    await waitFor(() => expect(screen.getByTestId("skill-estado").textContent).toContain("Publicada v2 · somente leitura"));
    expect(screen.queryByTestId("skill-publicar")).toBeNull();
  });

  it("maps skill_incompleta to friendly PT-BR when publish is refused", async () => {
    installFetch(base([{ method: "POST", path: `${L}/versoes/${V_DRAFT}/publicar`, status: 422, body: { detail: { detail: "skill incompleta", code: "skill_incompleta" } } }]));
    renderAt("/studio/biblioteca-skills/skill-um");
    fireEvent.click(await screen.findByTestId("skill-publicar"));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Publicar" }));
    expect((await screen.findByTestId("conteudo-erro")).textContent).toContain("antes de publicar");
  });

  it("shows a published version read-only, without draft actions", async () => {
    installFetch(base());
    renderAt(`/studio/biblioteca-skills/skill-um?versao=${V_PUB}`);
    await waitFor(() => expect(screen.getByTestId("skill-estado").textContent).toContain("Publicada v1 · somente leitura"));
    expect(screen.queryByTestId("skill-publicar")).toBeNull();
    expect((screen.getByLabelText(/Corpo/) as HTMLTextAreaElement).readOnly).toBe(true);
  });

  it("offers to create a draft copying the published version when no draft exists", async () => {
    const metas = { items: [{ id: V_PUB, versao: 1, status: "publicada", notas: null, publicada_em: "2026-10-01T10:00:00Z" }] as object[] };
    const net = installFetch([
      { method: "GET", path: L, body: { items: [row({ versao_publicada: 1 })] } },
      { method: "GET", path: `${L}/skill-um/versoes`, body: metas },
      { method: "GET", path: `${L}/versoes/${V_PUB}`, body: versao({ id: V_PUB, versao: 1, status: "publicada" }) },
      { method: "POST", path: `${L}/skill-um/versoes`, status: 201, body: versao() },
      { method: "GET", path: `${L}/versoes/${V_DRAFT}`, body: versao() },
    ]);
    renderAt("/studio/biblioteca-skills/skill-um");
    const btn = await screen.findByTestId("skill-criar-rascunho");
    metas.items.unshift({ id: V_DRAFT, versao: 2, status: "rascunho", notas: null, publicada_em: null }); // the server's list after the POST
    fireEvent.click(btn);
    await waitFor(() => expect(net.calls.some((c) => c.method === "POST")).toBe(true));
    expect(net.calls.find((c) => c.method === "POST")!.body).toEqual({ copiar_de: V_PUB });
    await waitFor(() => expect(screen.getByTestId("skill-estado").textContent).toContain("Rascunho v2"));
  });

  it("shows the empty versions state for a brand-new skill", async () => {
    installFetch([
      { method: "GET", path: L, body: { items: [row()] } },
      { method: "GET", path: `${L}/skill-um/versoes`, body: { items: [] } },
    ]);
    renderAt("/studio/biblioteca-skills/skill-um");
    expect(await screen.findByText(/ainda não tem versões/)).toBeTruthy();
    expect(screen.getByTestId("skill-criar-rascunho").textContent).not.toContain("a partir");
  });
});

describe("errorMessage — skills library shapes", () => {
  it("reads the nested {detail:{detail,code}} text", () => {
    const body = { detail: { detail: "Já existe um rascunho.", code: "rascunho_existente" } };
    expect(errorMessage(new ApiError(409, "Erro HTTP 409", body))).toBe("Já existe um rascunho.");
  });
  it("maps version_immutable and a FastAPI 422 list", () => {
    expect(errorMessage(new ApiError(409, "Erro HTTP 409", { detail: { detail: "x", code: "version_immutable" } }))).toContain("não pode mais ser alterada");
    expect(errorMessage(new ApiError(422, "String too short", { detail: [{ msg: "String too short" }] }))).toBe("Dados inválidos — revise os campos destacados.");
  });
});
