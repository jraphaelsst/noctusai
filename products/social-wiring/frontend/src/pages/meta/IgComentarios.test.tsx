/**
 * IgComentarios.test.tsx — Instagram "Comentários" subtab.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseActiveMetaAccountId = vi.fn();
const mockUseIgMedia = vi.fn();
const mockUseIgComments = vi.fn();
const mockUseIgReplyComment = vi.fn();
const mockUseIgHideComment = vi.fn();
const mockUseIgDeleteComment = vi.fn();

vi.mock("@/hooks/useMeta", () => ({
  isAppReviewGate: (x: unknown) =>
    !!x && typeof x === "object" && (x as any).requires_app_review === true,
  useActiveMetaAccountId: mockUseActiveMetaAccountId,
  useIgMedia: mockUseIgMedia,
  useIgComments: mockUseIgComments,
  useIgReplyComment: mockUseIgReplyComment,
  useIgHideComment: mockUseIgHideComment,
  useIgDeleteComment: mockUseIgDeleteComment,
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
  mockUseIgMedia.mockReturnValue({
    data: { media: [{ id: "media-1", caption: "post 1" }] },
    isPending: false,
    isError: false,
  });
  mockUseIgComments.mockReturnValue({ data: { comments: [] }, isPending: false, isError: false });
  mockUseIgReplyComment.mockReturnValue(noopMutation());
  mockUseIgHideComment.mockReturnValue(noopMutation());
  mockUseIgDeleteComment.mockReturnValue(noopMutation());
}

beforeEach(() => setDefaults());

async function renderPage() {
  const React = (await import("react")).default;
  const { default: IgComentarios } = await import("./IgComentarios");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(IgComentarios)), fireEvent: rtl.fireEvent };
}

describe("IgComentarios — no account selected", () => {
  it("shows the select-an-account prompt", async () => {
    mockUseActiveMetaAccountId.mockReturnValue(null);
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-comments-no-account")).toBeTruthy();
  });
});

describe("IgComentarios — media selector", () => {
  it("shows a no-media message when there are no posts", async () => {
    mockUseIgMedia.mockReturnValue({ data: { media: [] }, isPending: false, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-comments-no-media")).toBeTruthy();
  });
});

describe("IgComentarios — comments list states", () => {
  it("renders a loading state", async () => {
    mockUseIgComments.mockReturnValue({ data: undefined, isPending: true, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-comments-loading")).toBeTruthy();
  });

  it("renders an error state", async () => {
    mockUseIgComments.mockReturnValue({ data: undefined, isPending: false, isError: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-comments-error")).toBeTruthy();
  });

  it("renders an empty state", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-comments-empty")).toBeTruthy();
  });

  it("renders the comments list on success and replies", async () => {
    mockUseIgComments.mockReturnValue({
      data: { comments: [{ id: "c1", text: "oi", from_username: "fulano" }] },
      isPending: false,
      isError: false,
    });
    const reply = vi.fn();
    mockUseIgReplyComment.mockReturnValue({ mutate: reply, isPending: false, data: undefined });
    const { getByTestId, fireEvent } = await renderPage();
    expect(getByTestId("ig-comments-list")).toBeTruthy();
    fireEvent.change(getByTestId("ig-comment-reply-input"), { target: { value: "obrigado" } });
    fireEvent.submit(getByTestId("ig-comment-reply-form"));
    expect(reply).toHaveBeenCalledWith({ message: "obrigado" }, expect.anything());
  });

  it("shows the App Review gate on a gated hide action", async () => {
    mockUseIgComments.mockReturnValue({
      data: { comments: [{ id: "c1", text: "oi" }] },
      isPending: false,
      isError: false,
    });
    mockUseIgHideComment.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      data: { requires_app_review: true, error: "Revisão pendente" },
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("meta-app-review-gate")).toBeTruthy();
  });
});
