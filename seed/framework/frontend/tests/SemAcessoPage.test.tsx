import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SemAcessoPage } from "../src/pages/SemAcessoPage";

describe("SemAcessoPage", () => {
  it("shows the message, core link and Sair", async () => {
    const onSignOut = vi.fn();
    render(<SemAcessoPage coreUrl="https://core.example" onSignOut={onSignOut} />);
    expect(screen.getByText("Sua organização não tem acesso a este produto.")).toBeTruthy();
    const link = screen.getByRole("link", { name: "Voltar para a NoctusAI" });
    expect(link.getAttribute("href")).toBe("https://core.example");
    fireEvent.click(screen.getByRole("button", { name: "Sair" }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });
});
