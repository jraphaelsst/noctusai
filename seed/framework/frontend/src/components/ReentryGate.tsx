/**
 * The unauthenticated branch of `createProductApp` for SSO products (SSO session lifecycle, slice S4).
 *
 * Decides — once the auth bootstrap has settled and there is NO session — between the product Landing and a
 * trip to core's central login. The rules live in `@noctusai/lib` `reentry.ts` (decision table, loop guard,
 * multi-tab lock); this component only wires them to React. It never fetches anything: the authenticated route
 * tree is assembled by `AppContent` after `/api/auth/me` resolves, and this gate renders only before that.
 */
import { Suspense, useEffect, useMemo, useState, type ComponentType, type LazyExoticComponent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import {
  applyLoginRequiredBounce,
  buildCoreEntryUrl,
  clearReentryTrips,
  decideEntry,
  enterViaCore,
  isLeaving,
  isLoginRequiredBounce,
  readEntryMarker,
  sanitizeNextPath,
  wasSessionLost,
  whenVisible,
  type EntryDecision,
} from "@noctusai/lib";
import { PageSkeleton } from "@noctusai/lib/design-system";

/** Lets a Sair in a sibling tab stamp `signed-out` before this tab (which got the broadcast) reads the marker. */
export const REENTRY_SETTLE_MS = 250;

export type CoreNavigate = (url: string) => void;
export const defaultCoreNavigate: CoreNavigate = (url) => window.location.replace(url);

export interface ReentryGateProps {
  slug: string;
  coreUrl: string;
  Landing?: LazyExoticComponent<ComponentType<any>>;
  navigate?: CoreNavigate;
}

/** Shown when the loop guard stops the automatic round trips, or a Landing-less product was signed out. */
function EntrarFallback({ url, onClick }: { url: string; onClick: () => void }) {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-xl font-semibold">Entre para continuar</h1>
      <p className="text-sm text-muted-foreground">Sua sessão não pôde ser retomada automaticamente. Entre pelo NoctusAI para voltar.</p>
      <a
        href={url}
        onClick={onClick}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
      >
        Entrar
      </a>
    </main>
  );
}

export function ReentryGate({ slug, coreUrl, Landing, navigate = defaultCoreNavigate }: ReentryGateProps) {
  const { pathname, search, hash } = useLocation();
  // Both are facts about how this mount came to be; they must not change if the URL later does.
  const [bounced] = useState(() => isLoginRequiredBounce(hash));
  const [phase] = useState<"fresh" | "lost">(() => (wasSessionLost() ? "lost" : "fresh"));
  const [settled, setSettled] = useState(phase === "fresh");
  const [stopped, setStopped] = useState(false);

  // Core said "no session": remember it, drop the fragment from the URL, no error.
  useEffect(() => {
    if (!bounced) return;
    applyLoginRequiredBounce(hash);
    window.history.replaceState(window.history.state, "", pathname + search);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (settled) return;
    const t = setTimeout(() => setSettled(true), REENTRY_SETTLE_MS);
    return () => clearTimeout(t);
  }, [settled]);

  const decision: EntryDecision | null = useMemo(() => {
    if (bounced) return { kind: "landing" };
    if (!settled) return null;
    // Voltar (S5): this tab revoked its own session and is already navigating to core. Stay still;
    // re-entering here would launch the product again and undo the Voltar.
    if (isLeaving()) return null;
    const marker = readEntryMarker();
    const d = decideEntry({ phase, pathname, marker });
    // No Landing to show at "/": a stranger goes straight to core's login; a signed-out visitor clicks "Entrar".
    if (d.kind === "landing" && !Landing && marker !== "signed-out") return { kind: "core", prompt: "login" };
    return d;
  }, [bounced, settled, phase, pathname, Landing]);

  const next = pathname + search;
  const coreDecision = decision?.kind === "core" ? decision : null;
  const entryUrl = buildCoreEntryUrl({ coreUrl, slug, next, prompt: coreDecision?.prompt ?? "login" });

  useEffect(() => {
    if (!coreDecision) return;
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let wait = whenVisible();
    const run = async () => {
      // A hidden tab does nothing: it waits to be looked at.
      if (!(await wait.promise) || cancelled) return;
      const out = await enterViaCore(entryUrl, slug, { navigate });
      if (cancelled) return;
      if (out.status === "loop") setStopped(true);
      else if (out.status === "hidden") {
        wait = whenVisible();
        void run();
      } else if (out.status === "deferred") {
        // A sibling window is entering: its SIGNED_IN broadcast unmounts this gate. Re-check only if it never does.
        retry = setTimeout(() => {
          wait = whenVisible();
          void run();
        }, out.retryInMs);
      }
    };
    void run();
    return () => {
      cancelled = true;
      wait.cancel();
      if (retry) clearTimeout(retry);
    };
  }, [coreDecision?.prompt, entryUrl, slug, navigate]);

  if (stopped || (decision?.kind === "landing" && !Landing)) {
    const loginUrl = buildCoreEntryUrl({ coreUrl, slug, next, prompt: "login" });
    return <EntrarFallback url={loginUrl} onClick={() => clearReentryTrips()} />;
  }
  if (decision?.kind === "landing" && pathname === "/" && Landing) {
    return (
      <Suspense fallback={<PageSkeleton />}>
        <Landing />
      </Suspense>
    );
  }
  if (decision && decision.kind !== "core") return <Navigate to="/" replace />;
  return <PageSkeleton />;
}

export interface CoreRouteRedirectProps {
  slug: string;
  coreUrl: string;
  route: "/login" | "/esqueci-senha";
  /** Fallback `next` (the deep link the visitor was after) when the URL carries none. */
  fallbackNext?: () => string | null;
  navigate?: CoreNavigate;
}

/** Seed-owned `/login` and `/forgot-password`: credentials are collected at core only. */
export function CoreRouteRedirect({ slug, coreUrl, route, fallbackNext, navigate = defaultCoreNavigate }: CoreRouteRedirectProps) {
  const { search } = useLocation();
  const next = sanitizeNextPath(new URLSearchParams(search).get("next")) ?? fallbackNext?.() ?? null;
  const url = buildCoreEntryUrl({ coreUrl, slug, next, route });
  useEffect(() => {
    navigate(url);
  }, [url, navigate]);
  return <PageSkeleton />;
}
