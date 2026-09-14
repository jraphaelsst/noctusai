/**
 * errors.ts — PT-BR mapping tests (contract §E.2 error rows).
 *
 * Parses the flat `{detail, code}` body the way the seed `ApiClient` does
 * (`err.message` already carries `[<status>] <detail>` — see
 * `seed/lib/frontend/src/api.ts`) and asserts the task-specified copy per
 * backend `detail` text, plus the generic status fallbacks.
 */
import { describe, expect, it } from "vitest";
import { ApiError, errorMessage } from "@/lib/errors";

describe("errorMessage — code-specific overrides (contract §E.2)", () => {
  it("409 turn_in_progress → 'Julia ainda está respondendo a mensagem anterior.'", () => {
    const err = new ApiError(409, "Já existe um turno em andamento.");
    expect(errorMessage(err)).toBe("Julia ainda está respondendo a mensagem anterior.");
  });

  it("409 agent_off → 'Julia está desligada — um administrador pode ligá-la em Agentes.'", () => {
    const err = new ApiError(409, "O agente Julia está desligado.");
    expect(errorMessage(err)).toBe(
      "Julia está desligada — um administrador pode ligá-la em Agentes.",
    );
  });

  it("502 upstream_failed → 'Não foi possível falar com o social-wiring.'", () => {
    const err = new ApiError(502, "Falha ao comunicar com o social-wiring.");
    expect(errorMessage(err)).toBe("Não foi possível falar com o social-wiring.");
  });

  it("409 not_configured → 'Configure a conexão do One Chat.'", () => {
    const err = new ApiError(409, "One Chat ainda não configurado (nenhuma conexão vinculada).");
    expect(errorMessage(err)).toBe("Configure a conexão do One Chat.");
  });

  it("already_decided passes the backend's own PT-BR text through unchanged", () => {
    const err = new ApiError(409, "Esta aprovação já foi decidida.");
    expect(errorMessage(err)).toBe("Esta aprovação já foi decidida.");
  });

  it("orphaned passes the backend's own PT-BR text through unchanged", () => {
    const err = new ApiError(409, "Não há um turno ativo aguardando esta aprovação.");
    expect(errorMessage(err)).toBe("Não há um turno ativo aguardando esta aprovação.");
  });

  it("not_allowed (403) passes the backend's own PT-BR text through unchanged", () => {
    const err = new ApiError(403, "Você não pode decidir esta aprovação.");
    expect(errorMessage(err)).toBe("Você não pode decidir esta aprovação.");
  });
});

describe("errorMessage — status fallbacks", () => {
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
