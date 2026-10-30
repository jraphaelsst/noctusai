/** StatusBadge, MetricaPill, labels and EditarHeadlineModal (hooks mocked). */
import React from "react";
import * as rtl from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatusBadge } from "./StatusBadge";
import { MetricaPill } from "./MetricaPill";
import { emAndamento, STATUS_ROTULO } from "./labels";
import { EditarHeadlineModal } from "./headlines/EditarHeadlineModal";
import { AvisoTamanhoHeadline, ContadorHeadline } from "./headlines/TamanhoHeadline";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const editar = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
vi.mock("@/hooks/geracao/useHeadlineMutations", () => ({ useEditarHeadline: () => editar }));

describe("labels", () => {
  it("rotula todos os status e marca só criando/processando como em andamento", () => {
    expect(STATUS_ROTULO.completo).toBe("Completo");
    expect(STATUS_ROTULO.falha).toBe("Falha");
    expect(emAndamento("criando")).toBe(true);
    expect(emAndamento("processando")).toBe(true);
    expect(emAndamento("perguntas")).toBe(false);
    expect(emAndamento("completo")).toBe(false);
  });
});

describe("StatusBadge", () => {
  it("mostra o rótulo pt-BR e expõe data-status", () => {
    rtl.render(<StatusBadge status="processando" />);
    expect(rtl.screen.getByText("Processando").getAttribute("data-status")).toBe("processando");
  });
});

describe("MetricaPill", () => {
  it("compacta views em pt-BR", () => {
    rtl.render(<MetricaPill viral={{ views: 12_500, likes: 3, score_viral: 2 }} />);
    expect(rtl.screen.getByText("12,5K views")).toBeTruthy();
  });
  it("cai para curtidas quando views não é servido", () => {
    rtl.render(<MetricaPill viral={{ views: null, likes: 900, score_viral: null }} />);
    expect(rtl.screen.getByText("900 curtidas")).toBeTruthy();
  });
  it("sem viral ou sem métrica mostra traço, nunca 0", () => {
    const a = rtl.render(<MetricaPill viral={null} />);
    expect(a.container.textContent).toBe("—");
    a.unmount();
    const b = rtl.render(<MetricaPill viral={{ views: null, likes: null, score_viral: null }} />);
    expect(b.container.textContent).toBe("—");
  });
});

describe("EditarHeadlineModal", () => {
  const headline = { id: "h1", texto: "Original", texto_original: "Original" };

  it("só habilita Salvar quando o texto muda e é válido; salva e fecha", async () => {
    editar.mutateAsync.mockResolvedValue({ id: "h1", texto: "Novo texto" });
    const onOpenChange = vi.fn();
    const onSalvo = vi.fn();
    rtl.render(<EditarHeadlineModal open onOpenChange={onOpenChange} headline={headline} onSalvo={onSalvo} />);
    const salvar = rtl.screen.getByRole("button", { name: "Salvar" }) as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);
    rtl.fireEvent.change(rtl.screen.getByLabelText("Headline"), { target: { value: "Novo texto" } });
    expect(salvar.disabled).toBe(false);
    rtl.fireEvent.click(salvar);
    await rtl.waitFor(() => expect(editar.mutateAsync).toHaveBeenCalledWith({ id: "h1", texto: "Novo texto" }));
    await rtl.waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(onSalvo).toHaveBeenCalledWith({ id: "h1", texto: "Novo texto" });
  });

  it("bloqueia texto vazio", () => {
    rtl.render(<EditarHeadlineModal open onOpenChange={vi.fn()} headline={headline} />);
    rtl.fireEvent.change(rtl.screen.getByLabelText("Headline"), { target: { value: "   " } });
    expect((rtl.screen.getByRole("button", { name: "Salvar" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("tamanho da headline — recomendação, nunca bloqueio (owner 2026-10-11)", () => {
  const base = { id: "h1", texto: "Original", texto_original: "Original", recomendado_max_texto: 120 };

  it("contador fica âmbar acima do recomendado e Salvar continua habilitado", () => {
    rtl.render(<EditarHeadlineModal open onOpenChange={vi.fn()} headline={base} />);
    const contador = rtl.screen.getByTestId("contador-headline");
    expect(contador.textContent).toBe("8/120 caracteres recomendados");
    expect(contador.getAttribute("data-estado")).toBe("ok");
    rtl.fireEvent.change(rtl.screen.getByLabelText("Headline"), { target: { value: "x".repeat(300) } });
    expect(contador.getAttribute("data-estado")).toBe("acima");
    expect(contador.className).toContain("text-warning-foreground");
    expect(contador.textContent).toContain("Acima do recomendado (300/120 caracteres)");
    expect((rtl.screen.getByRole("button", { name: "Salvar" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("salva uma headline de 300 caracteres", async () => {
    editar.mutateAsync.mockResolvedValue({ id: "h1", texto: "x".repeat(300) });
    rtl.render(<EditarHeadlineModal open onOpenChange={vi.fn()} headline={base} />);
    rtl.fireEvent.change(rtl.screen.getByLabelText("Headline"), { target: { value: "x".repeat(300) } });
    rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Salvar" }));
    await rtl.waitFor(() => expect(editar.mutateAsync).toHaveBeenCalledWith({ id: "h1", texto: "x".repeat(300) }));
  });

  it("só o teto de armazenamento (1000) bloqueia", () => {
    rtl.render(<EditarHeadlineModal open onOpenChange={vi.fn()} headline={base} />);
    rtl.fireEvent.change(rtl.screen.getByLabelText("Headline"), { target: { value: "x".repeat(1001) } });
    expect(rtl.screen.getByTestId("contador-headline").getAttribute("data-estado")).toBe("maximo");
    expect((rtl.screen.getByRole("button", { name: "Salvar" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("sem limiar conhecido conta só contra o teto", () => {
    rtl.render(<ContadorHeadline texto={"x".repeat(300)} />);
    const c = rtl.screen.getByTestId("contador-headline");
    expect(c.textContent).toBe("300/1000 caracteres");
    expect(c.getAttribute("data-estado")).toBe("ok");
  });

  it("aviso âmbar aparece só quando o backend marca acima_recomendado", () => {
    const longa = { texto: "y".repeat(150), acima_recomendado: true, recomendado_max_texto: 120 };
    const a = rtl.render(<AvisoTamanhoHeadline headline={longa} />);
    expect(rtl.screen.getByTestId("aviso-tamanho-headline").textContent).toBe("Acima do recomendado (150/120 caracteres)");
    a.unmount();
    rtl.render(<AvisoTamanhoHeadline headline={{ ...longa, texto: "curta", acima_recomendado: false }} />);
    expect(rtl.screen.queryByTestId("aviso-tamanho-headline")).toBeNull();
  });
});
