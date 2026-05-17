/**
 * Example page — placeholder for the new product to fill in.
 *
 * This page is the **canonical frontend skeleton** every scaffolded
 * product inherits. It demonstrates:
 *
 *   - useAuthStore() for the current user / org context
 *   - The shared design language (rounded-lg, border-border, bg-card,
 *     text-foreground, text-muted-foreground) — never hand-roll Tailwind
 *     colors; always use the design-token classes so dark mode + theme
 *     overrides work out of the box.
 *   - A blank page wired to a route in App.tsx + a nav entry. The
 *     backend counterpart is `app/routers/example_router.py`.
 *
 * TODO(new-product): rename `Example` → your domain page, replace this
 * body with real content, and (likely) call the backend via a hook
 * like `useExample()` (the canonical shape lives in
 * `products/social-wiring/frontend/src/hooks/useVideos.ts`).
 */
import { useAuthStore } from "@noctusai/seed/infra";
import { Boxes, Sparkles } from "lucide-react";

export default function Example() {
  const { user } = useAuthStore();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Boxes className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Example</h1>
          <p className="text-sm text-muted-foreground">
            Placeholder route — replace with your domain page.
          </p>
        </div>
      </div>

      {/* Empty-state card */}
      <div className="rounded-lg border border-border border-dashed bg-card p-8 text-center space-y-3">
        <Sparkles className="h-8 w-8 mx-auto text-primary" />
        <h2 className="text-lg font-semibold text-foreground">
          Nothing here yet
        </h2>
        <p className="text-sm text-muted-foreground max-w-md mx-auto">
          This page is wired to <code className="rounded bg-muted px-1.5 py-0.5 text-xs">/example</code>{" "}
          via <code className="rounded bg-muted px-1.5 py-0.5 text-xs">App.tsx</code>. The
          backend mirror lives at <code className="rounded bg-muted px-1.5 py-0.5 text-xs">/api/example</code>.
          Replace this card with your real UI; rename <code>Example</code> everywhere; remove the nav
          entry if your product has a different navigation shape.
        </p>
        {user?.email && (
          <p className="text-xs text-muted-foreground">
            Logged in as <span className="font-mono">{user.email}</span>
          </p>
        )}
      </div>
    </div>
  );
}
