/**
 * EnviarAssinaturaDialog — signatários prefill + submit gate
 * (signature-integration-CONTRACT §4).
 *
 * Coverage: prefill from compradores + vendedores + org testemunhas (in that
 * order, papel mapped per side), empty testemunha e-mails blocking submit
 * until edited, the 422 `ASSINATURA_PROVEDOR_NAO_CONFIGURADO` rendering with
 * its `details.faltando` list, and the 502 `provedor_mensagem` rendering.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

import { EnviarAssinaturaDialog, partesParaSignatarios } from "./EnviarAssinaturaDialog";
import { AssinaturaError } from "@/hooks/useContratos";
import type { TestemunhaSelecionada } from "@/hooks/useContratoTestemunhas";
import type { Comprador } from "@/types/cardHub";

function comprador(over: Partial<Comprador> = {}): Comprador {
  return {
    id: "p1",
    atendimento_id: "a1",
    cliente_id: "cli-p1",
    lado: "comprador",
    papel: "comprador",
    ordem: 0,
    observacao: null,
    created_at: null,
    cliente: {
      id: "cli-p1",
      nome: "Ana Compradora",
      nome_completo: "Ana Compradora",
      celular: null,
      email: "ana@example.com",
      nome_oficial: null,
      nacionalidade: null,
      profissao: null,
      estado_civil: null,
      regime_bens: null,
      conjuge_cliente_id: null,
      cpf: "123.456.789-01",
      rg: null,
      rg_orgao_expedidor: null,
      endereco_cep: null,
      endereco_logradouro: null,
      endereco_numero: null,
      endereco_complemento: null,
      endereco_bairro: null,
      endereco_cidade: null,
      endereco_uf: null,
    },
    ...over,
  };
}

function testemunha(over: Partial<TestemunhaSelecionada> = {}): TestemunhaSelecionada {
  return {
    id: "t1",
    nome: "João Testemunha",
    cpf: "987.654.321-00",
    email: null,
    celular: null,
    excluida: false,
    ...over,
  };
}

async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const onEnviar = vi.fn();
  const onOpenChange = vi.fn();
  const props = {
    open: true,
    onOpenChange,
    compradores: [comprador()],
    vendedores: [],
    testemunhas: [],
    onEnviar,
    sending: false,
    erro: null,
    ...over,
  };
  const view = rtl.render(
    <EnviarAssinaturaDialog {...(props as unknown as Parameters<typeof EnviarAssinaturaDialog>[0])} />,
  );
  return { ...view, ...rtl, onEnviar, onOpenChange, props };
}

describe("partesParaSignatarios", () => {
  it("compradores → papel comprador, vendedores → papel vendedor, testemunhas last, prefilled from the registry e-mail", () => {
    const lista = partesParaSignatarios(
      [comprador({ cliente: { ...comprador().cliente!, email: "comprador@x.com", cpf: "111.111.111-11" } })],
      [comprador({ id: "p2", cliente: { ...comprador().cliente!, nome_completo: "Vitor Vendedor", email: "vendedor@x.com", cpf: "222.222.222-22" } })],
      [testemunha({ email: "joao.testemunha@exemplo.test" })],
    );
    expect(lista.map((s) => s.papel)).toEqual(["comprador", "vendedor", "testemunha"]);
    expect(lista[0].email).toBe("comprador@x.com");
    // 🔴 CPF normalized to digits only.
    expect(lista[0].cpf).toBe("11111111111");
    expect(lista[1].nome).toBe("Vitor Vendedor");
    // migration 143 — `org_testemunhas.email` prefills straight through.
    expect(lista[2].email).toBe("joao.testemunha@exemplo.test");
    expect(lista[2].nome).toBe("João Testemunha");
  });

  it("uma testemunha sem e-mail cadastrado ainda prefila vazio", () => {
    const lista = partesParaSignatarios([], [], [testemunha({ email: null })]);
    expect(lista[0].email).toBe("");
  });
});

describe("EnviarAssinaturaDialog", () => {
  it("prefills one row per comprador/vendedor/testemunha on open", async () => {
    const { screen } = await render({
      compradores: [comprador()],
      vendedores: [comprador({ id: "p2", lado: "vendedor" })],
      testemunhas: [testemunha()],
    });
    expect(screen.getByTestId("assinatura-signatario-0")).toBeTruthy();
    expect(screen.getByTestId("assinatura-signatario-1")).toBeTruthy();
    expect(screen.getByTestId("assinatura-signatario-2")).toBeTruthy();
    expect(
      (screen.getByTestId("assinatura-signatario-email-0") as HTMLInputElement).value,
    ).toBe("ana@example.com");
    // This testemunha fixture has no e-mail set in the registry — prefills empty.
    expect(
      (screen.getByTestId("assinatura-signatario-email-2") as HTMLInputElement).value,
    ).toBe("");
  });

  it("prefills a testemunha row from the registry's e-mail when one is set", async () => {
    const { screen } = await render({
      compradores: [],
      vendedores: [],
      testemunhas: [testemunha({ email: "joao.testemunha@exemplo.test" })],
    });
    expect(
      (screen.getByTestId("assinatura-signatario-email-0") as HTMLInputElement).value,
    ).toBe("joao.testemunha@exemplo.test");
  });

  it("🔴 an empty testemunha e-mail blocks submit until the operator fills it in", async () => {
    const { screen, fireEvent, onEnviar } = await render({
      compradores: [],
      vendedores: [],
      testemunhas: [testemunha()],
    });
    expect(screen.getByTestId("assinatura-email-obrigatorio")).toBeTruthy();
    expect((screen.getByTestId("assinatura-enviar-btn") as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByTestId("assinatura-signatario-email-0"), {
      target: { value: "joao@example.com" },
    });
    expect(screen.queryByTestId("assinatura-email-obrigatorio")).toBeNull();
    expect((screen.getByTestId("assinatura-enviar-btn") as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(screen.getByTestId("assinatura-enviar-btn"));
    expect(onEnviar).toHaveBeenCalledWith({
      signatarios: [
        {
          nome: "João Testemunha",
          email: "joao@example.com",
          cpf: "98765432100",
          papel: "testemunha",
          testemunha_id: "t1",
        },
      ],
      mensagem: undefined,
    });
  });

  it("blocks submit entirely when there are no signatários at all", async () => {
    const { screen } = await render({ compradores: [], vendedores: [], testemunhas: [] });
    expect(screen.getByTestId("assinatura-sem-signatarios")).toBeTruthy();
    expect((screen.getByTestId("assinatura-enviar-btn") as HTMLButtonElement).disabled).toBe(true);
  });

  it("🔴 422 ASSINATURA_PROVEDOR_NAO_CONFIGURADO renders details.faltando with a link to Configurações", async () => {
    const erro = new AssinaturaError(
      "ASSINATURA_PROVEDOR_NAO_CONFIGURADO",
      "Configure a plataforma de assinatura em Configurações.",
      { faltando: ["d4sign_api_token", "d4sign_safe_uuid"] },
    );
    const { screen, fireEvent } = await render({ erro });
    const bloco = screen.getByTestId("assinatura-erro");
    expect(bloco.textContent).toContain("Configure a plataforma de assinatura");
    const faltando = screen.getByTestId("assinatura-erro-faltando");
    expect(faltando.textContent).toContain("d4sign_api_token");
    expect(faltando.textContent).toContain("d4sign_safe_uuid");
    fireEvent.click(screen.getByTestId("assinatura-erro-configuracoes-link"));
    expect(mockNavigate).toHaveBeenCalledWith("/configuracoes");
  });

  it("🔴 409 ASSINATURA_JA_ENVIADA renders the server's own message with no extra widget", async () => {
    const erro = new AssinaturaError(
      "ASSINATURA_JA_ENVIADA",
      "Este contrato já está em assinatura.",
      null,
    );
    const { screen } = await render({ erro });
    expect(screen.getByTestId("assinatura-erro").textContent).toContain(
      "Este contrato já está em assinatura.",
    );
    expect(screen.queryByTestId("assinatura-erro-faltando")).toBeNull();
  });

  it("502 ASSINATURA_PROVEDOR_ERRO renders details.provedor_mensagem", async () => {
    const erro = new AssinaturaError(
      "ASSINATURA_PROVEDOR_ERRO",
      "A plataforma de assinatura recusou o envio.",
      { provedor_mensagem: "signer email already used" },
    );
    const { screen } = await render({ erro });
    expect(screen.getByTestId("assinatura-erro").textContent).toContain(
      "signer email already used",
    );
  });

  it("does not re-seed signatários on a background prop refresh while open", async () => {
    const rtl = await import("@testing-library/react");
    const onEnviar = vi.fn();
    const view = rtl.render(
      <EnviarAssinaturaDialog
        open
        onOpenChange={vi.fn()}
        compradores={[comprador()]}
        vendedores={[]}
        testemunhas={[]}
        onEnviar={onEnviar}
      />,
    );
    rtl.fireEvent.change(rtl.screen.getByTestId("assinatura-signatario-email-0"), {
      target: { value: "editado@example.com" },
    });
    // A refetch of `compradores` while the dialog stays open must not wipe
    // the operator's edit.
    view.rerender(
      <EnviarAssinaturaDialog
        open
        onOpenChange={vi.fn()}
        compradores={[comprador({ cliente: { ...comprador().cliente!, email: "outro@example.com" } })]}
        vendedores={[]}
        testemunhas={[]}
        onEnviar={onEnviar}
      />,
    );
    expect(
      (rtl.screen.getByTestId("assinatura-signatario-email-0") as HTMLInputElement).value,
    ).toBe("editado@example.com");
  });
});
