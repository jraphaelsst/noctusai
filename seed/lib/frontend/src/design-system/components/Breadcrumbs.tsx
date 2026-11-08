/**
 * Breadcrumbs — the seed route-mapping header ("Administração / Comercial / Produtos").
 *
 * Mounted ONCE by the seed `Header`, fed by the `AppShell` nav registry, so
 * every product gets it with zero per-product code. Does two things:
 *   1. says where the user is (last crumb = current page, `aria-current="page"`);
 *   2. lets them navigate: route crumbs are links; GROUP crumbs (no page of
 *      their own) open a menu with the group's pages for sideways jumps.
 *
 * Accessibility: `<nav aria-label="Você está em">` + `<ol>`; separators are
 * aria-hidden; group menus are real menu buttons (aria-haspopup, aria-expanded,
 * arrows/Home/End move, Esc closes and returns focus to the button). Below
 * 640px the trail collapses to "… / Parent / Current"; the ellipsis opens the
 * full path.
 */
import { createContext, useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, matchPath, useInRouterContext, useLocation, UNSAFE_DataRouterStateContext } from "react-router-dom";

import {
  buildBreadcrumbTrail,
  resolveCrumb,
  type Crumb,
  type CrumbMenuEntry,
  type ResolvedRouteCrumb,
  type RouteCrumbSpec,
} from "./breadcrumb-trail";
import type { NavGroup, NavItem } from "./Sidebar";

/** What the shell knows about the app's navigation; empty outside an `AppShell`. */
export interface BreadcrumbRegistry {
  navGroups: NavGroup[];
  standaloneItems?: NavItem[];
  /** Detail-route crumbs for apps on a non-data router (data routers use `handle.crumb`). */
  routeCrumbs?: RouteCrumbSpec[];
}

export const BreadcrumbRegistryContext = createContext<BreadcrumbRegistry | null>(null);

const NARROW_QUERY = "(max-width: 639px)";

function useIsNarrow(): boolean {
  const get = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(NARROW_QUERY).matches;
  const [narrow, setNarrow] = useState(get);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(NARROW_QUERY);
    const onChange = () => setNarrow(mq.matches);
    onChange();
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);
  return narrow;
}

/** `handle.crumb` of the data-router matches, resolved. Empty on a non-data router. */
function useHandleCrumbs(): ResolvedRouteCrumb[] {
  const state = useContext(UNSAFE_DataRouterStateContext);
  return useMemo(() => {
    const out: ResolvedRouteCrumb[] = [];
    for (const m of state?.matches ?? []) {
      const crumb = (m.route as { handle?: { crumb?: unknown } }).handle?.crumb;
      if (crumb === undefined) continue;
      out.push({
        pathname: m.pathname,
        label: resolveCrumb(crumb as never, {
          params: m.params,
          pathname: m.pathname,
          data: state?.loaderData?.[m.route.id],
        }),
      });
    }
    return out;
  }, [state]);
}

function useSpecCrumbs(specs: RouteCrumbSpec[] | undefined, pathname: string): ResolvedRouteCrumb[] {
  return useMemo(() => {
    const out: ResolvedRouteCrumb[] = [];
    for (const s of specs ?? []) {
      const m = matchPath({ path: s.path, end: false }, pathname);
      if (m) out.push({ pathname: m.pathname, label: resolveCrumb(s.crumb, { params: m.params, pathname: m.pathname }) });
    }
    return out;
  }, [specs, pathname]);
}

function Separator() {
  return (
    <li aria-hidden="true" className="select-none text-muted-foreground/60">
      /
    </li>
  );
}

interface MenuButtonProps {
  label: string;
  entries: CrumbMenuEntry[];
  currentHref: string;
}

/** A crumb that opens a menu of pages. Disclosure-menu pattern with roving focus. */
function CrumbMenu({ label, entries, currentHref }: MenuButtonProps) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);
  const rootRef = useRef<HTMLLIElement>(null);
  const menuId = useId();

  const items = () => Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);

  useEffect(() => {
    if (open) (items().find((el) => el.getAttribute("aria-current") === "page") ?? items()[0])?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) buttonRef.current?.focus();
  };

  const onMenuKey = (e: React.KeyboardEvent) => {
    const list = items();
    const i = list.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") {
      e.preventDefault();
      close(true);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      list[(i + 1) % list.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      list[(i - 1 + list.length) % list.length]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      list[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      list[list.length - 1]?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  const onButtonKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" && !open) {
      e.preventDefault();
      setOpen(true);
    }
  };

  return (
    <li ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onButtonKey}
        className="rounded px-1 hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {label}
      </button>
      {open && (
        <ul
          id={menuId}
          ref={menuRef}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKey}
          className="absolute left-0 top-full z-50 mt-1 max-h-80 min-w-48 overflow-auto rounded-md border border-border bg-popover p-1 text-sm text-popover-foreground shadow-md"
        >
          {entries.map((e, idx) =>
            e.kind === "heading" ? (
              <li key={`h-${idx}`} role="presentation" className="px-2 pb-1 pt-2 text-xs font-medium text-muted-foreground">
                {e.label}
              </li>
            ) : (
              <li key={e.href} role="none">
                <Link
                  role="menuitem"
                  to={e.href}
                  tabIndex={-1}
                  aria-current={e.href === currentHref ? "page" : undefined}
                  onClick={() => close(false)}
                  className="block rounded px-2 py-1.5 hover:bg-accent focus-visible:bg-accent focus-visible:outline-none aria-[current=page]:font-semibold"
                >
                  {e.label}
                </Link>
              </li>
            ),
          )}
        </ul>
      )}
    </li>
  );
}

function crumbEntries(crumbs: Crumb[]): CrumbMenuEntry[] {
  return crumbs.map((c) =>
    c.href ? { kind: "item" as const, label: c.label, href: c.href } : { kind: "heading" as const, label: c.label },
  );
}

/**
 * Renders nothing outside a router: the seed `Header` mounts this, and a Header
 * consumer without a router (tests, standalone pages) must not crash on `useLocation`.
 */
export function Breadcrumbs({ className }: { className?: string }) {
  return useInRouterContext() ? <RoutedBreadcrumbs className={className} /> : null;
}

function RoutedBreadcrumbs({ className }: { className?: string }) {
  const registry = useContext(BreadcrumbRegistryContext);
  const { pathname } = useLocation();
  const handleCrumbs = useHandleCrumbs();
  const specCrumbs = useSpecCrumbs(registry?.routeCrumbs, pathname);
  const narrow = useIsNarrow();

  const trail = useMemo(
    () =>
      registry
        ? buildBreadcrumbTrail({
            navGroups: registry.navGroups,
            standaloneItems: registry.standaloneItems,
            pathname,
            routeCrumbs: [...handleCrumbs, ...specCrumbs],
          })
        : [],
    [registry, pathname, handleCrumbs, specCrumbs],
  );

  if (trail.length === 0) return null;

  const collapsed = narrow && trail.length > 2;
  const hidden = collapsed ? trail.slice(0, trail.length - 2) : [];
  const visible = collapsed ? trail.slice(-2) : trail;
  const currentHref = pathname;

  const renderCrumb = (c: Crumb) => {
    if (c.current) {
      return (
        <li key={c.key} aria-current="page" className="min-w-0 truncate font-semibold text-foreground">
          {c.label}
        </li>
      );
    }
    if (c.menu && c.menu.length > 0) {
      return <CrumbMenu key={c.key} label={c.label} entries={c.menu} currentHref={currentHref} />;
    }
    if (c.href) {
      return (
        <li key={c.key} className="min-w-0 truncate">
          <Link to={c.href} className="rounded px-1 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {c.label}
          </Link>
        </li>
      );
    }
    return (
      <li key={c.key} className="min-w-0 truncate">
        {c.label}
      </li>
    );
  };

  const parts: React.ReactNode[] = [];
  if (collapsed) {
    parts.push(<CrumbMenu key="ellipsis" label="…" entries={crumbEntries(hidden)} currentHref={currentHref} />);
  }
  visible.forEach((c, i) => {
    if (i > 0 || collapsed) parts.push(<Separator key={`sep-${c.key}`} />);
    parts.push(renderCrumb(c));
  });

  return (
    <nav aria-label="Você está em" className={className ?? "min-w-0 text-[13px] text-muted-foreground"}>
      <ol className="flex min-w-0 items-center gap-1.5 whitespace-nowrap">{parts}</ol>
    </nav>
  );
}
