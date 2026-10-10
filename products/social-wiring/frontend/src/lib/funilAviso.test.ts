import { describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { avisarFunilRecusado, funilRecusado } from "./funilAviso";

vi.mock("sonner", () => ({ toast: { warning: vi.fn() } }));

describe("funilAviso", () => {
  it("returns the motivo of a real refusal", () => {
    expect(funilRecusado({ moveu: false, motivo: "Celular é obrigatório" })).toBe(
      "Celular é obrigatório",
    );
  });

  it.each(["ja_na_etapa", "ja_adiante", "noop", "", null])("ignores benign motivo %s", (m) => {
    expect(funilRecusado({ moveu: false, motivo: m })).toBeNull();
  });

  it("ignores a move that happened or a missing result", () => {
    expect(funilRecusado({ moveu: true, motivo: "etapa_auto:x" })).toBeNull();
    expect(funilRecusado(undefined)).toBeNull();
  });

  it("warns once with the motivo", () => {
    expect(avisarFunilRecusado({ moveu: false, motivo: "falta X" })).toBe(true);
    expect(toast.warning).toHaveBeenCalledWith("O card não avançou de etapa", {
      description: "falta X",
    });
  });
});
