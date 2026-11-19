import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/seed/infra", () => ({ api }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ReengajamentoPadraoTab } from "./ReengajamentoPadraoTab";
import { resumoHorario } from "./HorarioAtendimentoCard";
import { validarHorario, validarTextoPortal } from "@/hooks/useJuliaReengajamento";

const CFG = {
  minutos_ativo: false, minutos_intervalo: 15, horas_ativo: false, horas_intervalo: 2, portal_primeiro_contato_ativo: true,
  horario_abertura: "08:00", horario_fechamento: "20:00", dias_atendimento: [1, 2, 3, 4, 5, 6, 7], portal_primeiro_contato_texto: null as string | null,
};
const URL_PUT = "/api/julia/reengajamento/config";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}
const erro422 = (code: string, message: string) => ({ body: { error: { code, message } } });

beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));
afterEach(cleanup);

describe("regras puras", () => {
  it("resumo do horário", () => {
    expect(resumoHorario(CFG)).toBe("das 8h às 20h · todos os dias");
    expect(resumoHorario({ ...CFG, horario_abertura: "09:30", horario_fechamento: "18:00", dias_atendimento: [1, 2, 3, 4, 5] })).toBe(
      "das 9h30 às 18h · de segunda a sexta",
    );
    expect(resumoHorario({ ...CFG, dias_atendimento: [1, 3, 6] })).toBe("das 8h às 20h · Seg, Qua, Sáb");
  });
  it("valida abertura < fechamento e ao menos um dia", () => {
    expect(validarHorario("08:00", "20:00", [1])).toBeNull();
    expect(validarHorario("20:00", "08:00", [1])).toContain("meia-noite");
    expect(validarHorario("09:00", "09:00", [1])).not.toBeNull();
    expect(validarHorario("08:00", "20:00", [])).toContain("dia da semana");
  });
  it("o texto do portal exige {link}; vazio é permitido", () => {
    expect(validarTextoPortal("")).toBeNull();
    expect(validarTextoPortal("Oi, {link}")).toBeNull();
    expect(validarTextoPortal("Oi, sou a Julia")).toContain("{link}");
  });
});

describe("Horário de atendimento", () => {
  it("mostra o horário atual, o fuso e salva a alteração (admin)", async () => {
    api.get.mockResolvedValue({ data: CFG });
    const novo = { ...CFG, horario_abertura: "09:00", dias_atendimento: [1, 2, 3, 4, 5] };
    api.put.mockImplementation(async () => {
      api.get.mockResolvedValue({ data: novo }); // the settle refetch must see what the server now holds
      return { data: novo };
    });
    wrap(<ReengajamentoPadraoTab isAdmin />);
    const card = await screen.findByTestId("card-horario");
    expect(card.textContent).toContain("America/Sao_Paulo");
    expect((screen.getByLabelText("Abertura") as HTMLInputElement).value).toBe("08:00");
    const salvar = screen.getByText("Salvar horário").closest("button") as HTMLButtonElement;
    expect(salvar.disabled).toBe(true); // nothing changed yet
    fireEvent.change(screen.getByLabelText("Abertura"), { target: { value: "09:00" } });
    fireEvent.click(screen.getByLabelText("sábado"));
    fireEvent.click(screen.getByLabelText("domingo"));
    fireEvent.click(salvar);
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith(URL_PUT, { ...CFG, horario_abertura: "09:00", dias_atendimento: [1, 2, 3, 4, 5] }),
    );
    await waitFor(() => expect(screen.getByTestId("card-horas").textContent).toContain("das 9h às 20h · de segunda a sexta"));
  });

  it("recusa localmente abertura depois do fechamento, sem chamar a API", async () => {
    api.get.mockResolvedValue({ data: CFG });
    wrap(<ReengajamentoPadraoTab isAdmin />);
    await screen.findByTestId("card-horario");
    fireEvent.change(screen.getByLabelText("Abertura"), { target: { value: "21:00" } });
    fireEvent.click(screen.getByText("Salvar horário"));
    expect((await screen.findByTestId("horario-erro")).textContent).toContain("antes do fechamento");
    expect(api.put).not.toHaveBeenCalled();
  });

  it("mostra a recusa do servidor em vez de engolir", async () => {
    api.get.mockResolvedValue({ data: CFG });
    api.put.mockRejectedValue(erro422("horario_invalido", "O servidor recusou este horário."));
    wrap(<ReengajamentoPadraoTab isAdmin />);
    await screen.findByTestId("card-horario");
    fireEvent.change(screen.getByLabelText("Fechamento"), { target: { value: "21:00" } });
    fireEvent.click(screen.getByText("Salvar horário"));
    expect((await screen.findByTestId("horario-erro")).textContent).toContain("O servidor recusou este horário.");
  });

  it("é somente leitura para quem não é admin", async () => {
    api.get.mockResolvedValue({ data: CFG });
    wrap(<ReengajamentoPadraoTab isAdmin={false} />);
    await screen.findByTestId("card-horario");
    expect((screen.getByLabelText("Abertura") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("sábado") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Salvar horário").closest("button") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("Mensagem do primeiro contato dos portais", () => {
  it("sem texto próprio, a prévia diz que usa a mensagem inicial padrão", async () => {
    api.get.mockResolvedValue({ data: CFG });
    wrap(<ReengajamentoPadraoTab isAdmin />);
    await screen.findByTestId("card-portal");
    expect(screen.getByTestId("portal-previa").textContent).toContain("mensagem inicial padrão");
  });

  it("mostra a prévia com os marcadores preenchidos e salva", async () => {
    api.get.mockResolvedValue({ data: CFG });
    const texto = "Oi! Sou {agente}, assistente virtual (IA). Privacidade: {link}";
    api.put.mockResolvedValue({ data: { ...CFG, portal_primeiro_contato_texto: texto } });
    wrap(<ReengajamentoPadraoTab isAdmin />);
    await screen.findByTestId("card-portal");
    fireEvent.change(screen.getByLabelText("Mensagem do primeiro contato"), { target: { value: texto } });
    expect(screen.getByTestId("portal-previa").textContent).toContain("Sou Julia, assistente virtual (IA). Privacidade: https://");
    fireEvent.click(screen.getByText("Salvar mensagem"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith(URL_PUT, { ...CFG, portal_primeiro_contato_texto: texto }));
  });

  it("recusa um texto sem {link} (LGPD) sem chamar a API", async () => {
    api.get.mockResolvedValue({ data: CFG });
    wrap(<ReengajamentoPadraoTab isAdmin />);
    await screen.findByTestId("card-portal");
    fireEvent.change(screen.getByLabelText("Mensagem do primeiro contato"), { target: { value: "Oi, sou a Julia" } });
    fireEvent.click(screen.getByText("Salvar mensagem"));
    expect((await screen.findByTestId("portal-erro")).textContent).toContain("{link}");
    expect(api.put).not.toHaveBeenCalled();
  });

  it("mostra a recusa do servidor ao salvar o texto", async () => {
    api.get.mockResolvedValue({ data: CFG });
    api.put.mockRejectedValue(erro422("portal_texto_sem_link", "O servidor exige o link."));
    wrap(<ReengajamentoPadraoTab isAdmin />);
    await screen.findByTestId("card-portal");
    fireEvent.change(screen.getByLabelText("Mensagem do primeiro contato"), { target: { value: "Oi {link}" } });
    fireEvent.click(screen.getByText("Salvar mensagem"));
    expect((await screen.findByTestId("portal-erro")).textContent).toContain("O servidor exige o link.");
  });

  it("'usar a mensagem inicial padrão' limpa o texto salvo enviando vazio", async () => {
    const salvo = "Oi, assistente virtual (IA). {link}";
    api.get.mockResolvedValue({ data: { ...CFG, portal_primeiro_contato_texto: salvo } });
    api.put.mockResolvedValue({ data: CFG });
    wrap(<ReengajamentoPadraoTab isAdmin />);
    await screen.findByTestId("card-portal");
    expect((screen.getByLabelText("Mensagem do primeiro contato") as HTMLTextAreaElement).value).toBe(salvo);
    fireEvent.click(screen.getByText("Usar a mensagem inicial padrão"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith(URL_PUT, { ...CFG, portal_primeiro_contato_texto: "" }));
    await waitFor(() => expect((screen.getByLabelText("Mensagem do primeiro contato") as HTMLTextAreaElement).value).toBe(""));
  });

  it("o texto é somente leitura para quem não é admin", async () => {
    api.get.mockResolvedValue({ data: CFG });
    wrap(<ReengajamentoPadraoTab isAdmin={false} />);
    await screen.findByTestId("card-portal");
    expect((screen.getByLabelText("Mensagem do primeiro contato") as HTMLTextAreaElement).disabled).toBe(true);
  });
});
