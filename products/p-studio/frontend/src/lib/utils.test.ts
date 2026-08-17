/**
 * Formatação pt-BR e aritmética de datas.
 *
 * O motivo de estes testes existirem é o fuso. Toda data do backend é `DATE`
 * puro (`2026-07-13`), e `new Date("2026-07-13")` interpreta a string como
 * UTC — em qualquer fuso negativo o dia volta um. As funções abaixo fatiam a
 * string em vez de deixar o `Date` decidir, e é isso que se pina aqui.
 */
import { describe, expect, it } from "vitest";

import {
  cn,
  fimMes,
  fmtData,
  fmtDataCurta,
  fmtDataExtenso,
  fmtHora,
  fmtHoraFim,
  fmtMoeda,
  fmtMoedaCurta,
  fmtPercentual,
  hojeISO,
  inicioMes,
  inicioSemana,
  paraISO,
  somaDias,
} from "@/lib/utils";

/** O ICU usa espaço estreito não-quebrável em alguns builds; normaliza. */
const esp = (s: string) => s.replace(/[  ]/g, " ");

// ── cn ────────────────────────────────────────────────────────────────────

describe("cn", () => {
  it("junta classes e resolve conflito do Tailwind pelo último", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("ignora valores falsos", () => {
    expect(cn("a", false && "b", null, undefined, "c")).toBe("a c");
  });
});

// ── dinheiro ──────────────────────────────────────────────────────────────

describe("fmtMoeda", () => {
  it("formata em real com duas casas", () => {
    expect(esp(fmtMoeda(1800))).toBe("R$ 1.800,00");
  });

  it("trata null e undefined como zero em vez de quebrar", () => {
    expect(esp(fmtMoeda(null))).toBe("R$ 0,00");
    expect(esp(fmtMoeda(undefined))).toBe("R$ 0,00");
  });

  it("formata negativo", () => {
    expect(esp(fmtMoeda(-50))).toContain("50,00");
  });
});

describe("fmtMoedaCurta", () => {
  it("abrevia milhares", () => {
    expect(esp(fmtMoedaCurta(52400))).toBe("R$ 52,4 mil");
  });

  it("abaixo de mil cai no formato cheio", () => {
    expect(esp(fmtMoedaCurta(950))).toBe("R$ 950,00");
  });

  it("exatamente mil já abrevia", () => {
    expect(esp(fmtMoedaCurta(1000))).toBe("R$ 1 mil");
  });

  it("abrevia negativo grande pelo módulo", () => {
    expect(esp(fmtMoedaCurta(-2500))).toBe("R$ -2,5 mil");
  });

  it("null vira R$ 0,00", () => {
    expect(esp(fmtMoedaCurta(null))).toBe("R$ 0,00");
  });
});

// ── datas ─────────────────────────────────────────────────────────────────

describe("fmtData", () => {
  it("converte ISO para dd/mm/aaaa", () => {
    expect(fmtData("2026-07-13")).toBe("13/07/2026");
  });

  it("não escorrega de dia por causa do fuso", () => {
    // `new Date("2026-01-01")` em UTC-3 daria 31/12/2025.
    expect(fmtData("2026-01-01")).toBe("01/01/2026");
  });

  it("aceita timestamp completo truncando", () => {
    expect(fmtData("2026-07-13T23:30:00+00:00")).toBe("13/07/2026");
  });

  it("ausente vira travessão", () => {
    expect(fmtData(null)).toBe("—");
    expect(fmtData(undefined)).toBe("—");
    expect(fmtData("")).toBe("—");
  });
});

describe("fmtDataCurta", () => {
  it("mostra dia e mês abreviado", () => {
    expect(fmtDataCurta("2026-07-13")).toBe("13 de jul.");
  });

  it("primeiro de janeiro não volta para dezembro", () => {
    expect(fmtDataCurta("2026-01-01")).toBe("01 de jan.");
  });

  it("ausente vira travessão", () => {
    expect(fmtDataCurta(null)).toBe("—");
  });
});

describe("fmtDataExtenso", () => {
  it("traz dia da semana por extenso", () => {
    expect(fmtDataExtenso("2026-07-13")).toBe("segunda-feira, 13 de julho");
  });
});

describe("fmtHora", () => {
  it("corta os segundos", () => {
    expect(fmtHora("09:00:00")).toBe("09:00");
  });

  it("ausente vira string vazia", () => {
    expect(fmtHora(null)).toBe("");
    expect(fmtHora(undefined)).toBe("");
  });
});

describe("fmtHoraFim", () => {
  it("soma a duração ao horário de início", () => {
    expect(fmtHoraFim("09:00:00", 120)).toBe("11:00");
  });

  it("vira a hora quando os minutos passam de 60", () => {
    expect(fmtHoraFim("09:45", 30)).toBe("10:15");
  });

  it("duração zero devolve o próprio início", () => {
    expect(fmtHoraFim("14:30", 0)).toBe("14:30");
  });

  it("dá a volta na meia-noite em vez de estourar para 25h", () => {
    expect(fmtHoraFim("23:30", 60)).toBe("00:30");
  });
});

describe("fmtPercentual", () => {
  it("converte fração em porcentagem inteira", () => {
    expect(fmtPercentual(0.72)).toBe("72%");
  });

  it("arredonda", () => {
    expect(fmtPercentual(0.725)).toBe("73%");
  });

  it("null vira 0%", () => {
    expect(fmtPercentual(null)).toBe("0%");
  });
});

// ── aritmética de datas ───────────────────────────────────────────────────

describe("hojeISO / paraISO", () => {
  it("hojeISO sai no formato YYYY-MM-DD", () => {
    expect(hojeISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("paraISO usa a data local, não a UTC", () => {
    // 23:30 local em UTC-3 é o dia seguinte em UTC; deve sair o dia local.
    expect(paraISO(new Date(2026, 6, 13, 23, 30))).toBe("2026-07-13");
  });
});

describe("somaDias", () => {
  it("soma dentro do mês", () => {
    expect(somaDias("2026-07-13", 5)).toBe("2026-07-18");
  });

  it("atravessa o fim do mês", () => {
    expect(somaDias("2026-07-30", 5)).toBe("2026-08-04");
  });

  it("atravessa a virada do ano para trás", () => {
    expect(somaDias("2026-01-01", -1)).toBe("2025-12-31");
  });

  it("respeita ano bissexto", () => {
    expect(somaDias("2028-02-28", 1)).toBe("2028-02-29");
  });

  it("zero devolve a mesma data", () => {
    expect(somaDias("2026-07-13", 0)).toBe("2026-07-13");
  });
});

describe("inicioSemana", () => {
  it("volta para o domingo", () => {
    // 2026-07-13 é segunda; o domingo é 12.
    expect(inicioSemana("2026-07-13")).toBe("2026-07-12");
  });

  it("domingo é o próprio início", () => {
    expect(inicioSemana("2026-07-12")).toBe("2026-07-12");
  });

  it("sábado volta seis dias", () => {
    expect(inicioSemana("2026-07-18")).toBe("2026-07-12");
  });

  it("atravessa a virada do mês", () => {
    // 2026-08-01 é sábado → domingo 26/07.
    expect(inicioSemana("2026-08-01")).toBe("2026-07-26");
  });
});

describe("inicioMes / fimMes", () => {
  it("início é sempre dia 01", () => {
    expect(inicioMes("2026-07-13")).toBe("2026-07-01");
  });

  it("fim de mês de 31 dias", () => {
    expect(fimMes("2026-07-13")).toBe("2026-07-31");
  });

  it("fim de mês de 30 dias", () => {
    expect(fimMes("2026-04-10")).toBe("2026-04-30");
  });

  it("fevereiro comum", () => {
    expect(fimMes("2026-02-10")).toBe("2026-02-28");
  });

  it("fevereiro bissexto", () => {
    expect(fimMes("2028-02-10")).toBe("2028-02-29");
  });

  it("dezembro não vaza para o ano seguinte", () => {
    expect(fimMes("2026-12-05")).toBe("2026-12-31");
  });
});
