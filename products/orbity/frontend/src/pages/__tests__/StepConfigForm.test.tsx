import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { useState } from "react";
import {
  buildSendMessageConfig,
  buildWaitConfig,
  parseWaitConfig,
  SendMessageFields,
  WaitFields,
  TEMPLATE_VARIABLES,
  type WaitUnit,
} from "@/components/StepConfigForm";

describe("step config builders", () => {
  it("send_message requires a template", () => {
    expect(buildSendMessageConfig("   ").error).toBeTruthy();
    expect(buildSendMessageConfig("Oi {{nome}}").config).toEqual({ template: "Oi {{nome}}" });
  });
  it("send_message preserves extra keys", () => {
    expect(buildSendMessageConfig("x", { media_url: "u" }).config).toEqual({ media_url: "u", template: "x" });
  });
  it("wait converts to duration_minutes and validates", () => {
    expect(buildWaitConfig("2", "hours").config).toEqual({ duration_minutes: 120 });
    expect(buildWaitConfig("1", "days").config).toEqual({ duration_minutes: 1440 });
    expect(buildWaitConfig("0", "minutes").error).toBeTruthy();
    expect(buildWaitConfig("", "minutes").error).toBeTruthy();
  });
  it("parseWaitConfig picks the largest exact unit", () => {
    expect(parseWaitConfig({ duration_minutes: 2880 })).toEqual({ amount: "2", unit: "days" });
    expect(parseWaitConfig({ duration_minutes: 90 })).toEqual({ amount: "90", unit: "minutes" });
    expect(parseWaitConfig({ duration_minutes: 180 })).toEqual({ amount: "3", unit: "hours" });
    expect(parseWaitConfig(undefined)).toEqual({ amount: "60", unit: "minutes" });
  });
  it("variables are the engine's palette keys (pt-BR)", () => {
    const keys = TEMPLATE_VARIABLES.map((v) => v.key);
    expect(keys).toContain("nome");
    expect(keys).not.toContain("lead_name");
  });
});

describe("step config fields", () => {
  it("chip inserts the variable token into the template", () => {
    function Host() {
      const [t, setT] = useState("Oi ");
      return <SendMessageFields template={t} onChange={setT} />;
    }
    render(<Host />);
    fireEvent.click(screen.getByRole("button", { name: "{{nome}}" }));
    expect(screen.getByLabelText(/Mensagem/)).toHaveValue("Oi {{nome}}");
  });
  it("wait fields report amount and unit changes", () => {
    const calls: [string, WaitUnit][] = [];
    render(<WaitFields amount="5" unit="minutes" onChange={(a, u) => calls.push([a, u])} />);
    fireEvent.change(screen.getByLabelText(/Aguardar por/), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Unidade de tempo"), { target: { value: "hours" } });
    expect(calls).toEqual([["7", "minutes"], ["5", "hours"]]);
  });
});
