/**
 * FbConteudo.test.tsx — Facebook "Conteúdo" subtab (publish form + posts list).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseActiveMetaAccountId = vi.fn();
const mockUseMetaContext = vi.fn();
const mockUseFbPosts = vi.fn();
const mockUseFbPublish = vi.fn();

vi.mock("@/hooks/useMeta", () => ({
  isAppReviewGate: (x: unknown) =>
    !!x && typeof x === "object" && (x as any).requires_app_review === true,
  useActiveMetaAccountId: mockUseActiveMetaAccountId,
  useMetaContext: mockUseMetaContext,
  useFbPosts: mockUseFbPosts,
  useFbPublish: mockUseFbPublish,
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
  SelectTrigger: ({ children, "data-testid": dt }: any) => <div data-testid={dt}>{children}</div>,
  SelectValue: () => null,
  SelectContent: ({ children }: any) => <>{children}</>,
  SelectItem: ({ children, value }: any) => <option value={value}>{children}</option>,
}));
vi.mock("lucide-react", () => ({
  CircleAlert: () => <span data-testid="icon-alert" />,
  CircleCheck: () => <span data-testid="icon-check" />,
  Loader2: () => null,
  Send: () => null,
  ShieldAlert: () => null,
}));

function setDefaults() {
  mockUseActiveMetaAccountId.mockReturnValue("acc-1");
  mockUseMetaContext.mockReturnValue({
    data: { instagram: null, pages: [{ id: "page-1", name: "Minha Página" }], user: null },
    isPending: false,
    isError: false,
  });
  mockUseFbPosts.mockReturnValue({ data: { posts: [] }, isPending: false, isError: false });
  mockUseFbPublish.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false, data: undefined });
}

beforeEach(() => setDefaults());

async function renderPage() {
  const React = (await import("react")).default;
  const { default: FbConteudo } = await import("./FbConteudo");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(FbConteudo)), fireEvent: rtl.fireEvent };
}

describe("FbConteudo — no account selected", () => {
  it("shows the select-an-account prompt", async () => {
    mockUseActiveMetaAccountId.mockReturnValue(null);
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-content-no-account")).toBeTruthy();
  });
});

describe("FbConteudo — no pages", () => {
  it("shows the no-pages state", async () => {
    mockUseMetaContext.mockReturnValue({
      data: { instagram: null, pages: [], user: null },
      isPending: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-no-pages")).toBeTruthy();
  });
});

describe("FbConteudo — posts list states", () => {
  it("renders a loading state", async () => {
    mockUseFbPosts.mockReturnValue({ data: undefined, isPending: true, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-posts-loading")).toBeTruthy();
  });

  it("renders an error state", async () => {
    mockUseFbPosts.mockReturnValue({ data: undefined, isPending: false, isError: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-posts-error")).toBeTruthy();
  });

  it("renders an empty state", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-posts-empty")).toBeTruthy();
  });

  it("renders the posts list on success", async () => {
    mockUseFbPosts.mockReturnValue({
      data: { posts: [{ id: "p1", message: "oi", likes_count: 3, comments_count: 1 }] },
      isPending: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-posts-list")).toBeTruthy();
  });
});

describe("FbConteudo — publish form", () => {
  it("submits the publish mutation", async () => {
    const mutate = vi.fn();
    mockUseFbPublish.mockReturnValue({ mutate, isPending: false, isError: false, data: undefined });
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.change(getByTestId("fb-publish-message"), { target: { value: "olá pessoal" } });
    fireEvent.submit(getByTestId("fb-publish-form"));
    expect(mutate).toHaveBeenCalled();
  });

  it("shows the App Review gate instead of a fake success", async () => {
    mockUseFbPublish.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      data: { requires_app_review: true, error: "Revisão pendente" },
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("meta-app-review-gate")).toBeTruthy();
  });

  it("shows a success confirmation on a real publish", async () => {
    mockUseFbPublish.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      data: { id: "post-1" },
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-publish-success")).toBeTruthy();
  });
});
