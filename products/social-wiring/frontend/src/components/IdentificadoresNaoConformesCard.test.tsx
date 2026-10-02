/**
 * The identifier hand-in (owner rule 2026-10-01): list with a pt-BR reason,
 * inline correction through the EXISTING edit endpoints, two-signal loading.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet, mockPatch } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPatch: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get: mockGet, patch: mockPatch } }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import type { IdentificadorNaoConforme } from "@/hooks/useIdentificadoresNaoConformes";
import {
  IdentificadoresNaoConformesCard,
  IdentificadoresNaoConformesPanel,
} from "./IdentificadoresNaoConformesCard";

afterEach(cleanup);

const CPF: IdentificadorNaoConforme = {
  chave: "clientes:cli-1:cpf", tabela: "clientes", linha_id: "cli-1", campo: "cpf", rotulo_campo: "CPF",
  valor: "123.456.789-00", canonico: null, situacao: "nao_cabe",
  motivo: "O dígito verificador não confere — confira os números digitados.",
  entidade_nome: "Maria da Silva", link: { tipo: "cliente", id: "cli-1" },
  edicao: { tipo: "cliente", id: "cli-1", campo: "cpf" },
};
const MAT: IdentificadorNaoConforme = {
  chave: "imovel_dados:ONE9441:numero_matricula", tabela: "imovel_dados", linha_id: "ONE9441",
  campo: "numero_matricula", rotulo_campo: "Nº da matrícula", valor: "12.3", canonico: null, situacao: "nao_cabe",
  motivo: "A quantidade de dígitos não corresponde a este tipo de documento.",
  entidade_nome: "Imóvel ONE9441", link: { tipo: "imovel", id: "ONE9441" },
  edicao: { tipo: "imovel", id: "ONE9441", campo: "numero_matricula" },
};
const CONSULTA: IdentificadorNaoConforme = {
  chave: "certidao_consultas:q1:documento", tabela: "certidao_consultas", linha_id: "q1", campo: "documento",
  rotulo_campo: "Documento da consulta de certidão", valor: "123", canonico: null, situacao: "nao_cabe",
  motivo: "x", entidade_nome: "Maria", link: { tipo: "cliente", id: "cli-1" }, edicao: null,
};
const pagina = (items: IdentificadorNaoConforme[], total = items.length) => ({ items, total, page: 1, page_size: 50 });

const base = {
  isPending: false, isFetching: false, isError: false, onRetry: vi.fn(), page: 1, onPage: vi.fn(),
  onSalvar: vi.fn().mockResolvedValue(undefined),
};
const wrap = ({ children }: { children: ReactNode }) => (
  <MemoryRouter>
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
  </MemoryRouter>
);
beforeEach(() => { mockGet.mockReset(); mockPatch.mockReset(); });

describe("IdentificadoresNaoConformesCard", () => {
  it("shows a skeleton only while pending with no data", () => {
    render(<IdentificadoresNaoConformesCard {...base} data={undefined} isPending isFetching />, { wrapper: wrap });
    expect(screen.getByTestId("identificadores-nao-conformes-skeleton")).toBeTruthy();
  });

  it("keeps the list and shows 'Atualizando' on a background refetch (never the skeleton)", () => {
    render(<IdentificadoresNaoConformesCard {...base} data={pagina([CPF])} isFetching />, { wrapper: wrap });
    expect(screen.queryByTestId("identificadores-nao-conformes-skeleton")).toBeNull();
    expect(screen.getByTestId("identificadores-nao-conformes-atualizando")).toBeTruthy();
    expect(screen.getByText("Maria da Silva")).toBeTruthy();
  });

  it("lists value, pt-BR reason and a link to the record", () => {
    render(<IdentificadoresNaoConformesCard {...base} data={pagina([CPF, MAT])} />, { wrapper: wrap });
    expect(screen.getByText("123.456.789-00")).toBeTruthy();
    expect(screen.getByTestId(`identificadores-nao-conformes-motivo-${CPF.chave}`).textContent).toContain("dígito verificador");
    expect(screen.getByTestId(`identificadores-nao-conformes-link-${CPF.chave}`).getAttribute("href")).toBe("/clientes/cli-1");
    expect(screen.getByTestId(`identificadores-nao-conformes-link-${MAT.chave}`).getAttribute("href")).toBe("/imoveis/ONE9441");
  });

  it("empty state when nothing is non-conforming", () => {
    render(<IdentificadoresNaoConformesCard {...base} data={pagina([], 0)} />, { wrapper: wrap });
    expect(screen.getByTestId("identificadores-nao-conformes-vazio")).toBeTruthy();
  });

  it("corrects inline: hands the trimmed new value to onSalvar", async () => {
    const onSalvar = vi.fn().mockResolvedValue(undefined);
    render(<IdentificadoresNaoConformesCard {...base} onSalvar={onSalvar} data={pagina([CPF])} />, { wrapper: wrap });
    fireEvent.click(screen.getByTestId(`identificadores-nao-conformes-editar-${CPF.chave}`));
    fireEvent.change(screen.getByTestId(`identificadores-nao-conformes-input-${CPF.chave}`), { target: { value: " 529.982.247-25 " } });
    fireEvent.click(screen.getByTestId(`identificadores-nao-conformes-salvar-${CPF.chave}`));
    await waitFor(() => expect(onSalvar).toHaveBeenCalledWith(CPF, "529.982.247-25"));
  });

  it("a certidão consulta has no inline edit — it points at the person", () => {
    render(<IdentificadoresNaoConformesCard {...base} data={pagina([CONSULTA])} />, { wrapper: wrap });
    expect(screen.queryByTestId(`identificadores-nao-conformes-editar-${CONSULTA.chave}`)).toBeNull();
    expect(screen.getByText(/Corrija no cadastro da pessoa/)).toBeTruthy();
  });
});

describe("IdentificadoresNaoConformesPanel (wiring)", () => {
  it("reads the queue and PATCHes the existing cliente endpoint, then refetches", async () => {
    mockGet.mockResolvedValue(pagina([CPF]));
    mockPatch.mockResolvedValue({});
    render(<IdentificadoresNaoConformesPanel />, { wrapper: wrap });
    await screen.findByText("Maria da Silva");
    expect(mockGet).toHaveBeenCalledWith("/api/identificadores/nao-conformes?page=1&page_size=50");
    fireEvent.click(screen.getByTestId(`identificadores-nao-conformes-editar-${CPF.chave}`));
    fireEvent.change(screen.getByTestId(`identificadores-nao-conformes-input-${CPF.chave}`), { target: { value: "529.982.247-25" } });
    fireEvent.click(screen.getByTestId(`identificadores-nao-conformes-salvar-${CPF.chave}`));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith("/api/clientes/cli-1", { cpf: "529.982.247-25" }));
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
  });

  it("an imóvel matrícula goes to the imóvel dados endpoint", async () => {
    mockGet.mockResolvedValue(pagina([MAT]));
    mockPatch.mockResolvedValue({});
    render(<IdentificadoresNaoConformesPanel />, { wrapper: wrap });
    await screen.findByText("Imóvel ONE9441");
    fireEvent.click(screen.getByTestId(`identificadores-nao-conformes-editar-${MAT.chave}`));
    fireEvent.change(screen.getByTestId(`identificadores-nao-conformes-input-${MAT.chave}`), { target: { value: "12.345" } });
    fireEvent.click(screen.getByTestId(`identificadores-nao-conformes-salvar-${MAT.chave}`));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith("/api/imoveis/ONE9441/dados", { numero_matricula: "12.345" }));
  });
});
