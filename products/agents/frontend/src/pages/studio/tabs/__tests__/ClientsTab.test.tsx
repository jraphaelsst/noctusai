/**
 * ClientsTab.tsx tests — Agent Studio CONTRACT.md §G "Clientes". Stubs
 * `useClients.ts` (the ONE client hooks module, FE-DEF's — `useClientsKe.ts`
 * was collapsed into it) + `useIsAdmin`.
 */
import React from "react";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseClients = vi.fn();
const mockUseClient = vi.fn();
const mockUseCreateClient = vi.fn();
const mockUseUpdateClient = vi.fn();
const mockUseCreateClientEntry = vi.fn();
const mockUseUpdateClientEntry = vi.fn();
const mockUseDeleteClientEntry = vi.fn();
const mockUseIsAdmin = vi.fn();

vi.mock("@/hooks/studio/useClients", () => ({
  useClients: () => mockUseClients(),
  useClient: () => mockUseClient(),
  useCreateClient: () => mockUseCreateClient(),
  useUpdateClient: () => mockUseUpdateClient(),
  useCreateClientEntry: () => mockUseCreateClientEntry(),
  useUpdateClientEntry: () => mockUseUpdateClientEntry(),
  useDeleteClientEntry: () => mockUseDeleteClientEntry(),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockUseIsAdmin() }));

const CLIENT_LIST_ITEM = { id: "cl1", slug: "cliente-a", nome: "Cliente A", resumo: "...", ativo: true, total_entradas: 1 };
const CLIENT_DETAIL = {
  id: "cl1",
  slug: "cliente-a",
  nome: "Cliente A",
  resumo: "Marca X",
  ativo: true,
  entradas: [{ id: "e1", tipo: "marca" as const, titulo: "Tom de voz", conteudo: "Direto, sem jargão.", status: "ativo" as const, created_at: "t" }],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseIsAdmin.mockReturnValue(false);
  mockUseClients.mockReturnValue({ data: [CLIENT_LIST_ITEM], showSkeleton: false, isError: false, error: null });
  mockUseClient.mockReturnValue({ data: CLIENT_DETAIL, showSkeleton: false, isError: false, error: null });
  mockUseCreateClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseUpdateClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseCreateClientEntry.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseUpdateClientEntry.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockUseDeleteClientEntry.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

afterEach(() => cleanup());

async function renderTab() {
  const ClientsTab = (await import("@/pages/studio/tabs/ClientsTab")).default;
  render(React.createElement(ClientsTab, { agentKey: "isaia" }));
}

describe("ClientsTab — loading/empty/error", () => {
  it("shows a skeleton while clients load", async () => {
    mockUseClients.mockReturnValue({ data: undefined, showSkeleton: true, isError: false, error: null });
    await renderTab();
    expect(screen.queryByTestId("clients-row-cliente-a")).toBeNull();
  });

  it("shows an error state when clients fail to load", async () => {
    mockUseClients.mockReturnValue({ data: undefined, showSkeleton: false, isError: true, error: new Error("boom") });
    await renderTab();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("shows an empty client list and an empty selection placeholder", async () => {
    mockUseClients.mockReturnValue({ data: [], showSkeleton: false, isError: false, error: null });
    await renderTab();
    expect(screen.getByText("Nenhum cliente ainda.")).toBeTruthy();
    expect(screen.getByText("Selecione um cliente.")).toBeTruthy();
  });
});

describe("ClientsTab — success + role gating", () => {
  it("member: lists clients, selecting one shows its resumo and entries read-only, no write controls", async () => {
    await renderTab();
    fireEvent.click(screen.getByTestId("clients-row-cliente-a"));

    expect(await screen.findByTestId("client-detail")).toBeTruthy();
    expect(screen.getByDisplayValue("Marca X")).toBeTruthy();
    expect(screen.getByText("Tom de voz")).toBeTruthy();
    expect(screen.queryByTestId("clients-new-toggle")).toBeNull();
    expect(screen.queryByTestId("client-entry-form")).toBeNull();
  });

  it("admin: sees the new-client toggle and the entry form on a selected client", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    await renderTab();
    expect(screen.getByTestId("clients-new-toggle")).toBeTruthy();

    fireEvent.click(screen.getByTestId("clients-row-cliente-a"));
    expect(await screen.findByTestId("client-entry-form")).toBeTruthy();
  });
});
