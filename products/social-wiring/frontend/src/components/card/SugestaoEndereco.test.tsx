/**
 * The `endereco` suggestion: fills an empty address, or — `substitui` —
 * asks to REPLACE the stored one with a bill whose titular is not this person.
 * Real `useExtracaoSugestaoMutation` + real QueryClient; only the transport
 * (`api`) is fake. Synthetic data only.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

afterEach(cleanup);

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post, patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));

import { useExtracaoSugestaoMutation } from "@/hooks/useCardHub";
import type { ExtracaoSugestaoEndereco } from "@/types/cardHub";

import { DocumentoChecklistSection } from "./DocumentoChecklistSection";

const ATUAL = { cep: "01000-000", logradouro: "Rua Antiga", numero: "10", complemento: null, bairro: "Centro", cidade: "São Paulo", uf: "SP" };
const NOVO = { cep: "02000-000", logradouro: "Av. Nova", numero: "500", complemento: "ap 3", bairro: "Jardim", cidade: "Osasco", uf: "SP" };

function sug(over: Partial<ExtracaoSugestaoEndereco> = {}): ExtracaoSugestaoEndereco {
  return {
    valor: NOVO,
    valor_atual: ATUAL,
    documento_id: "doc-1",
    documento_nome: "conta-luz.pdf",
    tipo_documento: "comprovante_residencia",
    confianca: "alta",
    fonte: "texto",
    rotulo: null,
    titular_documento: "Fulano Outro da Silva",
    substitui: true,
    aviso: "comprovante_titular_nao_confere",
    ...over,
  };
}

function Harness({ sugestao, erro }: { sugestao: ExtracaoSugestaoEndereco; erro?: boolean }) {
  const m = useExtracaoSugestaoMutation("cli-1");
  return (
    <>
      <DocumentoChecklistSection
        items={[]}
        onToggle={vi.fn()}
        onResolverSugestao={(documentoId, acao, itemKey) => m.mutate({ documentoId, acao, itemKey })}
        sugestaoSaving={m.isPending}
        sugestoesExtras={{ endereco: sugestao }}
      />
      {erro && m.isError && <p data-testid="erro">falhou</p>}
    </>
  );
}

function mount(sugestao: ExtracaoSugestaoEndereco, erro = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Harness sugestao={sugestao} erro={erro} />
    </QueryClientProvider>,
  );
}

describe("SugestaoEndereco", () => {
  it("substitution: asks, shows both addresses + titular + warning", () => {
    mount(sug());
    const base = "documento-checklist-endereco-sugestao";
    expect(screen.getByTestId(`${base}-pergunta`).textContent).toBe(
      "Substituir o endereço atual pelo deste comprovante?",
    );
    expect(screen.getByTestId(`${base}-atual`).textContent).toContain("Rua Antiga, 10");
    expect(screen.getByTestId(`${base}-proposto`).textContent).toContain("Av. Nova, 500");
    expect(screen.getByTestId(`${base}-titular`).textContent).toContain("Fulano Outro da Silva");
    expect(screen.getByTestId(`${base}-aviso-titular`)).toBeTruthy();
  });

  it("accept posts confirmar with item_key endereco; refuse posts descartar", async () => {
    post.mockReset().mockResolvedValue({ documento_id: "doc-1", substituiu: ATUAL });
    mount(sug());
    fireEvent.click(screen.getByTestId("documento-checklist-endereco-sugestao-confirmar"));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/clientes/cli-1/documentos/doc-1/extracao/confirmar", { item_key: "endereco" }),
    );
    cleanup();
    post.mockClear();
    mount(sug());
    fireEvent.click(screen.getByTestId("documento-checklist-endereco-sugestao-descartar"));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/clientes/cli-1/documentos/doc-1/extracao/descartar", { item_key: "endereco" }),
    );
  });

  it("buttons are disabled while saving, and a failure surfaces", async () => {
    let rej: (e: Error) => void = () => {};
    post.mockReset().mockReturnValue(new Promise((_, r) => (rej = r)));
    mount(sug(), true);
    fireEvent.click(screen.getByTestId("documento-checklist-endereco-sugestao-confirmar"));
    await waitFor(() =>
      expect((screen.getByTestId("documento-checklist-endereco-sugestao-confirmar") as HTMLButtonElement).disabled).toBe(true),
    );
    rej(new Error("boom"));
    await waitFor(() => expect(screen.getByTestId("erro")).toBeTruthy());
  });

  it("empty-address case: no 'current' block, fill wording, no titular warning", () => {
    mount(sug({ substitui: false, valor_atual: null, aviso: null, titular_documento: null }));
    const base = "documento-checklist-endereco-sugestao";
    expect(screen.getByTestId(`${base}-pergunta`).textContent).toContain("Preencher");
    expect(screen.queryByTestId(`${base}-atual`)).toBeNull();
    expect(screen.queryByTestId(`${base}-aviso-titular`)).toBeNull();
  });
});
