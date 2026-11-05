import { describe, expect, it } from "vitest";

import { blocosParaTexto } from "@/lib/juliaAviso";

describe("juliaAviso blocks -> text", () => {
  it("renders paragraphs separated by a blank line and bullet lists as '- ' lines", () => {
    expect(blocosParaTexto([{ p: "Tratamos seus dados." }, { ul: ["nome", "telefone"] }, { p: "Fim." }])).toBe(
      "Tratamos seus dados.\n\n- nome\n- telefone\n\nFim.",
    );
  });
});
