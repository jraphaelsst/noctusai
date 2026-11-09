import React from "react";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const platformAdmin = vi.fn();
const orgAdmin = vi.fn();
const iniciar = vi.fn();
const mecRun = vi.fn();
const criarEval = vi.fn();
const evalRun = vi.fn();
const ligar = vi.fn();
const agentHook = vi.fn();

vi.mock("@/hooks/useIsPlatformAdmin", () => ({ useIsPlatformAdmin: () => platformAdmin() }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => orgAdmin() }));
vi.mock("@/hooks/studio/useMecanismo", () => ({ useIniciarMecanismo: () => iniciar(), useMecanismoRun: (...a: unknown[]) => mecRun(...a) }));
vi.mock("@/hooks/studio/useEvals", () => ({ useCreateEvalRun: () => criarEval(), useEvalRun: () => evalRun() }));
vi.mock("@/hooks/studio/useControle", () => ({ useSetControle: () => ligar() }));
vi.mock("@/hooks/studio/useBiblioteca", () => ({ useAtualizarSkillsBiblioteca: () => ({ mutate: vi.fn(), isPending: false, isError: false, isSuccess: false }) }));
vi.mock("@/hooks/studio/useStudioAgents", () => ({ useStudioAgent: () => agentHook() }));

import { ProntidaoAcao, acaoDoItem, descreverFalha } from "@/components/studio/ProntidaoAcao";

const mut = (over: object = {}) => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, isError: false, isSuccess: false, error: null, ...over });
const runView = (data?: object, over: object = {}) => ({ data, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn(), ...over });
const MEC = { run_id: "r1", status: "concluida", aprovado: false, completo: true, orcamento_excedido: false, total_casos: 2, casos_aprovados: 1, erro: null, casos: [] };

beforeEach(() => {
  platformAdmin.mockReturnValue(true);
  orgAdmin.mockReturnValue(true);
  iniciar.mockReturnValue(mut());
  mecRun.mockReturnValue(runView());
  criarEval.mockReturnValue(mut());
  evalRun.mockReturnValue(runView());
  ligar.mockReturnValue(mut());
  agentHook.mockReturnValue({ data: { versoes: [{ id: "d1", status: "rascunho" }, { id: "a1", status: "ativa" }] }, showSkeleton: false });
});
afterEach(cleanup);

describe("acaoDoItem", () => {
  it("maps fixable items to an action and leaves ok/other items alone", () => {
    expect(acaoDoItem("mecanismo_hash_diferente")).toBe("mecanismo");
    expect(acaoDoItem("mecanismo_ok")).toBeNull();
    expect(acaoDoItem("mecanismo_nao_configurado")).toBeNull();
    expect(acaoDoItem("eval_juiz_sem_execucao")).toBe("avaliacao");
    expect(acaoDoItem("eval_juiz_ok")).toBeNull();
    expect(acaoDoItem("eval_sem_casos")).toBeNull();
    expect(acaoDoItem("controles_desligado")).toBe("ligar");
    expect(acaoDoItem("skill_desatualizada")).toBe("skills");
  });
  it("describes assert failures in pt-BR with a safe fallback", () => {
    expect(descreverFalha("sem_pii", "cpf")).toContain("dado pessoal");
    expect(descreverFalha("inexistente", "x")).toContain("verificação");
  });
});

describe("mecanismo action", () => {
  it("lets a second run start while one executes (parallel runs, 071) and follows the newest", () => {
    let n = 0;
    const m = mut({ mutate: (_v: unknown, o: { onSuccess: (r: { run_id: string }) => void }) => o.onSuccess({ run_id: `r${++n}` }) });
    iniciar.mockReturnValue(m);
    mecRun.mockReturnValue(runView({ ...MEC, status: "executando" }));
    render(<ProntidaoAcao codigo="mecanismo_hash_diferente" agentKey="julia" />);
    const botao = screen.getByRole("button", { name: /Rodar suíte de mecanismo/ }) as HTMLButtonElement;
    fireEvent.click(botao);
    expect(botao.disabled).toBe(false);
    fireEvent.click(botao);
    expect(mecRun).toHaveBeenLastCalledWith("julia", "r2");
  });

  it("starts the suite on click", () => {
    const m = mut();
    iniciar.mockReturnValue(m);
    render(<ProntidaoAcao codigo="mecanismo_hash_diferente" agentKey="julia" />);
    fireEvent.click(screen.getByRole("button", { name: /Rodar suíte de mecanismo/ }));
    expect(m.mutate).toHaveBeenCalled();
  });
  it("hides the button from non platform admins and says who can", () => {
    platformAdmin.mockReturnValue(false);
    render(<ProntidaoAcao codigo="mecanismo_hash_diferente" agentKey="julia" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByTestId("acao-mecanismo-restrito").textContent).toContain("administrador da plataforma");
  });
  it("shows the server refusal (409) in plain words", () => {
    iniciar.mockReturnValue(mut({ isError: true, error: new Error("O agente não tem casos de mecanismo ativos.") }));
    render(<ProntidaoAcao codigo="mecanismo_hash_diferente" agentKey="julia" />);
    expect(screen.getByRole("alert").textContent).toContain("casos de mecanismo");
  });
  it("shows progress and disables the button while running", () => {
    iniciar.mockReturnValue(mut({ isPending: true }));
    render(<ProntidaoAcao codigo="mecanismo_hash_diferente" agentKey="julia" />);
    expect((screen.getByRole("button", { name: /Rodar suíte/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("Rodando a suíte");
  });
  it("lists failing cases with pt-BR reasons once done", () => {
    mecRun.mockReturnValue(runView({
      ...MEC,
      casos: [
        { slug: "lead-frio", passou: false, taxa: 0, execucoes: [{ indice: 1, status: "reprovado", falhas: [{ assert: "sem_pii", codigo: "cpf" }] }] },
        { slug: "lead-quente", passou: true, taxa: 1, execucoes: [] },
      ],
    }));
    iniciar.mockReturnValue(mut({ isSuccess: true }));
    // the component keeps the run id in state: simulate a click that resolved the POST
    const m = mut({ mutate: (_v: unknown, o: { onSuccess: (r: { run_id: string }) => void }) => o.onSuccess({ run_id: "r1" }) });
    iniciar.mockReturnValue(m);
    render(<ProntidaoAcao codigo="mecanismo_hash_diferente" agentKey="julia" />);
    fireEvent.click(screen.getByRole("button", { name: /Rodar suíte/ }));
    expect(screen.getByTestId("acao-mecanismo-resultado").textContent).toContain("1 de 2 casos passaram");
    expect(screen.getByTestId("acao-mecanismo-falhas").textContent).toContain("lead-frio");
    expect(screen.getByTestId("acao-mecanismo-falhas").textContent).toContain("dado pessoal");
  });
  it("shows a failed run with its fixed reason", () => {
    mecRun.mockReturnValue(runView({ ...MEC, status: "falhou", erro: "Falha ao executar a suíte." }));
    iniciar.mockReturnValue(mut({ mutate: (_v: unknown, o: { onSuccess: (r: { run_id: string }) => void }) => o.onSuccess({ run_id: "r1" }) }));
    render(<ProntidaoAcao codigo="mecanismo_hash_diferente" agentKey="julia" />);
    fireEvent.click(screen.getByRole("button", { name: /Rodar suíte/ }));
    expect(screen.getByTestId("acao-mecanismo-falhou").textContent).toContain("Falha ao executar a suíte");
  });
});

describe("avaliacao action", () => {
  it("creates a run on the draft version", () => {
    const m = mut();
    criarEval.mockReturnValue(m);
    render(<ProntidaoAcao codigo="eval_juiz_sem_execucao" agentKey="julia" />);
    fireEvent.click(screen.getByRole("button", { name: /Rodar avaliação completa/ }));
    expect(m.mutate).toHaveBeenCalledWith({ version_id: "d1" }, expect.any(Object));
  });
  it("is disabled with a hint when there is no draft", () => {
    agentHook.mockReturnValue({ data: { versoes: [{ id: "a1", status: "ativa" }] }, showSkeleton: false });
    render(<ProntidaoAcao codigo="eval_juiz_sem_execucao" agentKey="julia" />);
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("acao-avaliacao-sem-rascunho")).toBeTruthy();
  });
  it("shows the run's progress while in flight", () => {
    criarEval.mockReturnValue(mut({ mutate: (_v: unknown, o: { onSuccess: (r: { id: string }) => void }) => o.onSuccess({ id: "e1" }) }));
    evalRun.mockReturnValue(runView({ status: "executando", total: 5, aprovados: 2 }));
    render(<ProntidaoAcao codigo="eval_juiz_sem_execucao" agentKey="julia" />);
    fireEvent.click(screen.getByRole("button", { name: /Rodar avaliação/ }));
    expect(screen.getByRole("status").textContent).toContain("2 de 5");
  });
});

describe("ligar action", () => {
  it("turns the agent on", () => {
    const m = mut();
    ligar.mockReturnValue(m);
    render(<ProntidaoAcao codigo="controles_desligado" agentKey="julia" />);
    fireEvent.click(screen.getByRole("button", { name: "Ligar agente" }));
    expect(m.mutate).toHaveBeenCalledWith({ modo: "ligado" });
  });
  it("asks to publish first when no version is active", () => {
    agentHook.mockReturnValue({ data: { versoes: [{ id: "d1", status: "rascunho" }] }, showSkeleton: false });
    render(<ProntidaoAcao codigo="controles_desligado" agentKey="julia" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByTestId("acao-ligar-publicar").textContent).toContain("Publique o agente");
  });
  it("hides the button from non org admins", () => {
    orgAdmin.mockReturnValue(false);
    render(<ProntidaoAcao codigo="controles_desligado" agentKey="julia" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByTestId("acao-ligar-restrito")).toBeTruthy();
  });
  it("shows the server refusal", () => {
    ligar.mockReturnValue(mut({ isError: true, error: new Error("Conteúdo incompleto.") }));
    render(<ProntidaoAcao codigo="controles_desligado" agentKey="julia" />);
    expect(screen.getByRole("alert").textContent).toContain("Conteúdo incompleto");
  });
});
