/** Roteiro Avançado + Estruturas: formato selector only without Estruturas; request fields; coded refusals rendered. */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(cleanup);

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const m = vi.hoisted(() => ({ criar: vi.fn() }));
vi.mock("@/hooks/useCerebro", () => ({ useCerebroBrains: () => ({ data: [], showSkeleton: false }) }));
vi.mock("@/hooks/geracao/useRoteiros", () => ({
  useCriarRoteiro: () => ({ mutateAsync: m.criar, isPending: false }),
  useResponderPerguntas: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useGerarRoteiro: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRoteiro: () => ({ data: undefined, showSkeleton: false, isError: false, refetch: vi.fn() }),
  useSalvarRoteiro: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useFeedbackRoteiro: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/hooks/geracao/useEsteira", () => ({
  useCriarPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useVincularRoteiro: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/components/geracao/biblioteca/VideoPicker", () => ({ VideoPicker: () => null }));
vi.mock("@/components/geracao/estruturas/EstruturaPicker", () => ({
  EstruturaPicker: (p: { onChange: (v: unknown[]) => void }) => (
    <button
      type="button"
      onClick={() => p.onChange([{ id: "e1", codigo: 1, formula_headline: "F", formato: "carrossel", perfil: { id: "p1", handle: "ana", nome: null, foto_url: null } }])}
    >
      escolher estrutura
    </button>
  ),
}));

import { toast } from "sonner";

import { RoteiroAvancadoModal } from "./RoteiroAvancadoModal";

const abrir = () => render(<RoteiroAvancadoModal open onOpenChange={vi.fn()} marcaId="m1" headlineInicial={{ id: "h1", texto: "3 alimentos" }} />);
const grupoFormato = () => screen.getByRole("radiogroup", { name: "Formato" });

beforeEach(() => {
  vi.clearAllMocks();
  m.criar.mockResolvedValue({ id: "r1" });
});

describe("Roteiro Avançado: formato", () => {
  it("enabled and Reels by default while no Estrutura is picked", () => {
    abrir();
    const reels = within(grupoFormato()).getByRole("radio", { name: "Reels" });
    expect(reels).toHaveAttribute("aria-checked", "true");
    expect(within(grupoFormato()).getByRole("radio", { name: "Carrossel" })).not.toBeDisabled();
  });

  it("the default (Reels) request carries no formato and no estrutura_ids", async () => {
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    await waitFor(() => expect(m.criar).toHaveBeenCalled());
    const body = m.criar.mock.calls[0]![0];
    expect("formato" in body).toBe(false);
    expect("estrutura_ids" in body).toBe(false);
  });

  it("another formato is sent as formato", async () => {
    abrir();
    fireEvent.click(within(grupoFormato()).getByRole("radio", { name: "Stories" }));
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    await waitFor(() => expect(m.criar.mock.calls[0]![0].formato).toBe("stories"));
  });

  it("with an Estrutura the selector is disabled, shows the Estrutura's formato, and estrutura_ids is sent (no formato)", async () => {
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "escolher estrutura" }));
    const car = within(grupoFormato()).getByRole("radio", { name: "Carrossel" });
    expect(car).toHaveAttribute("aria-checked", "true");
    expect(within(grupoFormato()).getByRole("radio", { name: "Reels" })).toBeDisabled();
    expect(screen.getByTestId("formato-da-estrutura").textContent).toContain("Carrossel");
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    await waitFor(() => expect(m.criar).toHaveBeenCalled());
    const body = m.criar.mock.calls[0]![0];
    expect(body.estrutura_ids).toEqual(["e1"]);
    expect("formato" in body).toBe(false);
  });

  it("renders a coded refusal inline and toasts it", async () => {
    m.criar.mockRejectedValue(Object.assign(new Error("[422] x"), { code: "formatos_misturados", status: 422 }));
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    const aviso = await screen.findByTestId("erro-criar-roteiro");
    expect(aviso.textContent).toContain("As estruturas escolhidas têm formatos diferentes");
    expect(toast.error).toHaveBeenCalled();
  });

  it("an ambiguous profile in the instructions offers its candidates; picking one writes @handle", async () => {
    m.criar.mockRejectedValue(
      Object.assign(new Error("[422] x"), { code: "perfil_ambiguo", status: 422, body: { candidatos: [{ perfil_id: "p2", handle: "ana.b", nome: "Ana B" }] } }),
    );
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    fireEvent.click(await screen.findByRole("button", { name: /@ana\.b/ }));
    expect((screen.getByLabelText("Instruções") as HTMLTextAreaElement).value).toContain("@ana.b");
  });
});
