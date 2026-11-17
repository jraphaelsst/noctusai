/** Card "Origem" section: formato for all four, the caption PATCH, loading/error states. */
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(() => rtl.cleanup());
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const m = vi.hoisted(() => ({ origem: vi.fn(), atualizar: vi.fn() }));
vi.mock("@/hooks/geracao/useHeadlinesRoteiros", () => ({ useOrigemDoCard: () => m.origem() }));
vi.mock("@/hooks/geracao/useEsteira", () => ({ useAtualizarPost: () => ({ mutate: m.atualizar, isPending: false }) }));

import { EstruturasSecao } from "./EstruturasSecao";
import { origemCard } from "@/test/hrFixtures";
import type { PostDetalhe } from "@/types/esteira";

const post = { id: "post1" } as PostDetalhe;
const base = { isRefreshing: false, isError: false, error: null, showSkeleton: false };
const renderIt = () => rtl.render(<MemoryRouter><EstruturasSecao post={post} /></MemoryRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  m.origem.mockReturnValue({ ...base, data: origemCard() });
});

describe("EstruturasSecao", () => {
  it.each([
    ["reels", "Reels"],
    ["carrossel", "Carrossel"],
    ["stories", "Stories"],
    ["post", "Post"],
  ] as const)("shows formato %s", (formato, rotulo) => {
    m.origem.mockReturnValue({ ...base, data: origemCard({ formato }) });
    renderIt();
    expect(rtl.screen.getByTestId("origem-formato").textContent).toBe(rotulo);
  });

  it("shows headline, Estrutura + profile, duração and ordem do CTA", () => {
    renderIt();
    expect(rtl.screen.getByText("Headline de teste")).toBeTruthy();
    expect(rtl.screen.getByText(/@criador\.exemplo/)).toBeTruthy();
    expect(rtl.screen.getByText(/2 min · CTA: CTA no final/)).toBeTruthy();
    expect(rtl.screen.getByText("Escrita pela IA")).toBeTruthy();
  });

  it("saves an edited caption through the post PATCH", async () => {
    renderIt();
    const campo = rtl.screen.getByLabelText("Legenda");
    await userEvent.type(campo, " nova");
    expect(rtl.screen.getByText("Alterações não salvas")).toBeTruthy();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Salvar legenda" }));
    expect(m.atualizar).toHaveBeenCalledWith({ id: "post1", patch: { legenda: "Legenda IA nova" } }, expect.any(Object));
  });

  it("skeleton while loading, coded message on failure", () => {
    m.origem.mockReturnValue({ ...base, data: undefined, showSkeleton: true });
    renderIt();
    expect(rtl.screen.getByTestId("origem-loading")).toBeTruthy();
    rtl.cleanup();
    m.origem.mockReturnValue({ ...base, data: undefined, isError: true, error: Object.assign(new Error("x"), { status: 404 }) });
    renderIt();
    expect(rtl.screen.getByRole("alert").textContent).toContain("Não encontramos este item");
  });
});
