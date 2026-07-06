/**
 * IgConteudo.test.tsx — Instagram "Conteúdo" subtab (publish form + media grid).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseActiveMetaAccountId = vi.fn();
const mockUseIgMedia = vi.fn();
const mockUseIgPublish = vi.fn();

vi.mock("@/hooks/useMeta", () => ({
  isAppReviewGate: (x: unknown) =>
    !!x && typeof x === "object" && (x as any).requires_app_review === true,
  useActiveMetaAccountId: mockUseActiveMetaAccountId,
  useIgMedia: mockUseIgMedia,
  useIgPublish: mockUseIgPublish,
}));

vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...p }: any) => <div {...p}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardDescription: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...p }: any) => <div {...p}>{children}</div>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...p }: any) => <button {...p}>{children}</button>,
}));
vi.mock("@/components/ui/input", () => ({
  Input: (p: any) => <input {...p} />,
}));
vi.mock("@/components/ui/textarea", () => ({
  Textarea: (p: any) => <textarea {...p} />,
}));
vi.mock("@/components/ui/label", () => ({
  Label: ({ children, ...p }: any) => <label {...p}>{children}</label>,
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ "data-testid": dt }: any) => <div data-testid={dt ?? "skeleton"} />,
}));
vi.mock("@/components/ui/select", () => ({
  Select: ({ children, value, onValueChange }: any) => (
    <select value={value} onChange={(e) => onValueChange(e.target.value)} data-testid="select">
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: any) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: any) => <>{children}</>,
  SelectItem: ({ children, value }: any) => <option value={value}>{children}</option>,
}));
vi.mock("lucide-react", () => ({
  CircleAlert: () => <span data-testid="icon-alert" />,
  CircleCheck: () => <span data-testid="icon-check" />,
  Loader2: () => <span data-testid="icon-loader" />,
  Send: () => null,
  ShieldAlert: () => <span data-testid="icon-shield" />,
}));

function setDefaults() {
  mockUseActiveMetaAccountId.mockReturnValue("acc-1");
  mockUseIgMedia.mockReturnValue({ data: { media: [] }, isLoading: false, isError: false });
  mockUseIgPublish.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false, data: undefined });
}

beforeEach(() => setDefaults());

async function renderPage() {
  const React = (await import("react")).default;
  const { default: IgConteudo } = await import("./IgConteudo");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(IgConteudo)), fireEvent: rtl.fireEvent };
}

describe("IgConteudo — no account selected", () => {
  it("shows the select-an-account prompt", async () => {
    mockUseActiveMetaAccountId.mockReturnValue(null);
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-content-no-account")).toBeTruthy();
  });
});

describe("IgConteudo — media grid states", () => {
  it("renders a loading grid", async () => {
    mockUseIgMedia.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-content-grid-loading")).toBeTruthy();
  });

  it("renders an error state", async () => {
    mockUseIgMedia.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-content-grid-error")).toBeTruthy();
  });

  it("renders an empty state", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-content-grid-empty")).toBeTruthy();
  });

  it("renders a media grid on success", async () => {
    mockUseIgMedia.mockReturnValue({
      data: { media: [{ id: "1", thumbnail_url: "http://x/1.jpg", caption: "oi" }] },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-content-grid")).toBeTruthy();
  });
});

describe("IgConteudo — publish form", () => {
  it("submits the publish mutation", async () => {
    const mutate = vi.fn();
    mockUseIgPublish.mockReturnValue({ mutate, isPending: false, isError: false, data: undefined });
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.change(getByTestId("ig-publish-urls"), { target: { value: "http://x/1.jpg" } });
    fireEvent.submit(getByTestId("ig-publish-form"));
    expect(mutate).toHaveBeenCalled();
  });

  it("shows the error state on publish failure", async () => {
    mockUseIgPublish.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: true, data: undefined });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-publish-error")).toBeTruthy();
  });

  it("shows the App Review gate instead of a fake success", async () => {
    mockUseIgPublish.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      data: { requires_app_review: true, error: "Escopo pendente" },
    });
    const { getByTestId, getByText } = await renderPage();
    expect(getByTestId("meta-app-review-gate")).toBeTruthy();
    expect(getByText("Escopo pendente")).toBeTruthy();
  });

  it("shows a success confirmation on a real publish", async () => {
    mockUseIgPublish.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      data: { id: "media-1", permalink: "http://x" },
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-publish-success")).toBeTruthy();
  });
});
