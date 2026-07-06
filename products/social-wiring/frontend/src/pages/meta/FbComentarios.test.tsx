/**
 * FbComentarios.test.tsx — Facebook "Comentários" subtab.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseActiveMetaAccountId = vi.fn();
const mockUseMetaContext = vi.fn();
const mockUseFbPosts = vi.fn();
const mockUseFbComments = vi.fn();
const mockUseFbReplyComment = vi.fn();
const mockUseFbHideComment = vi.fn();
const mockUseFbDeleteComment = vi.fn();

vi.mock("@/hooks/useMeta", () => ({
  isAppReviewGate: (x: unknown) =>
    !!x && typeof x === "object" && (x as any).requires_app_review === true,
  useActiveMetaAccountId: mockUseActiveMetaAccountId,
  useMetaContext: mockUseMetaContext,
  useFbPosts: mockUseFbPosts,
  useFbComments: mockUseFbComments,
  useFbReplyComment: mockUseFbReplyComment,
  useFbHideComment: mockUseFbHideComment,
  useFbDeleteComment: mockUseFbDeleteComment,
}));

vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...p }: any) => <div {...p}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...p }: any) => <div {...p}>{children}</div>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...p }: any) => <button {...p}>{children}</button>,
}));
vi.mock("@/components/ui/input", () => ({
  Input: (p: any) => <input {...p} />,
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
  EyeOff: () => null,
  Loader2: () => null,
  Send: () => null,
  Trash2: () => null,
  ShieldAlert: () => null,
}));

const noopMutation = () => ({ mutate: vi.fn(), isPending: false, data: undefined });

function setDefaults() {
  mockUseActiveMetaAccountId.mockReturnValue("acc-1");
  mockUseMetaContext.mockReturnValue({
    data: { instagram: null, pages: [{ id: "page-1", name: "Minha Página" }], user: null },
    isLoading: false,
    isError: false,
  });
  mockUseFbPosts.mockReturnValue({
    data: { posts: [{ id: "post-1", message: "publicação 1" }] },
    isLoading: false,
    isError: false,
  });
  mockUseFbComments.mockReturnValue({ data: { comments: [] }, isLoading: false, isError: false });
  mockUseFbReplyComment.mockReturnValue(noopMutation());
  mockUseFbHideComment.mockReturnValue(noopMutation());
  mockUseFbDeleteComment.mockReturnValue(noopMutation());
}

beforeEach(() => setDefaults());

async function renderPage() {
  const React = (await import("react")).default;
  const { default: FbComentarios } = await import("./FbComentarios");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(FbComentarios)), fireEvent: rtl.fireEvent };
}

describe("FbComentarios — no account selected", () => {
  it("shows the select-an-account prompt", async () => {
    mockUseActiveMetaAccountId.mockReturnValue(null);
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-comments-no-account")).toBeTruthy();
  });
});

describe("FbComentarios — no pages", () => {
  it("shows the no-pages state", async () => {
    mockUseMetaContext.mockReturnValue({
      data: { instagram: null, pages: [], user: null },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-no-pages")).toBeTruthy();
  });
});

describe("FbComentarios — no posts", () => {
  it("shows the no-posts message", async () => {
    mockUseFbPosts.mockReturnValue({ data: { posts: [] }, isLoading: false, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-comments-no-posts")).toBeTruthy();
  });
});

describe("FbComentarios — comments list states", () => {
  it("renders a loading state", async () => {
    mockUseFbComments.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-comments-loading")).toBeTruthy();
  });

  it("renders an error state", async () => {
    mockUseFbComments.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-comments-error")).toBeTruthy();
  });

  it("renders an empty state", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-comments-empty")).toBeTruthy();
  });

  it("renders the comments list on success and replies", async () => {
    mockUseFbComments.mockReturnValue({
      data: { comments: [{ id: "c1", text: "oi", from_username: "fulano" }] },
      isLoading: false,
      isError: false,
    });
    const reply = vi.fn();
    mockUseFbReplyComment.mockReturnValue({ mutate: reply, isPending: false, data: undefined });
    const { getByTestId, fireEvent } = await renderPage();
    expect(getByTestId("fb-comments-list")).toBeTruthy();
    fireEvent.change(getByTestId("fb-comment-reply-input"), { target: { value: "valeu" } });
    fireEvent.submit(getByTestId("fb-comment-reply-form"));
    expect(reply).toHaveBeenCalledWith({ message: "valeu" }, expect.anything());
  });

  it("shows the App Review gate on a gated delete action", async () => {
    mockUseFbComments.mockReturnValue({
      data: { comments: [{ id: "c1", text: "oi" }] },
      isLoading: false,
      isError: false,
    });
    mockUseFbDeleteComment.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      data: { requires_app_review: true, error: "Revisão pendente" },
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("meta-app-review-gate")).toBeTruthy();
  });
});
