/**
 * `errorMessage()` — verifies the contract §B.0 status-taxonomy PT-BR text
 * is resolved from `err.code` (the flat `{detail, code}` body, per the
 * seed `ApiError.code` getter — `seed/lib/frontend/src/api.ts`), with the
 * two 403 sub-codes (`scope_missing` vs `assertion_invalid`) and the two
 * 409 sub-codes (`assertion_used` vs `conflict`) now distinguishable even
 * though they share an HTTP status.
 */
import { describe, expect, it } from "vitest";
import { ApiError } from "@noctusai/lib";
import { errorMessage } from "@/lib/errors";

/** Builds an `ApiError` the way the seed `ApiClient` does for a flat
 * `{detail, code}` error body. */
function flatError(status: number, detail: string, code: string): ApiError {
  return new ApiError(status, detail, { detail, code });
}

describe("errorMessage — code-specific overrides (contract §B.0)", () => {
  it("403 scope_missing → contract copy, distinguishable from assertion_invalid", () => {
    const err = flatError(403, "Missing scope(s): academia:kb:write", "scope_missing");
    expect(errorMessage(err)).toBe("Sem permissão para esta ação.");
  });

  it("403 assertion_invalid → contract copy, distinguishable from scope_missing", () => {
    const err = flatError(403, "Aprovação inválida — peça de novo.", "assertion_invalid");
    expect(errorMessage(err)).toBe("Aprovação inválida — peça de novo.");
  });

  it("403 role_missing (seed's English `detail`) gets the same copy as scope_missing", () => {
    const err = flatError(403, "Insufficient role", "role_missing");
    expect(errorMessage(err)).toBe("Sem permissão para esta ação.");
  });

  it("409 assertion_used → contract copy, distinguishable from conflict", () => {
    const err = flatError(409, "Esta aprovação já foi usada.", "assertion_used");
    expect(errorMessage(err)).toBe("Esta aprovação já foi usada.");
  });

  it("409 conflict → the endpoint's own specific PT-BR text, not the generic fallback", () => {
    const err = flatError(409, "O slug já existe.", "conflict");
    expect(errorMessage(err)).toBe("O slug já existe.");
  });
});

describe("errorMessage — unmapped codes pass the backend's own detail through", () => {
  it("not_found (404) passes the backend's own PT-BR text through unchanged", () => {
    const err = flatError(404, "Não encontrado.", "not_found");
    expect(errorMessage(err)).toBe("Não encontrado.");
  });

  it("approver_not_allowed (403, §D.8) passes the backend's own PT-BR text through unchanged", () => {
    const err = flatError(
      403,
      "Quem aprovou não tem permissão para esta ação.",
      "approver_not_allowed",
    );
    expect(errorMessage(err)).toBe("Quem aprovou não tem permissão para esta ação.");
  });

  it("product_forbidden (403, §B.6) passes the backend's own PT-BR text through unchanged", () => {
    const err = flatError(
      403,
      "Tokens de produto não podem importar — apenas administradores humanos.",
      "product_forbidden",
    );
    expect(errorMessage(err)).toBe(
      "Tokens de produto não podem importar — apenas administradores humanos.",
    );
  });

  it("invalid (422) passes the endpoint's own dynamic PT-BR text through unchanged", () => {
    const err = flatError(422, "Dado inválido.", "invalid");
    expect(errorMessage(err)).toBe("Dado inválido.");
  });
});

describe("errorMessage — status fallbacks (no usable code)", () => {
  it("401 falls back to the status table when there is no code", () => {
    const err = new ApiError(401, "Sessão expirada — entre novamente.");
    expect(errorMessage(err)).toBe("Sessão expirada — entre novamente.");
  });

  it("strips the ApiError status prefix before matching the generic placeholder", () => {
    const err = new ApiError(404, "Não encontrado.");
    expect(err.message).toBe("[404] Não encontrado.");
    expect(errorMessage(err)).toBe("Não encontrado.");
  });

  it("falls back to the status table when the client-side generic placeholder leaked through", () => {
    const err = new ApiError(404, "Erro HTTP 404");
    expect(errorMessage(err)).toBe("Não encontrado.");
  });

  it("falls back to a generic message for a transport-level failure (status null)", () => {
    const err = new ApiError(
      null,
      "Servidor indisponível (/api/kb). Verifique se o backend esta rodando.",
    );
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
