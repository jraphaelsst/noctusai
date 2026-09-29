/**
 * LGPD consent-refusal state for the negócio card's Assistente IA panel.
 *
 * `POST /api/comercial/negocios/{id}/assistente` is gated by
 * `igig.assistente_negocio` (`app/services/ai_consent_features.py`,
 * `default_granted=False`). Without consent the backend answers HTTP 412
 * `{error: {code: "AI_CONSENT_REQUIRED", ...}}` — the panel must show a
 * clear pt-BR explanation + a link to `/settings/ai`, never a generic
 * error string.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { ApiError } from "@noctusai/lib";

const { useAssistenteNegocioMock } = vi.hoisted(() => ({
  useAssistenteNegocioMock: vi.fn(),
}));
vi.mock("@/hooks/useComercial", () => ({
  useAssistenteNegocio: useAssistenteNegocioMock,
}));

import { AssistenteSubpage } from "../NegocioCardDialog";

afterEach(cleanup);

function renderSubpage() {
  render(
    <MemoryRouter>
      <AssistenteSubpage negocioId="n1" />
    </MemoryRouter>,
  );
}

describe("AssistenteSubpage — LGPD consent gate", () => {
  it("shows a pt-BR explanation and a link to /settings/ai when consent is required", () => {
    const consentError = new ApiError(
      412,
      "Consentimento necessário para usar este recurso de IA (Assistente IA do negócio).",
      { error: { code: "AI_CONSENT_REQUIRED", message: "Consentimento necessário." } },
    );
    useAssistenteNegocioMock.mockReturnValue({
      isPending: false,
      isError: true,
      error: consentError,
      data: undefined,
      variables: undefined,
      mutate: vi.fn(),
    });

    renderSubpage();

    expect(screen.getByTestId("assistente-consent-required")).toBeInTheDocument();
    expect(
      screen.getByText(/autorize o uso de IA com dados de clientes/i),
    ).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /ir para configurações de ia/i });
    expect(link).toHaveAttribute("href", "/settings/ai");
    // Never the generic fallback text for THIS error.
    expect(screen.queryByText("O assistente não respondeu.")).toBeNull();
  });

  it("shows the generic error message for a non-consent failure", () => {
    const providerError = new ApiError(
      502,
      "O provedor de IA não respondeu.",
      { detail: "O provedor de IA não respondeu.", code: "ia_indisponivel" },
    );
    useAssistenteNegocioMock.mockReturnValue({
      isPending: false,
      isError: true,
      error: providerError,
      data: undefined,
      variables: undefined,
      mutate: vi.fn(),
    });

    renderSubpage();

    expect(screen.queryByTestId("assistente-consent-required")).toBeNull();
    expect(screen.getByText("O provedor de IA não respondeu.")).toBeInTheDocument();
  });
});
