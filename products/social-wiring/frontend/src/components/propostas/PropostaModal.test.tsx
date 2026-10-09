/**
 * PropostaModal / PropostasSection / PreparandoContratoPanel against the
 * lead-to-contract CONTRACT §4 shapes (hooks mocked at the boundary).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ApiError } from "@noctusai/lib";
import type { Proposta } from "@/types/propostas";

const m = vi.hoisted(() => ({
  list: vi.fn(),
  one: vi.fn(),
  salvar: vi.fn(),
  enviar: vi.fn(),
  recusar: vi.fn(),
  aceitar: vi.fn(),
  excluir: vi.fn(),
  posAceite: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));
const mut = (fn: ReturnType<typeof vi.fn>) => ({ mutateAsync: fn, isPending: false });
vi.mock("@/hooks/usePropostas", () => ({
  usePropostas: m.list,
  useProposta: m.one,
  usePropostaMutations: () => ({
    criar: mut(vi.fn()),
    salvar: mut(m.salvar),
    enviar: mut(m.enviar),
    recusar: mut(m.recusar),
    aceitar: mut(m.aceitar),
    excluir: mut(m.excluir),
    posAceite: mut(m.posAceite),
  }),
}));
vi.mock("@/hooks/useImobiliarias", () => ({
  useImobiliarias: () => ({ data: { items: [{ id: "im1", razao_social: "Imob 1", nome_fantasia: null, cnpj: null }] } }),
}));
vi.mock("@/hooks/useTestemunhas", () => ({
  useTestemunhas: () => ({
    data: { items: [{ id: "t1", nome: "Ana", cpf_pendente: false }, { id: "t2", nome: "Bia", cpf_pendente: false }] },
  }),
}));
vi.mock("sonner", () => ({ toast: m.toast }));

import { PropostaModal } from "./PropostaModal";
import { PropostasSection } from "./PropostasSection";

function proposta(over: Partial<Proposta> = {}): Proposta {
  return {
    id: "p1", atendimento_id: "a1", cliente_id: "c1", visita_id: null, imovel_codigo: "ONE9441",
    status: "rascunho", valor_proposto: "850000.00", pct_comissao: "6", financiamento: false, fgts: false,
    validade_ate: "2026-11-01", observacoes: null,
    parcelas: [{ tipo: "sinal", valor: "50000.00" }], favorecidos: [], intermediarios: [], termos: {},
    imobiliaria_id: null, testemunha_ids: [], enviada_em: null, aceita_em: null, recusada_em: null,
    motivo_recusa: null, contrato_id: null, created_at: null, updated_at: null,
    imovel: { codigo: "ONE9441", titulo: "Casa Cotia", endereco: "Rua A" },
    visita: null, imobiliaria: null, testemunhas: [], saldo_nao_alocado: "800000.00",
    completude: ["Imobiliária"],
    ...over,
  };
}
const resp = (data: unknown, over: Record<string, unknown> = {}) => ({
  data, showSkeleton: false, isRefreshing: false, isError: false, error: null, ...over,
});

beforeEach(() => {
  m.one.mockReturnValue(resp(proposta()));
  m.list.mockReturnValue(resp([proposta()]));
});
afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  Object.values(m).forEach((f) => typeof f === "function" && f.mockReset());
  m.toast.success.mockReset();
  m.toast.error.mockReset();
});

async function abrir(irPara = vi.fn(), onAbrirContrato = vi.fn()) {
  const rtl = await import("@testing-library/react");
  rtl.render(
    <MemoryRouter>
      <PropostaModal clienteId="c1" propostaId="p1" onClose={vi.fn()} irPara={irPara} onAbrirContrato={onAbrirContrato} />
    </MemoryRouter>,
  );
  return { rtl, irPara, onAbrirContrato };
}

describe("PropostasSection", () => {
  it("lists cards and opens the modal", async () => {
    const rtl = await import("@testing-library/react");
    rtl.render(<MemoryRouter><PropostasSection clienteId="c1" /></MemoryRouter>);
    rtl.fireEvent.click(rtl.screen.getByTestId("proposta-card-p1"));
    expect(await rtl.screen.findByTestId("proposta-modal")).toBeTruthy();
  });
  it("shows the empty state", async () => {
    m.list.mockReturnValue(resp([]));
    const rtl = await import("@testing-library/react");
    rtl.render(<MemoryRouter><PropostasSection clienteId="c1" /></MemoryRouter>);
    expect(rtl.screen.getByTestId("propostas-vazio")).toBeTruthy();
  });
});

describe("PropostaModal", () => {
  it("renders the sections and live saldo, and edits parcelas", async () => {
    const { rtl } = await abrir();
    expect(rtl.screen.getByTestId("proposta-secao-parcelas")).toBeTruthy();
    expect(rtl.screen.getByTestId("proposta-saldo").textContent).toContain("800.000,00");
    rtl.fireEvent.change(rtl.screen.getByLabelText("Valor da parcela 1"), { target: { value: "850.000,00" } });
    expect(rtl.screen.getByTestId("proposta-saldo").textContent).toContain("0,00");
    rtl.fireEvent.click(rtl.screen.getByTestId("parcela-add"));
    expect(rtl.screen.getByTestId("parcela-row-1")).toBeTruthy();
    rtl.fireEvent.click(rtl.screen.getAllByLabelText("Remover linha")[1]);
    expect(rtl.screen.queryByTestId("parcela-row-1")).toBeNull();
  });

  it("saves the edited draft with decimal-string money", async () => {
    m.salvar.mockResolvedValue(proposta());
    const { rtl } = await abrir();
    rtl.fireEvent.change(rtl.screen.getByLabelText("Valor proposto"), { target: { value: "900.000,50" } });
    rtl.fireEvent.click(rtl.screen.getByTestId("proposta-salvar"));
    await rtl.waitFor(() => expect(m.salvar).toHaveBeenCalled());
    const arg = m.salvar.mock.calls[0][0];
    expect(arg.id).toBe("p1");
    expect(arg.patch.valor_proposto).toBe("900000.50");
  });

  it("recusar requires a motivo", async () => {
    m.recusar.mockResolvedValue(proposta({ status: "recusada" }));
    const { rtl } = await abrir();
    rtl.fireEvent.click(rtl.screen.getByTestId("proposta-recusar"));
    const confirmar = (await rtl.screen.findByTestId("recusar-confirmar")) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
    rtl.fireEvent.change(rtl.screen.getByLabelText("Motivo da recusa"), { target: { value: "Valor baixo" } });
    expect(confirmar.disabled).toBe(false);
    rtl.fireEvent.click(confirmar);
    await rtl.waitFor(() => expect(m.recusar).toHaveBeenCalledWith({ id: "p1", motivo: "Valor baixo" }));
  });

  it("aceitar confirms with completude, then shows Preparando contrato and navigates", async () => {
    m.aceitar.mockResolvedValue({
      proposta: proposta({ status: "aceita" }), contrato_id: "k1",
      geracao: { pronto: false, faltando: [], bloqueios: [], avisos: [] },
      passos: [
        { passo: "materializar", status: "ok", mensagem: null },
        { passo: "pos_aceite", status: "erro", mensagem: "InfoSimples fora do ar" },
      ],
      pos_aceite: {
        certidoes: [{ parte_nome: "João", kind: "parte", alvo_id: "x", consulta_id: null, status: "emitindo", motivo: null, tipos: ["federal"] }],
        matricula: { status: "faltando", documento_id: null, motivo: "matricula_ausente" },
      },
    });
    const { rtl, irPara, onAbrirContrato } = await abrir();
    rtl.fireEvent.click(rtl.screen.getByTestId("proposta-aceitar"));
    expect((await rtl.screen.findByTestId("aceitar-completude")).textContent).toContain("Imobiliária");
    rtl.fireEvent.click(rtl.screen.getByTestId("aceitar-confirmar"));
    expect(await rtl.screen.findByTestId("preparando-contrato-panel")).toBeTruthy();
    expect(rtl.screen.getByText("João")).toBeTruthy();
    expect(rtl.screen.getByTestId("pos-aceite-matricula").textContent).toContain("Matrícula não anexada");
    expect(rtl.screen.getByText("InfoSimples fora do ar")).toBeTruthy();
    expect(rtl.screen.getByTestId("aceite-tentar-de-novo")).toBeTruthy();
    expect(m.toast.success).toHaveBeenCalled();
    rtl.fireEvent.click(rtl.screen.getByTestId("ir-contratos"));
    expect(onAbrirContrato).toHaveBeenCalledWith("k1");
    expect(irPara).toHaveBeenCalledWith("contratos");
  });

  it("maps 409 codes to friendly copy and highlights 400 field paths", async () => {
    m.salvar.mockRejectedValue(
      new ApiError(400, "Proposta inválida", {
        error: { code: "snapshot_invalido", message: "Proposta inválida", details: { campos: [{ path: "valor_proposto", mensagem: "x" }] } },
      }),
    );
    const { rtl } = await abrir();
    rtl.fireEvent.change(rtl.screen.getByLabelText("Valor proposto"), { target: { value: "1" } });
    rtl.fireEvent.click(rtl.screen.getByTestId("proposta-salvar"));
    await rtl.waitFor(() => expect(m.toast.error).toHaveBeenCalled());
    expect(rtl.screen.getByLabelText("Valor proposto").className).toContain("border-destructive");

    m.salvar.mockResolvedValue(proposta());
    rtl.fireEvent.click(rtl.screen.getByTestId("proposta-salvar"));
    await rtl.waitFor(() => expect(m.salvar).toHaveBeenCalledTimes(2));
    m.aceitar.mockRejectedValue(
      new ApiError(409, "O imóvel desta proposta é diferente do imóvel já em negociação.", {
        error: { code: "imovel_divergente", message: "O imóvel desta proposta é diferente do imóvel já em negociação." },
      }),
    );
    rtl.fireEvent.click(rtl.screen.getByTestId("proposta-aceitar"));
    rtl.fireEvent.click(await rtl.screen.findByTestId("aceitar-confirmar"));
    await rtl.waitFor(() =>
      expect(m.toast.error).toHaveBeenLastCalledWith(expect.stringContaining("diferente do imóvel")),
    );
  });

  it("is read-only when the proposta is closed", async () => {
    m.one.mockReturnValue(resp(proposta({ status: "aceita" })));
    const { rtl } = await abrir();
    expect(rtl.screen.getByTestId("proposta-somente-leitura")).toBeTruthy();
    expect(rtl.screen.queryByTestId("proposta-aceitar")).toBeNull();
    expect(rtl.screen.queryByTestId("proposta-salvar")).toBeNull();
    expect((rtl.screen.getByLabelText("Valor proposto") as HTMLInputElement).disabled).toBe(true);
    expect(rtl.screen.queryByTestId("parcela-add")).toBeNull();
  });

  it("offers Excluir only for rascunho", async () => {
    m.one.mockReturnValue(resp(proposta({ status: "enviada" })));
    const { rtl } = await abrir();
    expect(rtl.screen.queryByTestId("proposta-excluir")).toBeNull();
    expect(rtl.screen.queryByTestId("proposta-enviar")).toBeNull();
  });
});

describe("snapshot refs and ids", () => {
  it("sends real-id fields as null and re-points fav: refs when a favorecido is removed", async () => {
    m.one.mockReturnValue(resp(proposta({
      favorecidos: [{ nome: "A" }, { nome: "B" }],
      parcelas: [{ tipo: "sinal", valor: "1.00", favorecido_ref: "fav:0" }, { tipo: "saldo", valor: "2.00", favorecido_ref: "fav:1" }],
      termos: { posse_marco_parcela_ref: "parcela:1", posse_marco_parcela_id: "real-id", ad_corpus: null },
    })));
    m.salvar.mockResolvedValue(proposta());
    const { rtl } = await abrir();
    rtl.fireEvent.click(rtl.screen.getByTestId("favorecido-row-0").querySelector("button[aria-label='Remover linha']")!);
    rtl.fireEvent.click(rtl.screen.getByTestId("proposta-salvar"));
    await rtl.waitFor(() => expect(m.salvar).toHaveBeenCalled());
    const patch = m.salvar.mock.calls[0][0].patch;
    expect(patch.parcelas[0].favorecido_ref).toBeNull();
    expect(patch.parcelas[1].favorecido_ref).toBe("fav:0");
    expect(patch.parcelas.every((p: { favorecido_id: unknown }) => p.favorecido_id === null)).toBe(true);
    expect(patch.termos.posse_marco_parcela_id).toBeNull();
    expect(patch.termos.permuta_posse_marco_parcela_id).toBeNull();
    expect(patch.termos.posse_marco_parcela_ref).toBe("parcela:1");
    expect("ad_corpus" in patch.termos).toBe(true); // keys round-trip
  });

  it("re-points parcela: refs when a parcela is removed", async () => {
    m.one.mockReturnValue(resp(proposta({
      parcelas: [{ tipo: "sinal", valor: "1.00" }, { tipo: "saldo", valor: "2.00" }],
      termos: { posse_marco_parcela_ref: "parcela:1" },
    })));
    m.salvar.mockResolvedValue(proposta());
    const { rtl } = await abrir();
    rtl.fireEvent.click(rtl.screen.getByTestId("parcela-row-0").querySelector("button[aria-label='Remover linha']")!);
    rtl.fireEvent.click(rtl.screen.getByTestId("proposta-salvar"));
    await rtl.waitFor(() => expect(m.salvar).toHaveBeenCalled());
    expect(m.salvar.mock.calls[0][0].patch.termos.posse_marco_parcela_ref).toBe("parcela:0");
  });
});

describe("lerErroProposta 422", () => {
  it("maps detail[].loc to field paths with a generic message", async () => {
    const { lerErroProposta } = await import("./erroProposta");
    const e = new ApiError(422, "x", { detail: [{ loc: ["body", "parcelas", 0, "valor"], msg: "bad" }] });
    const r = lerErroProposta(e, "fb");
    expect(r.campos).toEqual(["parcelas.0.valor"]);
    expect(r.mensagem).toContain("inválidos");
  });
  it("covers the new 4xx codes without details", async () => {
    const { lerErroProposta } = await import("./erroProposta");
    const e = new ApiError(409, "", { error: { code: "proposta_nao_rascunho" } });
    expect(lerErroProposta(e, "fb").mensagem).toContain("rascunho");
  });
});

describe("lerErroProposta", () => {
  it("prefers the server message, falls back to the code map, then to the caller copy", async () => {
    const { lerErroProposta } = await import("./erroProposta");
    const srv = new ApiError(409, "Mensagem do servidor", { error: { code: "proposta_fechada", message: "Mensagem do servidor" } });
    expect(lerErroProposta(srv, "fb").mensagem).toBe("Mensagem do servidor");
    expect(lerErroProposta(srv, "fb").code).toBe("proposta_fechada");
    const semMsg = new ApiError(409, "", { error: { code: "proposta_ja_aceita" } });
    expect(lerErroProposta(semMsg, "fb").mensagem).toContain("aceita");
    expect(lerErroProposta(new Error(""), "fb").mensagem).toBe("fb");
  });
});
