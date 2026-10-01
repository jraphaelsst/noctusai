import { describe, it, expect } from "vitest";
import { ApiError } from "@noctusai/lib";
import { errorMessage } from "./errors";

describe("errorMessage — 422 validation arrays", () => {
  it("maps a Pydantic pattern mismatch to pt-BR, never leaking the English msg", () => {
    const body = {
      detail: [
        {
          type: "string_pattern_mismatch",
          loc: ["body", "telefone"],
          msg: "String should match pattern '^\\+[1-9]\\d{7,14}$'",
        },
      ],
    };
    const err = new ApiError(422, "String should match pattern", body);
    expect(errorMessage(err)).toBe("Telefone: formato inválido.");
  });

  it("joins several fields (missing + too short)", () => {
    const body = {
      detail: [
        { type: "missing", loc: ["body", "email"], msg: "Field required" },
        { type: "string_too_short", loc: ["body", "nome"], msg: "x", ctx: { min_length: 2 } },
      ],
    };
    const msg = errorMessage(new ApiError(422, "Field required; x", body));
    expect(msg).toBe("E-mail: campo obrigatório. Nome: mínimo de 2 caracteres.");
  });

  it("still returns a string detail verbatim", () => {
    expect(errorMessage(new ApiError(409, "Já existe um membro com esse e-mail.", { detail: "x" }))).toBe(
      "Já existe um membro com esse e-mail.",
    );
  });
});
