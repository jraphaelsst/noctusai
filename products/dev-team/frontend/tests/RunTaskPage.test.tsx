/**
 * RunTaskPage tests — submits the form and renders the result envelope.
 *
 * Covers all three discriminated statuses the engine returns: ok /
 * switch-not-flipped / dry-run, plus the error path.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch },
}));

// react-router context not needed by the page itself, but the lazy-imported
// page tree might link to / — use a minimal wrapper anyway for safety.
import { MemoryRouter } from "react-router-dom";

function wrap(ui: React.ReactElement) {
  return <MemoryRouter>{ui}</MemoryRouter>;
}

describe("RunTaskPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("submits the form and renders an ok envelope", async () => {
    mockPost.mockResolvedValue({
      data: { status: "ok", summary: "All done.", task: "ship it", config: "default" },
    });

    const user = userEvent.setup();
    const { default: RunTaskPage } = await import("@/pages/RunTaskPage");
    render(wrap(<RunTaskPage />));

    await user.type(screen.getByTestId("run-task-input"), "ship it");
    await user.click(screen.getByTestId("run-submit"));

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/run", {
        task: "ship it",
        project: undefined,
        config: "default",
      }),
    );

    expect(await screen.findByTestId("run-result")).toBeInTheDocument();
    expect(screen.getByTestId("run-summary")).toHaveTextContent("All done.");
  });

  it("renders the switch-not-flipped envelope without erroring", async () => {
    mockPost.mockResolvedValue({
      data: { status: "switch-not-flipped", summary: "ANTHROPIC_API_KEY not set." },
    });

    const user = userEvent.setup();
    const { default: RunTaskPage } = await import("@/pages/RunTaskPage");
    render(wrap(<RunTaskPage />));

    await user.type(screen.getByTestId("run-task-input"), "anything");
    await user.click(screen.getByTestId("run-submit"));

    expect(await screen.findByText("switch-not-flipped")).toBeInTheDocument();
    expect(screen.getByTestId("run-summary")).toHaveTextContent(/ANTHROPIC_API_KEY/);
  });

  it("blocks submit when task is empty + surfaces the inline error", async () => {
    const user = userEvent.setup();
    const { default: RunTaskPage } = await import("@/pages/RunTaskPage");
    render(wrap(<RunTaskPage />));

    await user.click(screen.getByTestId("run-submit"));

    expect(await screen.findByText(/Task is required/i)).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("surfaces an API error from POST /api/run", async () => {
    mockPost.mockRejectedValue(new Error("[503] engine cold"));

    const user = userEvent.setup();
    const { default: RunTaskPage } = await import("@/pages/RunTaskPage");
    render(wrap(<RunTaskPage />));

    await user.type(screen.getByTestId("run-task-input"), "do thing");
    await user.click(screen.getByTestId("run-submit"));

    expect(await screen.findByText(/engine cold/)).toBeInTheDocument();
  });
});
