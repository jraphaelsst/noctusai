/** Julia ligada card: the switch cannot go ON unless the server says `pode_ligar`; OFF is always allowed; 409/503 map to the same sentences. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import { JuliaLigadaCard } from "./JuliaLigadaCard";
import { JULIA_ROTEAMENTO_KEY, type LinhaRoteamento } from "@/hooks/useJuliaRoteamento";

const L = (alimenta: boolean): LinhaRoteamento => ({
  connection_id: "c1", label: "Linha 1", alimenta, alimenta_desde: null, destino_handoff_user_id: null,
});

function renderCard(props: Partial<React.ComponentProps<typeof JuliaLigadaCard>> & { alimenta: boolean }) {
  const { alimenta, ...rest } = props;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(JULIA_ROTEAMENTO_KEY, { linhas: [L(alimenta)], destino_handoff_padrao: { tipo: "owner", user_id: null } });
  const ui = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <JuliaLigadaCard linhas={[L(alimenta)]} status={null} isAdmin {...rest} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { qc, ...ui };
}
const sw = () => screen.getByRole("switch") as HTMLButtonElement;
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("JuliaLigadaCard bloqueio de ligar", () => {
  it.each([
    ["julia_nao_publicada", "A Julia ainda não foi liberada para esta empresa pela NoctusAI. Assim que for, você poderá ligá-la aqui."],
    ["julia_desligada_no_agents", "A Julia está pausada pela NoctusAI no momento. Você poderá ligá-la aqui quando ela for reativada."],
    ["agents_indisponivel", "Não foi possível confirmar agora se a Julia pode ser ligada. Tente novamente em instantes."],
  ] as const)("off line + %s: switch disabled with the reason (never naming the agents app)", (motivo, texto) => {
    renderCard({ alimenta: false, podeLigar: false, motivoBloqueio: motivo });
    expect(sw().disabled).toBe(true);
    expect(screen.getByTestId("linha-bloqueio").textContent).toContain(texto);
    expect(sw().getAttribute("aria-describedby")).toBe(screen.getByTestId("linha-bloqueio").id);
    expect(screen.queryByRole("link", { name: /agentes/i })).toBeNull();
  });

  it("an already-ON line can always be turned OFF, even when pode_ligar is false", async () => {
    api.put.mockResolvedValue({ data: {} });
    const { qc } = renderCard({ alimenta: true, podeLigar: false, motivoBloqueio: "julia_desligada_no_agents" });
    expect(sw().disabled).toBe(false);
    expect(screen.queryByTestId("linha-bloqueio")).toBeNull();
    fireEvent.click(sw());
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/julia/roteamento/linhas/c1", { alimenta: false }));
    // cache write: the switch moved in the cache without waiting for a refetch
    await waitFor(() => expect((qc.getQueryData(JULIA_ROTEAMENTO_KEY) as { linhas: LinhaRoteamento[] }).linhas[0].alimenta).toBe(false));
  });

  it("pode_ligar true: switch is enabled and turning ON sends alimenta:true", async () => {
    api.put.mockResolvedValue({ data: {} });
    renderCard({ alimenta: false, podeLigar: true, motivoBloqueio: null });
    expect(sw().disabled).toBe(false);
    expect(screen.queryByTestId("linha-bloqueio")).toBeNull();
    fireEvent.click(sw());
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/julia/roteamento/linhas/c1", { alimenta: true }));
  });

  it.each([
    [409, "julia_nao_publicada", "A Julia ainda não foi liberada para esta empresa pela NoctusAI. Assim que for, você poderá ligá-la aqui."],
    [409, "julia_desligada_no_agents", "A Julia está pausada pela NoctusAI no momento. Você poderá ligá-la aqui quando ela for reativada."],
    [503, "agents_indisponivel", "Não foi possível confirmar agora se a Julia pode ser ligada. Tente novamente em instantes."],
  ])("maps %s %s on the PUT to its sentence and rolls the switch back", async (status, code, texto) => {
    api.put.mockRejectedValue(Object.assign(new Error("x"), { status, body: { error: { code, message: "ignored" } } }));
    const { qc } = renderCard({ alimenta: false });
    fireEvent.click(sw());
    expect((await screen.findByTestId("linha-erro")).textContent).toBe(texto);
    expect((qc.getQueryData(JULIA_ROTEAMENTO_KEY) as { linhas: LinhaRoteamento[] }).linhas[0].alimenta).toBe(false);
  });

  it("links to Proteção under the switch", () => {
    renderCard({ alimenta: false });
    expect(screen.getByRole("link", { name: "Bloquear números (o modo de avaliação é configurado na página da Julia no agents)" }).getAttribute("href")).toBe("/julia/protecao");
  });
});
