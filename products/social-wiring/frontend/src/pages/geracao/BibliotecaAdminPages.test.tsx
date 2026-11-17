/** Import report + block-type catalog pages: restricted to admins, honest states, every refusal explained. */
import { ConfirmProvider } from "@noctusai/lib/components";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const m = vi.hoisted(() => ({ admin: vi.fn(), importacoes: vi.fn(), tipos: vi.fn(), salvar: vi.fn(), excluir: vi.fn() }));
vi.mock("@/hooks/geracao/useEstruturas", () => ({
  useEstruturasAdmin: () => m.admin(),
  useImportacoes: (...a: unknown[]) => m.importacoes(...a),
  useTiposBloco: () => m.tipos(),
  useSalvarTipoBloco: () => ({ mutateAsync: (v: unknown) => m.salvar(v), isPending: false }),
  useExcluirTipoBloco: () => ({ mutateAsync: (v: unknown) => m.excluir(v), isPending: false }),
}));

import { importacao, TIPOS } from "@/test/estruturasFixtures";
import BibliotecaImportacoes from "./BibliotecaImportacoes";
import BibliotecaTiposBloco from "./BibliotecaTiposBloco";

const base = { isRefreshing: false, isError: false, error: null, failureCount: 0, isFetching: false, refetch: vi.fn(), showSkeleton: false };
const apiErr = (code: string) => Object.assign(new Error("[409] x"), { code, status: 409 });
const wrap = (ui: React.ReactNode) => rtl.render(<MemoryRouter><ConfirmProvider>{ui}</ConfirmProvider></MemoryRouter>);
const dialogo = async () => rtl.within(await rtl.screen.findByRole("dialog"));

beforeEach(() => {
  vi.clearAllMocks();
  m.admin.mockReturnValue({ data: true, isPending: false, isError: false });
  m.importacoes.mockReturnValue({ ...base, data: { items: [importacao(), importacao({ id: "i2", fonte: "maquina_de_roteiros", status: "simulada", dry_run: true, erro: null, ignoradas_motivos: {}, campos_nao_importados: [], finished_at: null })], total: 2 } });
  m.tipos.mockReturnValue({ ...base, data: TIPOS });
  m.salvar.mockResolvedValue({});
  m.excluir.mockResolvedValue(undefined);
});

describe("Importações", () => {
  it("is restricted to admins (and does not even query for a member)", () => {
    m.admin.mockReturnValue({ data: false, isPending: false, isError: false });
    wrap(<BibliotecaImportacoes />);
    expect(rtl.screen.getByRole("alert").textContent).toContain("restrita a administradores");
    expect(m.importacoes.mock.calls.at(-1)![2]).toBe(false);
  });

  it("renders each run's counts in pt-BR, the dry-run mark, the reason histogram and non-imported fields", () => {
    wrap(<BibliotecaImportacoes />);
    const a = rtl.screen.getByTestId("importacao-i1");
    expect(a.textContent).toContain("Estruturas de referência");
    expect(a.textContent).toContain("Concluída");
    expect(a.textContent).toContain("Criadas7");
    expect(a.textContent).toContain("1 — perfil com @handle inválido");
    expect(a.textContent).toContain("nota_extra");
    expect(a.textContent).toContain("abcdef012345");
    const b = rtl.screen.getByTestId("importacao-i2");
    expect(b.textContent).toContain("Simulação (nada foi gravado)");
    expect(b.textContent).toContain("Máquina de Roteiros");
  });

  it("a failed run shows its error; empty and error states are honest", () => {
    m.importacoes.mockReturnValue({ ...base, data: { items: [importacao({ status: "falhou", erro: "arquivo truncado" })], total: 1 } });
    wrap(<BibliotecaImportacoes />);
    expect(rtl.screen.getByRole("alert").textContent).toContain("arquivo truncado");
    rtl.cleanup();
    m.importacoes.mockReturnValue({ ...base, data: { items: [], total: 0 } });
    wrap(<BibliotecaImportacoes />);
    expect(rtl.screen.getByText("Nenhuma importação ainda")).toBeTruthy();
    rtl.cleanup();
    m.importacoes.mockReturnValue({ ...base, data: undefined, isError: true, error: new Error("x") });
    wrap(<BibliotecaImportacoes />);
    expect(rtl.screen.getByRole("button", { name: /Tentar novamente/ })).toBeTruthy();
    rtl.cleanup();
    m.importacoes.mockReturnValue({ ...base, data: undefined, showSkeleton: true });
    wrap(<BibliotecaImportacoes />);
    expect(rtl.screen.getByLabelText("Carregando importações")).toBeTruthy();
  });
});

describe("Tipos de bloco", () => {
  it("is restricted to admins", () => {
    m.admin.mockReturnValue({ data: false, isPending: false, isError: false });
    wrap(<BibliotecaTiposBloco />);
    expect(rtl.screen.getByRole("alert").textContent).toContain("restrita a administradores");
    expect(rtl.screen.queryByRole("button", { name: "Novo tipo" })).toBeNull();
  });

  it("lists the catalog; 'Outro' is a protected system row with no actions", () => {
    wrap(<BibliotecaTiposBloco />);
    expect(rtl.screen.getByTestId("tipo-t1").textContent).toContain("Headline");
    const outro = rtl.screen.getByTestId("tipo-t4");
    expect(outro.textContent).toContain("Sistema");
    expect(rtl.within(outro).queryByRole("button")).toBeNull();
    expect(rtl.screen.getByTestId("tipo-t9").textContent).toContain("Inativo");
  });

  it("deactivates a type with the versao it was read with", async () => {
    m.tipos.mockReturnValue({ ...base, data: [{ ...TIPOS[0]!, versao: 4 }, ...TIPOS.slice(1)] });
    wrap(<BibliotecaTiposBloco />);
    await userEvent.click(rtl.screen.getByLabelText("Desativar o tipo Headline"));
    await rtl.waitFor(() => expect(m.salvar).toHaveBeenCalledWith(expect.objectContaining({ id: "t1", ativo: false, expected_versao: 4 })));
  });

  it("delete is confirmed; tipo_em_uso is explained (deactivate instead)", async () => {
    m.excluir.mockRejectedValueOnce(apiErr("tipo_em_uso"));
    wrap(<BibliotecaTiposBloco />);
    await userEvent.click(rtl.screen.getByLabelText("Excluir o tipo Revelação"));
    await userEvent.click((await dialogo()).getByRole("button", { name: "Excluir" }));
    await rtl.waitFor(() => expect(toast.error).toHaveBeenCalledWith("Este tipo de bloco está em uso. Desative-o em vez de excluir."));
    expect(m.excluir).toHaveBeenCalledWith("t2");
  });

  it("creates a type through the dialog, validating in pt-BR first", async () => {
    wrap(<BibliotecaTiposBloco />);
    await userEvent.click(rtl.screen.getByRole("button", { name: "Novo tipo" }));
    const d = await dialogo();
    await userEvent.click(d.getByRole("button", { name: "Salvar" }));
    expect(d.getByText("Informe o nome do tipo.")).toBeTruthy();
    expect(m.salvar).not.toHaveBeenCalled();
    await userEvent.type(d.getByLabelText("Nome"), "Prova social");
    await userEvent.type(d.getByLabelText("Instrução de referência"), "Mostre um resultado real.");
    await userEvent.click(d.getByRole("button", { name: "Salvar" }));
    await rtl.waitFor(() => expect(m.salvar).toHaveBeenCalledWith({ nome: "Prova social", tempo_tipico: null, instrucao_referencia: "Mostre um resultado real.", ativo: true }));
  });

  it("a refused save is shown inside the dialog (409 versao_desatualizada)", async () => {
    m.salvar.mockRejectedValueOnce(apiErr("versao_desatualizada"));
    wrap(<BibliotecaTiposBloco />);
    await userEvent.click(rtl.screen.getByLabelText("Editar o tipo Headline"));
    await userEvent.click((await dialogo()).getByRole("button", { name: "Salvar" }));
    expect((await rtl.screen.findAllByRole("alert")).some((a) => a.textContent?.includes("alterada por outra pessoa"))).toBe(true);
  });
});
