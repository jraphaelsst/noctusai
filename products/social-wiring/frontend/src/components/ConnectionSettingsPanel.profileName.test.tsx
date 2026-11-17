/**
 * ConnectionSettingsPanel — "Editar linha": the line name (label, PATCH) AND the WhatsApp profile display name
 * (`PUT /{id}/perfil`) leads see on the number. Hooks mocked at the module boundary (same pattern as Conexao.test.tsx).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const profileMutate = vi.fn();
const profileState = { isPending: false, isError: false, error: null as Error | null };
const updateMutate = vi.fn();
const statusState: { data: any } = {
  data: { paired: true, status: "WORKING", me_name: "One Chat", session: "s", error: null },
};

vi.mock("@/hooks/useWhatsAppConnections", () => ({
  useWhatsAppConnectionMutations: () => ({
    update: { mutate: updateMutate, isPending: false },
    create: { mutate: vi.fn(), isPending: false },
    remove: { mutate: vi.fn(), isPending: false },
  }),
  useSetWhatsAppProfileName: () => ({ mutate: profileMutate, ...profileState }),
  useWhatsAppConnectionStatus: () => statusState,
  useWhatsAppConnectionQr: () => ({ data: null }),
  useRecoverConnection: () => ({ mutate: vi.fn(), isPending: false }),
  useWhatsAppConnectionActions: () => ({
    start: { mutate: vi.fn(), isPending: false },
    restart: { mutate: vi.fn(), isPending: false },
    logout: { mutate: vi.fn(), isPending: false },
  }),
  useConnectionChats: () => ({ data: [], isPending: false }),
  useToggleAutoReply: () => ({ mutate: vi.fn(), isPending: false }),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const line: any = {
  id: "conn-1", label: "One Chat", base_url: "http://waha", session_name: "sw_1",
  webhook_url: "https://x/hook", bound_chats: [], created_at: "", updated_at: "",
};

async function renderPanel() {
  const rtl = await import("@testing-library/react");
  const { ConnectionSettingsPanel } = await import("@/components/ConnectionDetailDialog");
  rtl.render(<ConnectionSettingsPanel line={line} onRequestDelete={vi.fn()} />);
  return rtl;
}

describe("ConnectionSettingsPanel — profile display name", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    profileState.isPending = false;
    profileState.isError = false;
    profileState.error = null;
    statusState.data = { paired: true, status: "WORKING", me_name: "One Chat", session: "s", error: null };
  });

  it("prefills the profile name from the live WhatsApp name and the label from the line", async () => {
    const rtl = await renderPanel();
    expect((rtl.screen.getByTestId("edit-conn-label") as HTMLInputElement).value).toBe("One Chat");
    expect((rtl.screen.getByTestId("edit-conn-profile-name") as HTMLInputElement).value).toBe("One Chat");
  });

  it("sends the trimmed profile name to the perfil endpoint and toasts on success", async () => {
    const rtl = await renderPanel();
    rtl.fireEvent.change(rtl.screen.getByTestId("edit-conn-profile-name"), {
      target: { value: "  Júlia ~ One Consultoria " },
    });
    rtl.fireEvent.click(rtl.screen.getByTestId("btn-save-profile-name"));
    expect(profileMutate).toHaveBeenCalledTimes(1);
    const [vars, opts] = profileMutate.mock.calls[0];
    expect(vars).toEqual({ id: "conn-1", nome: "Júlia ~ One Consultoria" });
    opts.onSuccess();
    expect(toast.success).toHaveBeenCalledWith("Nome exibido no WhatsApp atualizado");
  });

  it("surfaces a refusal (toast + inline alert), never silently", async () => {
    profileState.isError = true;
    profileState.error = new Error("Esta linha não permite alterar o nome exibido no WhatsApp (envio desativado).");
    const rtl = await renderPanel();
    expect(rtl.screen.getByTestId("profile-name-error").textContent).toContain("não permite");
    rtl.fireEvent.click(rtl.screen.getByTestId("btn-save-profile-name"));
    profileMutate.mock.calls[0][1].onError(new Error("recusado"));
    expect(toast.error).toHaveBeenCalledWith("recusado");
  });

  it("the line name is saved through the label PATCH, independent of the profile name", async () => {
    const rtl = await renderPanel();
    rtl.fireEvent.change(rtl.screen.getByTestId("edit-conn-label"), { target: { value: "Júlia ~ One Consultoria" } });
    rtl.fireEvent.click(rtl.screen.getByTestId("btn-save"));
    expect(updateMutate.mock.calls[0][0]).toEqual({ id: "conn-1", body: { label: "Júlia ~ One Consultoria" } });
    expect(profileMutate).not.toHaveBeenCalled();
  });

  it("blocks an empty profile name", async () => {
    const rtl = await renderPanel();
    rtl.fireEvent.change(rtl.screen.getByTestId("edit-conn-profile-name"), { target: { value: "  " } });
    expect((rtl.screen.getByTestId("btn-save-profile-name") as HTMLButtonElement).disabled).toBe(true);
  });
});
