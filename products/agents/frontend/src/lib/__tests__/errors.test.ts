/**
 * errors.ts — PT-BR mapping tests (contract §E.2 error rows).
 *
 * Backend errors reach the client as the flat `{detail, code}` body (§0);
 * the seed `ApiClient` throws `ApiError(status, detail, body)` — `err.code`
 * reads the flat `code` field (`seed/lib/frontend/src/api.ts`). Tests build
 * `ApiError` with the real body shape rather than matching on `err.message`
 * text, since `errorMessage()` now branches on `err.code`.
 */
import { describe, expect, it } from "vitest";
import { ApiError, errorMessage } from "@/lib/errors";

/** Builds an `ApiError` the way the seed `ApiClient` does for a flat
 * `{detail, code}` error body. */
function flatError(status: number, detail: string, code: string): ApiError {
  return new ApiError(status, detail, { detail, code });
}

describe("errorMessage — code-specific overrides (contract §E.2)", () => {
  it("409 turn_in_progress → 'Julia ainda está respondendo a mensagem anterior.'", () => {
    const err = flatError(409, "Já existe um turno em andamento.", "turn_in_progress");
    expect(errorMessage(err)).toBe("Julia ainda está respondendo a mensagem anterior.");
  });

  it("409 agent_off → 'Julia está desligada — um administrador pode ligá-la em Agentes.'", () => {
    const err = flatError(409, "O agente Julia está desligado.", "agent_off");
    expect(errorMessage(err)).toBe(
      "Julia está desligada — um administrador pode ligá-la em Agentes.",
    );
  });

  it("502 upstream_failed → 'Não foi possível falar com o social-wiring.'", () => {
    const err = flatError(502, "Falha ao comunicar com o social-wiring.", "upstream_failed");
    expect(errorMessage(err)).toBe("Não foi possível falar com o social-wiring.");
  });

  it("409 not_configured → 'Configure a conexão do One Chat.'", () => {
    const err = flatError(
      409,
      "One Chat ainda não configurado (nenhuma conexão vinculada).",
      "not_configured",
    );
    expect(errorMessage(err)).toBe("Configure a conexão do One Chat.");
  });

  it("403 role_missing (seed's English `detail`) is overridden with PT-BR copy", () => {
    const err = flatError(403, "Insufficient role", "role_missing");
    expect(errorMessage(err)).toBe("Sem permissão para esta ação.");
  });

  it("403 user_required (seed's English `detail`) is overridden with PT-BR copy", () => {
    const err = flatError(403, "Restricted to human users", "user_required");
    expect(errorMessage(err)).toBe("Sem permissão para esta ação.");
  });

  it("already_decided passes the backend's own PT-BR text through unchanged (no override)", () => {
    const err = flatError(409, "Esta aprovação já foi decidida.", "already_decided");
    expect(errorMessage(err)).toBe("Esta aprovação já foi decidida.");
  });

  it("orphaned passes the backend's own PT-BR text through unchanged (no override)", () => {
    const err = flatError(
      409,
      "Não há um turno ativo aguardando esta aprovação.",
      "orphaned",
    );
    expect(errorMessage(err)).toBe("Não há um turno ativo aguardando esta aprovação.");
  });

  it("not_allowed (403) passes the backend's own PT-BR text through unchanged (no override)", () => {
    const err = flatError(403, "Você não pode decidir esta aprovação.", "not_allowed");
    expect(errorMessage(err)).toBe("Você não pode decidir esta aprovação.");
  });

  it("not_found (404) passes the backend's own per-entity PT-BR text through unchanged", () => {
    const err = flatError(404, "Conversa não encontrada.", "not_found");
    expect(errorMessage(err)).toBe("Conversa não encontrada.");
  });

  it("invalid_field (422) passes the backend's own dynamic PT-BR text through unchanged", () => {
    const err = flatError(422, "estado deve ser 'pendente'.", "invalid_field");
    expect(errorMessage(err)).toBe("estado deve ser 'pendente'.");
  });
});

describe("errorMessage — status fallbacks (no usable code)", () => {
  it("401 → session-expired message", () => {
    const err = new ApiError(401, "");
    expect(errorMessage(err)).toBe("Sessão expirada — entre novamente.");
  });

  it("429 → rate-limit message even without a contract-shaped body", () => {
    const err = new ApiError(429, "Erro HTTP 429");
    expect(errorMessage(err)).toBe(
      "Muitas mensagens em pouco tempo — aguarde um instante e tente novamente.",
    );
  });

  it("a nested {error:{code,message}} body's PT-BR message passes through unmapped codes", () => {
    // slowapi's real 429 shape (seed `app_factory.py` rate_limit_handler) —
    // nested, not flat, and RATE_LIMITED has no CODE_MESSAGES entry.
    const err = new ApiError(429, "Muitas requisições. Tente novamente em breve.", {
      error: { code: "RATE_LIMITED", message: "Muitas requisições. Tente novamente em breve." },
    });
    expect(errorMessage(err)).toBe("Muitas requisições. Tente novamente em breve.");
  });

  it("a transport failure (status null) falls back to the generic message", () => {
    const err = new ApiError(null, "Servidor indisponivel");
    expect(errorMessage(err)).toBe("Servidor indisponivel");
  });

  it("a plain Error (not ApiError) uses its own message", () => {
    expect(errorMessage(new Error("boom"))).toBe("boom");
  });

  it("an unknown thrown value falls back to the generic message", () => {
    expect(errorMessage("nope")).toBe("Ocorreu um erro. Tente novamente.");
  });
});
