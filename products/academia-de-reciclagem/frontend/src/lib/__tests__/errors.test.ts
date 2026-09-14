/**
 * `errorMessage()` — verifies the contract §B.0 status-taxonomy PT-BR text
 * survives from a backend `{detail, code}` body through `ApiError` to the
 * UI-facing string, and that the generic per-status fallback only kicks in
 * when the backend did not send a usable `detail`.
 */
import { describe, expect, it } from "vitest";
import { ApiError } from "@noctusai/lib";
import { errorMessage } from "@/lib/errors";

describe("errorMessage", () => {
  it("prefers the backend's own PT-BR detail text (contract §B.0 401 row)", () => {
    const err = new ApiError(401, "Sessão expirada — entre novamente.");
    expect(errorMessage(err)).toBe("Sessão expirada — entre novamente.");
  });

  it("prefers the backend's own PT-BR detail text (contract §B.0 403 assertion_invalid row)", () => {
    const err = new ApiError(403, "Aprovação inválida — peça de novo.");
    expect(errorMessage(err)).toBe("Aprovação inválida — peça de novo.");
  });

  it("prefers the backend's own PT-BR detail text (contract §B.0 409 conflict row)", () => {
    const err = new ApiError(409, "O slug já existe.");
    expect(errorMessage(err)).toBe("O slug já existe.");
  });

  it("strips the ApiError status prefix", () => {
    const err = new ApiError(404, "Não encontrado.");
    expect(err.message).toBe("[404] Não encontrado.");
    expect(errorMessage(err)).toBe("Não encontrado.");
  });

  it("falls back to the status table when the client-side generic placeholder leaked through", () => {
    const err = new ApiError(404, "Erro HTTP 404");
    expect(errorMessage(err)).toBe("Não encontrado.");
  });

  it("falls back to a generic message for a transport-level failure (status null)", () => {
    const err = new ApiError(null, "Servidor indisponível (/api/kb). Verifique se o backend esta rodando.");
    expect(errorMessage(err)).toBe(
      "Servidor indisponível (/api/kb). Verifique se o backend esta rodando.",
    );
  });

  it("handles a plain Error", () => {
    expect(errorMessage(new Error("boom"))).toBe("boom");
  });

  it("handles a non-Error value", () => {
    expect(errorMessage("nope")).toBe("Ocorreu um erro. Tente novamente.");
  });
});
