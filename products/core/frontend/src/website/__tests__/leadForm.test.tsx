import "@testing-library/jest-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LocaleProvider } from "../lib/i18n";
import { LeadForm } from "../components/LeadForm";

afterEach(cleanup);

describe("LeadForm", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { id: "lead_1", whatsapp_url: null } }),
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  it("submits a payload matching the contract §3 POST /api/website/leads shape", async () => {
    render(
      <LocaleProvider locale="pt-BR">
        <LeadForm variant="waitlist" />
      </LocaleProvider>,
    );

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Ana Silva" } });
    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "ana@example.com" } });
    fireEvent.click(screen.getByText(/Concordo em ser contatado/));
    fireEvent.click(screen.getByText("Enviar"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/website\/leads$/);
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body).toMatchObject({
      source: "waitlist",
      name: "Ana Silva",
      email: "ana@example.com",
      locale: "pt-BR",
      consent_marketing: true,
    });
    expect(typeof body.consent_text_version).toBe("string");
  });

  it("refuses to submit without the consent checkbox", async () => {
    render(
      <LocaleProvider locale="pt-BR">
        <LeadForm variant="contact" />
      </LocaleProvider>,
    );
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Ana Silva" } });
    fireEvent.click(screen.getByText("Enviar"));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
