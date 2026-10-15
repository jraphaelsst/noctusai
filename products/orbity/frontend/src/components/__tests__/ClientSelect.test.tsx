import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

const { mockOptions } = vi.hoisted(() => ({ mockOptions: vi.fn() }));
vi.mock("@/hooks/useClients", () => ({ useClientOptions: () => mockOptions(), useLeadOptions: () => mockOptions() }));

import { ClientSelect } from "../ClientSelect";

const q = (o: object) => ({ data: undefined, isPending: false, isError: false, refetch: vi.fn(), ...o });

describe("ClientSelect", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists clients by NAME and emits the id", () => {
    mockOptions.mockReturnValue(q({ data: [{ id: "u-1", name: "Acme", company: "Acme SA", active: true }] }));
    const onChange = vi.fn();
    render(<ClientSelect value={undefined} onChange={onChange} id="c" />);
    expect(screen.getByRole("option", { name: /Acme/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Cliente"), { target: { value: "u-1" } });
    expect(onChange).toHaveBeenCalledWith("u-1");
  });
  it("clearing emits undefined", () => {
    mockOptions.mockReturnValue(q({ data: [{ id: "u-1", name: "Acme", company: null, active: true }] }));
    const onChange = vi.fn();
    render(<ClientSelect value="u-1" onChange={onChange} id="c" />);
    fireEvent.change(screen.getByLabelText("Cliente"), { target: { value: "" } });
    expect(onChange).toHaveBeenCalledWith(undefined);
  });
  it("loading shows a disabled placeholder (skeleton signal off data)", () => {
    mockOptions.mockReturnValue(q({ isPending: true }));
    render(<ClientSelect value={undefined} onChange={() => {}} id="c" />);
    expect(screen.getByLabelText("Cliente")).toBeDisabled();
  });
  it("error offers retry; empty shows guidance", () => {
    const refetch = vi.fn();
    mockOptions.mockReturnValue(q({ isError: true, refetch }));
    const { unmount } = render(<ClientSelect value={undefined} onChange={() => {}} id="c" />);
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
    unmount();
    mockOptions.mockReturnValue(q({ data: [] }));
    render(<ClientSelect value={undefined} onChange={() => {}} id="c" />);
    expect(screen.getByText(/Nenhum cliente ativo/)).toBeInTheDocument();
  });
  it("keeps a stored id that is no longer in the list selectable", () => {
    mockOptions.mockReturnValue(q({ data: [] }));
    render(<ClientSelect value="gone" onChange={() => {}} id="c" />);
    expect(screen.getByLabelText("Cliente")).toHaveValue("gone");
  });
});
