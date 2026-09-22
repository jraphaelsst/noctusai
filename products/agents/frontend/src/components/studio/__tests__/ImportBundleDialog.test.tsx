/**
 * ImportBundleDialog tests — Agent Studio CONTRACT.md §D5, §F, tech-lead
 * runtime add-on "item 11" (no UI existed for the import endpoint). Covers
 * the dry-run-then-confirm flow and the Overview tab's key-mismatch guard.
 * `useImportBundle` is stubbed; the hook has its own request-shape test.
 */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ImportBundleDialog } from "@/components/studio/ImportBundleDialog";

const mockUseImportBundle = vi.fn();
vi.mock("@/hooks/studio/useImportBundle", () => ({ useImportBundle: () => mockUseImportBundle() }));

afterEach(() => cleanup());

const BUNDLE = {
  formato: "noctus.agent-bundle/v1",
  agente: { key: "isaia", nome: "IsaIA", descricao: "Estrategista de Instagram." },
  versao: { notas: "", model: "claude-opus-5", effort: "high", max_turns: 40, idioma: "pt-BR", tool_policy: { web_search: true, knowledge: true } },
  secoes: [{ chave: "identidade", titulo: "Identidade", ordem: 10, conteudo: "...", ativo: true }],
  skills: [{ nome: "roteiro-reels", descricao: "...", corpo: "...", ordem: 10, ativo: true, arquivos: [] }],
  conhecimento: [{ slug: "audience", nome: "Audiência", tag: "AU", descricao: "", ordem: 10, documentos: [{ slug: "a", titulo: "A", tipo: "fonte", resumo: "", proveniencia: {}, conteudo: "..." }] }],
  evals: [{ slug: "caso-1", titulo: "Caso 1", entrada: "...", contexto: null, criterios: { deve: ["x"], nao_deve: [] }, rubrica: null, tags: [] }],
  clientes: [],
};

const PLAN = {
  dry_run: true,
  agente: { criado: false },
  rascunho: { version_id: "v1", secoes: 1, skills: 1, arquivos: 0 },
  conhecimento: { colecoes_criadas: 0, documentos_criados: 1, documentos_atualizados: 0, documentos_inalterados: 0 },
  evals: { criados: 1, atualizados: 0 },
  clientes: { criados: 0 },
  avisos: ["Seção 'identidade' já existe e será substituída."],
};

function makeFile(content: unknown, name = "bundle.json") {
  return new File([JSON.stringify(content)], name, { type: "application/json" });
}

/** Selects `file` on the hidden input and waits for the client-side parse. */
async function selectFile(file: File) {
  const input = screen.getByTestId("import-bundle-file-input") as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
  await waitFor(() => expect(screen.queryByTestId("import-bundle-preview") ?? screen.queryByRole("alert")).toBeTruthy());
}

describe("ImportBundleDialog — dry-run then confirm", () => {
  it("parses the file, shows the plan on dry-run, then imports and reports the key", async () => {
    const mutateAsync = vi.fn().mockImplementation(async ({ dryRun }: { dryRun: boolean }) =>
      dryRun ? PLAN : { ...PLAN, dry_run: false },
    );
    mockUseImportBundle.mockReturnValue({ mutateAsync, isPending: false });
    const onImported = vi.fn();
    render(<ImportBundleDialog onClose={vi.fn()} onImported={onImported} />);

    await selectFile(makeFile(BUNDLE));
    expect(screen.getByTestId("import-bundle-preview").textContent).toContain("IsaIA");
    expect(screen.getByTestId("import-bundle-preview").textContent).toContain("isaia");

    fireEvent.click(screen.getByTestId("import-bundle-dry-run"));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ key: "isaia", bundle: expect.objectContaining({ agente: BUNDLE.agente }), dryRun: true }));
    const plan = await screen.findByTestId("import-bundle-plan");
    expect(plan.textContent).toContain("já existe e será substituída");
    expect(plan.textContent).toContain("simulação");

    fireEvent.click(screen.getByTestId("import-bundle-confirm"));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ key: "isaia", bundle: expect.anything(), dryRun: false }));
    await waitFor(() => expect(onImported).toHaveBeenCalledWith("isaia"));
  });

  it("shows a parse error for a non-bundle JSON file and never calls the mutation", async () => {
    const mutateAsync = vi.fn();
    mockUseImportBundle.mockReturnValue({ mutateAsync, isPending: false });
    render(<ImportBundleDialog onClose={vi.fn()} onImported={vi.fn()} />);

    await selectFile(makeFile({ formato: "algo-diferente" }));
    expect(screen.getByRole("alert").textContent).toContain("Formato inesperado");
    expect(screen.queryByTestId("import-bundle-dry-run")?.hasAttribute("disabled")).toBe(true);
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});

describe("ImportBundleDialog — key-mismatch guard (Overview tab)", () => {
  it("blocks the plan/import actions when the bundle's agente.key differs from expectedAgentKey", async () => {
    const mutateAsync = vi.fn();
    mockUseImportBundle.mockReturnValue({ mutateAsync, isPending: false });
    render(<ImportBundleDialog expectedAgentKey="outro-agente" onClose={vi.fn()} onImported={vi.fn()} />);

    await selectFile(makeFile(BUNDLE));
    const mismatch = screen.getByTestId("import-bundle-key-mismatch");
    expect(mismatch.textContent).toContain("isaia");
    expect(mismatch.textContent).toContain("outro-agente");
    expect(screen.getByTestId("import-bundle-dry-run").hasAttribute("disabled")).toBe(true);

    fireEvent.click(screen.getByTestId("import-bundle-dry-run"));
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("allows the flow when the bundle's key matches expectedAgentKey", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(PLAN);
    mockUseImportBundle.mockReturnValue({ mutateAsync, isPending: false });
    render(<ImportBundleDialog expectedAgentKey="isaia" onClose={vi.fn()} onImported={vi.fn()} />);

    await selectFile(makeFile(BUNDLE));
    expect(screen.queryByTestId("import-bundle-key-mismatch")).toBeNull();
    fireEvent.click(screen.getByTestId("import-bundle-dry-run"));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  });
});
