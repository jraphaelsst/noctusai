import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { buildTriggerConfig, subjectLabel, TriggerConfigFields } from "@/components/TriggerConfigFields";

const v = { keyword: "", stageId: "", leadStatus: "" };

describe("buildTriggerConfig", () => {
  it("keyword is required", () => {
    expect(buildTriggerConfig("keyword_received", {}, v).error).toBeTruthy();
    expect(buildTriggerConfig("keyword_received", {}, { ...v, keyword: " oi " }).config).toEqual({ keyword: "oi" });
  });
  it("stage/status are optional and unknown keys are preserved", () => {
    expect(buildTriggerConfig("pipeline_stage_entered", { x: 1, stage_id: "old" }, v).config).toEqual({ x: 1 });
    expect(buildTriggerConfig("pipeline_stage_entered", { x: 1 }, { ...v, stageId: "s" }).config).toEqual({ x: 1, stage_id: "s" });
    expect(buildTriggerConfig("lead_status_changed", {}, { ...v, leadStatus: "won" }).config).toEqual({ status: "won" });
  });
  it("drops stale managed keys when the trigger changes", () => {
    expect(buildTriggerConfig("manual", { keyword: "a" }, v).config).toEqual({});
  });
});

describe("subjectLabel", () => {
  const name = (id: string) => (id === "l1" ? "Maria" : undefined);
  it("resolves lead names, falls back for others", () => {
    expect(subjectLabel({ lead_id: "l1" }, name)).toBe("Maria");
    expect(subjectLabel({ lead_id: null, subject_type: "task", subject_id: "abcdef123456" }, name)).toBe("Tarefa #abcdef12");
    expect(subjectLabel({ lead_id: null, subject_type: "lead" }, name)).toMatch(/indisponível/);
  });
});

describe("TriggerConfigFields", () => {
  const base = { keyword: "", onKeyword: () => {}, stageId: "", onStageId: () => {}, stages: [{ id: "s", name: "Proposta" }], leadStatus: "", onLeadStatus: () => {} };
  it("renders per-trigger fields", () => {
    const { rerender } = render(<TriggerConfigFields {...base} triggerType="keyword_received" />);
    expect(screen.getByLabelText(/Palavra-chave/)).toBeInTheDocument();
    rerender(<TriggerConfigFields {...base} triggerType="pipeline_stage_entered" />);
    expect(screen.getByRole("option", { name: "Proposta" })).toBeInTheDocument();
    rerender(<TriggerConfigFields {...base} triggerType="meeting_created" />);
    expect(screen.getByTestId("aut-meeting-note")).toBeInTheDocument();
  });
});
