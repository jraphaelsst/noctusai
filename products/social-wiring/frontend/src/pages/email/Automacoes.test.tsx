import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

import { EnrollmentPauseReason } from "./Automacoes";

const base = {
  id: "en-1", automation_id: "a1", contact_id: "c1", current_step_id: null,
  next_action_at: null, enrolled_at: "2026-10-10T00:00:00Z", completed_at: null,
};

describe("EnrollmentPauseReason (migration 243)", () => {
  afterEach(cleanup);

  it("shows the recorded reason on a paused enrollment", () => {
    render(<EnrollmentPauseReason enrollment={{ ...base, status: "paused", pause_reason: "webhook steps are not supported" }} />);
    expect(screen.getByTestId("enrollment-pause-reason-en-1").textContent).toBe("Pausada: webhook steps are not supported");
  });

  it("says so when a paused enrollment has no recorded reason (never silent)", () => {
    render(<EnrollmentPauseReason enrollment={{ ...base, status: "paused", pause_reason: null }} />);
    expect(screen.getByTestId("enrollment-pause-reason-en-1").textContent).toContain("motivo não registrado");
  });

  it("renders nothing for an active enrollment", () => {
    const { container } = render(<EnrollmentPauseReason enrollment={{ ...base, status: "active" }} />);
    expect(container.textContent).toBe("");
  });
});
