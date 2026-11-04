/** Julia v3 UI: kill banner, relatórios destino, catálogo fonte, lead card chips + report. `@/lib/api` is the seam. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@/hooks/useTeam", () => ({ useTeamMembers: () => ({ data: [{ id: "u1", nome: "Raphael", email: "r@x.test" }], isError: false }) }));
vi.mock("@noctusai/lib", () => ({ env: { CORE_URL: "https://core.example.test/" } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { JuliaLigadaBanner } from "./JuliaLigadaCard";
import { RelatoriosCard, CatalogoCard } from "./RelatoriosCatalogoCards";
import { ImoveisOferecidosChips, RelatorioLeadSection } from "./RelatorioLeadSection";
import { imoveisOferecidos } from "@/hooks/useJuliaRelatorioLead";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}
const st = { agent_key: "julia", nome: "Julia", ativo: true, versao_ativa: 1, provider: null, model: null, llm_configurado: true };

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("Julia v3", () => {
  it("banner: platform kill / modo != ligado / silent when on", () => {
    const { rerender } = render(<JuliaLigadaBanner status={{ ...st, desligado_plataforma: true }} />);
    expect(screen.getByText("A Julia está desligada pela plataforma.")).toBeTruthy();
    rerender(<JuliaLigadaBanner status={{ ...st, modo: "pausado" }} />);
    expect(screen.getByTestId("julia-banner-desligada")).toBeTruthy();
    rerender(<JuliaLigadaBanner status={{ ...st, modo: "ligado" }} />);
    expect(screen.queryByTestId("julia-banner-desligada")).toBeNull();
  });

  it("picks a member, shows the noc WhatsApp, and surfaces a refusal", async () => {
    api.get.mockResolvedValue({ data: { modo: "usuario", usuario_id: null, usuario_nome: null, telefone_resolvido: null } });
    api.put.mockRejectedValue(Object.assign(new Error("x"), { status: 422, body: { error: { code: "x", message: "Recusado no servidor" } } }));
    wrap(<RelatoriosCard isAdmin />);
    fireEvent.change(await screen.findByLabelText("Quem recebe os relatórios"), { target: { value: "u1" } });
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/julia/relatorio-destino", { modo: "usuario", usuario_id: "u1" }));
    expect(await screen.findByTestId("relatorios-salvar-erro")).toBeTruthy();
  });

  it("no WhatsApp: amber notice with link to core settings; with WhatsApp: shows it", async () => {
    api.get.mockResolvedValue({ data: { modo: "usuario", usuario_id: "u1", usuario_nome: "Raphael", telefone_resolvido: null } });
    wrap(<RelatoriosCard isAdmin />);
    const aviso = await screen.findByTestId("rel-sem-whatsapp");
    expect(aviso.textContent).toContain("Sem WhatsApp — cadastre no noc");
    expect(aviso.querySelector("a")?.getAttribute("href")).toBe("https://core.example.test/settings");
    cleanup();
    api.get.mockResolvedValue({ data: { modo: "usuario", usuario_id: "u1", usuario_nome: "Raphael", telefone_resolvido: "+5511987654321" } });
    wrap(<RelatoriosCard isAdmin={false} />);
    expect((await screen.findByTestId("rel-telefone")).textContent).toContain("+5511987654321");
    expect((screen.getByLabelText("Quem recebe os relatórios") as HTMLSelectElement).disabled).toBe(true);
  });

  it("catalog source writes the chosen fonte", async () => {
    api.get.mockResolvedValue({ data: { fonte: "espelho" } });
    api.put.mockResolvedValue({ data: { fonte: "vista" } });
    wrap(<CatalogoCard isAdmin />);
    fireEvent.click(await screen.findByLabelText("Vista (ao vivo)"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/julia/catalogo-fonte", { fonte: "vista" }));
  });

  it("adapter handles codes only and codes + links", () => {
    expect(imoveisOferecidos({ imoveis_oferecidos: ["A1"] })).toEqual([{ codigo: "A1", link: null }]);
    expect(
      imoveisOferecidos({ imoveis_oferecidos: ["A1"], imoveis_oferecidos_links: [{ codigo: "A1", link: "https://x/imovel/A1" }] }),
    ).toEqual([{ codigo: "A1", link: "https://x/imovel/A1" }]);
  });

  it("lead card: chips open in a new tab; latest report + older collapsed", async () => {
    api.get.mockResolvedValue({
      data: [
        { id: "2", tipo: "handoff", texto: "linha1\nlinha2", dados: null, destino_e164: "+5511", envio_status: "enviado", envio_erro: null, created_at: "2026-11-03T10:00:00Z" },
        { id: "1", tipo: "alerta", texto: "antigo", dados: null, destino_e164: null, envio_status: "falhou", envio_erro: "x", created_at: "2026-11-02T10:00:00Z" },
      ],
    });
    wrap(
      <>
        <ImoveisOferecidosChips payload={{ imoveis_oferecidos_links: [{ codigo: "A1", link: "https://x/imovel/A1" }], imoveis_oferecidos: ["A1"] }} />
        <RelatorioLeadSection contatoId="c1" />
      </>,
    );
    const chip = screen.getByTestId("imovel-chip-A1");
    expect(chip.getAttribute("target")).toBe("_blank");
    expect((await screen.findByTestId("relatorio-ultimo")).textContent).toContain("Enviado");
    expect(screen.getByTestId("relatorios-anteriores")).toBeTruthy();
  });

  it("lead card shows an error, never silence", async () => {
    api.get.mockRejectedValue(new Error("boom"));
    wrap(<RelatorioLeadSection contatoId="c1" />);
    expect(await screen.findByTestId("relatorio-erro")).toBeTruthy();
  });
});
