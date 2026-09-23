/**
 * The esteira's client-side move rules (roadmap R3) — mirrored from
 * `esteira_quadro.mover_tarefa` so the board refuses a skip and asks for a
 * reason BEFORE a request the server would reject.
 */
import { describe, expect, it } from "vitest";

import { formatarMinutos, formatarPrazo, prazoVencido } from "./formatos";
import { decidirMovimento, MENSAGEM_UM_PASSO, PAPEL_APROVACAO_CLIENTE } from "./moveRules";

const stage = (label: string, papel: string | null = null) => ({ label, papel });

describe("decidirMovimento", () => {
  it("lets a card move forward exactly one stage", () => {
    expect(
      decidirMovimento({
        direction: "forward",
        stepDistance: 1,
        fromStage: stage("Roteiro"),
        toStage: stage("Design"),
      }),
    ).toEqual({ tipo: "seguir" });
  });

  it("cancels a forward skip with the one-step message", () => {
    expect(
      decidirMovimento({
        direction: "forward",
        stepDistance: 2,
        fromStage: stage("Roteiro"),
        toStage: stage("Revisão"),
      }),
    ).toEqual({ tipo: "cancelar", mensagem: MENSAGEM_UM_PASSO });
  });

  it("lets a card be reordered inside its own column without a reason", () => {
    expect(
      decidirMovimento({
        direction: "same",
        stepDistance: 0,
        fromStage: stage("Roteiro"),
        toStage: stage("Roteiro"),
      }),
    ).toEqual({ tipo: "seguir" });
  });

  it("asks for a reason on any backward move, of any distance", () => {
    const decisao = decidirMovimento({
      direction: "backward",
      stepDistance: 3,
      fromStage: stage("Revisão interna"),
      toStage: stage("Aguardando roteiro"),
    });
    expect(decisao).toEqual({
      tipo: "motivo",
      refacao: false,
      titulo: "Devolver para Aguardando roteiro?",
    });
  });

  it("labels leaving the approval stage backwards as a Refação, keyed on the role", () => {
    const decisao = decidirMovimento({
      direction: "backward",
      stepDistance: 1,
      // A renamed approval stage is still the approval stage.
      fromStage: stage("Com o cliente", PAPEL_APROVACAO_CLIENTE),
      toStage: stage("Revisão interna"),
    });
    expect(decisao).toMatchObject({ tipo: "motivo", refacao: true });
    expect(decisao.tipo === "motivo" && decisao.titulo).toMatch(/^Refação/);
  });

  it("does not call it a refação when the label merely looks like approval", () => {
    const decisao = decidirMovimento({
      direction: "backward",
      stepDistance: 1,
      fromStage: stage("Aprovação do cliente", null),
      toStage: stage("Revisão interna"),
    });
    expect(decisao).toMatchObject({ tipo: "motivo", refacao: false });
  });
});


describe("formatos", () => {
  it("flags a prazo before today (local date) as overdue, today is not", () => {
    const hoje = new Date(2026, 8, 23, 22, 0);
    expect(prazoVencido("2026-09-22", hoje)).toBe(true);
    expect(prazoVencido("2026-09-23", hoje)).toBe(false);
    expect(prazoVencido(null, hoje)).toBe(false);
  });

  it("formats prazo and minutes for a phone-width card", () => {
    expect(formatarPrazo("2026-09-23")).toBe("23/09/26");
    expect(formatarMinutos(65)).toBe("1h05");
    expect(formatarMinutos(40)).toBe("40 min");
  });
});
