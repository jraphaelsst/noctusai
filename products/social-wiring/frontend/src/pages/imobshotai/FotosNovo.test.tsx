/**
 * ImobShotAI photo funnel -- the 6 steps of contract §8, driven through the UI against the HTTP boundary
 * (contract-shaped fixtures): picker select-only (step 1), `POST /api/imobshotai/lotes` body + error-code mapping,
 * upload in blocks of 10 (step 2), read-only style (step 3), submit + progress (step 4), D6 approve/reject hiding
 * for non-admins (step 5), and the link to the card (step 6).
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";

const { admin, toastError, toastSuccess } = vi.hoisted(() => ({
  admin: { value: false },
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", async () => ({ api: (await import("@/test/imobshotaiApiMock")).api }));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));
vi.mock("sonner", () => ({ toast: { success: toastSuccess, error: toastError } }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({
  ...(await orig<object>()),
  useIsOrgAdmin: () => admin.value,
}));

import {
  api,
  CAPACIDADES,
  CONFIGURACOES,
  cardResumo,
  erroDoContrato,
  fotoRevisao,
  limparRotas,
  loteResumo,
  renderComQuery,
  rota,
} from "@/test/imobshotaiApiMock";
import FotosNovo, { emBlocos } from "./FotosNovo";

const BUSCA_HIT = {
  codigo: "ONE8990",
  titulo: "Apartamento amplo",
  empreendimento: null,
  logradouro: null,
  numero: null,
  complemento: null,
  bairro: "Pinheiros",
  cidade: "São Paulo",
  uf: null,
  cep: null,
  foto_destaque: null,
  captacao: null,
  corretores: [],
  ativo_no_vista: true,
  fonte: "imoveis",
};

function loteDetalhe(estado: string, n = 1) {
  return {
    id: "lote-1",
    nome: "Fotos ONE8990 13/11",
    velocidade: "urgente",
    imovel: { org_id: "org-1", codigo: "ONE8990" },
    criado_em: "2026-11-13T09:00:00Z",
    fotos: Array.from({ length: n }, (_, i) => fotoRevisao({ id: `f${i + 1}`, estado })),
  };
}

function rotasBase() {
  rota("GET", "/api/edicao-fotos/capacidades", () => CAPACIDADES);
  rota("GET", "/api/edicao-fotos/configuracoes", () => CONFIGURACOES);
  rota("GET", "/api/edicao-fotos/regras/guia-efetivo", () => ({
    atual: { id: "g1", guia_estilo_id: "ge1", conjunto_regras_id: null, texto: "Luz natural, sem exagero.", sha256: "x", criado_em: null },
    historico: { items: [], page: 1, page_size: 1, total: 0 },
  }));
  rota("GET", "/api/imoveis/busca", () => ({ items: [BUSCA_HIT] }));
  rota("POST", "/api/imobshotai/lotes", () => ({ card: cardResumo(), lote: loteResumo() }));
}

async function escolherImovel() {
  fireEvent.change(await screen.findByTestId("imovel-picker-input"), { target: { value: "ONE" } });
  fireEvent.click(await screen.findByTestId("imovel-picker-opcao-ONE8990"));
}

async function iniciar() {
  await escolherImovel();
  fireEvent.click(await screen.findByRole("button", { name: "Continuar" }));
}

/** Drive the funnel up to step 5 (review) using the Vista pull. */
async function ateRevisao() {
  rota("POST", "/api/edicao-fotos/lotes/lote-1/vista", () => ({}));
  rota("GET", "/api/edicao-fotos/lotes/lote-1", () => loteDetalhe("aguardando_decisao"));
  rota("POST", "/api/edicao-fotos/lotes/lote-1/submeter", () => loteResumo({ estado_agregado: "processando" }));
  rota("GET", "/api/edicao-fotos/revisao/lote-1", () => [fotoRevisao()]);
  await iniciar();
  fireEvent.click(await screen.findByRole("button", { name: "Puxar fotos do Vista" }));
  await waitFor(() => expect(screen.getByTestId("imobshotai-total-fotos")).toHaveTextContent("1 foto(s)"));
  fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
  fireEvent.click(await screen.findByRole("button", { name: "Continuar" })); // step 3 -> 4
  fireEvent.click(await screen.findByRole("button", { name: "Enviar para edição" }));
  const revisar = await screen.findByRole("button", { name: "Ir para a revisão" });
  await waitFor(() => expect(revisar).toBeEnabled());
  fireEvent.click(revisar);
}

beforeEach(() => {
  limparRotas();
  admin.value = false;
  toastError.mockClear();
  toastSuccess.mockClear();
  rotasBase();
});
afterEach(cleanup);

describe("emBlocos", () => {
  it("splits into blocks of at most N, keeping order", () => {
    expect(emBlocos([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
    expect(emBlocos([], 10)).toEqual([]);
  });
});

describe("step 1 · Imóvel (picker select-only)", () => {
  it("loading gate: skeleton until capacidades land", async () => {
    rota("GET", "/api/edicao-fotos/capacidades", () => new Promise(() => {}));
    renderComQuery(<FotosNovo />);
    expect(await screen.findByTestId("imobshotai-funil-loading")).toBeInTheDocument();
  });

  it("a role without access sees the contract message", async () => {
    rota("GET", "/api/edicao-fotos/capacidades", () => ({ ...CAPACIDADES, pode_criar_lote: false }));
    renderComQuery(<FotosNovo />);
    expect(await screen.findByText("Seu papel não dá acesso ao ImobShotAI.")).toBeInTheDocument();
  });

  it("capacidades failing offers a retry", async () => {
    rota("GET", "/api/edicao-fotos/capacidades", () => {
      throw new Error("x");
    });
    renderComQuery(<FotosNovo />);
    expect(await screen.findByText("Não foi possível carregar as permissões para editar fotos.")).toBeInTheDocument();
  });

  it("under 2 characters: hint; empty result: contract message and NO way to register a new imóvel", async () => {
    rota("GET", "/api/imoveis/busca", () => ({ items: [] }));
    renderComQuery(<FotosNovo />);
    const input = await screen.findByTestId("imovel-picker-input");
    expect(screen.getByText(/Digite ao menos 2 caracteres/)).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "ZZZ" } });
    expect(await screen.findByText("Nenhum imóvel com esse código.")).toBeInTheDocument();
    expect(screen.queryByTestId("imovel-picker-cadastrar-novo")).toBeNull();
    // free text can never be submitted: no chosen imóvel -> no continue button
    expect(screen.getByRole("button", { name: "Continuar" })).toBeDisabled();
  });

  it("picking a ref and continuing POSTs exactly the contract body, then lands on step 2", async () => {
    renderComQuery(<FotosNovo />);
    await iniciar();
    expect(await screen.findByRole("button", { name: "Puxar fotos do Vista" })).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith("/api/imobshotai/lotes", { imovel_codigo: "ONE8990", velocidade: "urgente" });
  });

  it("imovel_inexistente (422) -> the contract message, and the user stays on step 1", async () => {
    rota("POST", "/api/imobshotai/lotes", () => {
      throw erroDoContrato(422, "imovel_inexistente", "Imóvel inexistente.");
    });
    renderComQuery(<FotosNovo />);
    await iniciar();
    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Nenhum imóvel com esse código."));
    expect(screen.queryByRole("button", { name: "Puxar fotos do Vista" })).toBeNull();
  });

  it("sem_acesso_edicao_fotos (403) maps to the contract message", async () => {
    rota("POST", "/api/imobshotai/lotes", () => {
      throw erroDoContrato(403, "sem_acesso_edicao_fotos", "Sem acesso.");
    });
    renderComQuery(<FotosNovo />);
    await iniciar();
    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Seu papel não dá acesso ao ImobShotAI."));
  });

  it("modelo_nao_configurado (422) keeps the lotes-route server message", async () => {
    rota("POST", "/api/imobshotai/lotes", () => {
      throw erroDoContrato(422, "modelo_nao_configurado", "Escolha um modelo de edição.");
    });
    renderComQuery(<FotosNovo />);
    await iniciar();
    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Escolha um modelo de edição."));
  });
});

describe("step 2 · Fotos", () => {
  it("uploads in requests of at most 10 files", async () => {
    rota("UPLOAD", "/api/edicao-fotos/lotes/lote-1/fotos", () => ({}));
    rota("GET", "/api/edicao-fotos/lotes/lote-1", () => loteDetalhe("recebida", 0));
    renderComQuery(<FotosNovo />);
    await iniciar();
    const input = await screen.findByLabelText(/Fotos \(até/);
    const arquivos = Array.from({ length: 12 }, (_, i) => new File(["x"], `f${i}.jpg`, { type: "image/jpeg" }));
    fireEvent.change(input, { target: { files: arquivos } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar fotos" }));
    await waitFor(() => expect(api.upload).toHaveBeenCalledTimes(2));
    const contagens = api.upload.mock.calls.map(([, form]) => (form as FormData).getAll("fotos").length);
    expect(contagens).toEqual([10, 2]);
  });

  it("cannot continue without photos", async () => {
    rota("GET", "/api/edicao-fotos/lotes/lote-1", () => loteDetalhe("recebida", 0));
    renderComQuery(<FotosNovo />);
    await iniciar();
    await screen.findByRole("button", { name: "Puxar fotos do Vista" });
    expect(screen.getByRole("button", { name: "Continuar" })).toBeDisabled();
  });
});

describe("steps 3-6", () => {
  it("step 3 shows the lote's speed and the active style guide, read-only", async () => {
    rota("POST", "/api/edicao-fotos/lotes/lote-1/vista", () => ({}));
    rota("GET", "/api/edicao-fotos/lotes/lote-1", () => loteDetalhe("recebida"));
    renderComQuery(<FotosNovo />);
    await iniciar();
    fireEvent.click(await screen.findByRole("button", { name: "Puxar fotos do Vista" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Continuar" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByText("Urgente")).toBeInTheDocument();
    expect(await screen.findByTestId("imobshotai-guia")).toHaveTextContent("Luz natural, sem exagero.");
  });

  it("D6: a non-admin sees NO approve/reject and the waiting message", async () => {
    admin.value = false;
    renderComQuery(<FotosNovo />);
    await ateRevisao();
    expect(await screen.findByText("Aguardando aprovação de um administrador.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aprovar foto" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rejeitar foto" })).toBeNull();
  });

  it("D6: an org admin sees approve/reject", async () => {
    admin.value = true;
    renderComQuery(<FotosNovo />);
    await ateRevisao();
    expect(await screen.findByRole("button", { name: "Aprovar foto" })).toBeInTheDocument();
    expect(screen.queryByText("Aguardando aprovação de um administrador.")).toBeNull();
  });

  it("step 6 links to the card and offers a disabled video CTA", async () => {
    renderComQuery(<FotosNovo />);
    await ateRevisao();
    fireEvent.click(await screen.findByRole("button", { name: "Concluir" }));
    expect(await screen.findByRole("link", { name: "Ver o imóvel" })).toHaveAttribute("href", "/imobshotai/imoveis/card-1");
    expect(screen.getByRole("button", { name: "Criar vídeo (em breve)" })).toBeDisabled();
  });

  it("submit failure maps the error and keeps the user on step 4", async () => {
    rota("POST", "/api/edicao-fotos/lotes/lote-1/vista", () => ({}));
    rota("GET", "/api/edicao-fotos/lotes/lote-1", () => loteDetalhe("recebida"));
    rota("POST", "/api/edicao-fotos/lotes/lote-1/submeter", () => {
      throw erroDoContrato(422, "sem_tipos_edicao", "Ative ao menos um tipo de edição.");
    });
    renderComQuery(<FotosNovo />);
    await iniciar();
    fireEvent.click(await screen.findByRole("button", { name: "Puxar fotos do Vista" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Continuar" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    fireEvent.click(await screen.findByRole("button", { name: "Continuar" }));
    fireEvent.click(await screen.findByRole("button", { name: "Enviar para edição" }));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Ative ao menos um tipo de edição."));
    expect(screen.getByRole("button", { name: "Enviar para edição" })).toBeInTheDocument();
  });
});
