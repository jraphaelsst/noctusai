import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, Menu, Monitor, Moon, Sun, X } from "lucide-react";
import { Button } from "../design-system/ui/Button";
import { cn } from "../utils";
import { HIDDEN_ATTR, LandingIcon, linkButtonClass, wrapClass } from "./shared";

export interface NavLink { label: string; href: string }
export interface NavProduct {
  nome: string;
  href: string;
  /** Short public description; omitted when the product has none. */
  descricao?: string | null;
  /** Registered lucide icon name. */
  icone?: string | null;
}
export type ThemeChoice = "system" | "light" | "dark";

export interface LandingNavProps {
  brand: { label: string; href: string; ariaLabel?: string; mark?: ReactNode };
  /** Links after the products disclosure (Soluções, Preços, …). */
  links: NavLink[];
  /**
   * Only the "disponível" products: derived from the catalog, never hand-kept. The "Produtos" disclosure
   * (and the drawer's Produtos link) renders only when this prop is passed; omit it for a single-product site.
   */
  products?: NavProduct[];
  productsLabel?: string;
  /** Target of the "all products" entry (menu footer and the mobile drawer's Produtos link). */
  allProductsHref?: string;
  loginAction?: NavLink;
  primaryAction: NavLink;
  /** Language switch link (e.g. EN). Rendered with `lang` so it is pronounced correctly. */
  languageLink?: { label: string; href: string; lang: string; ariaLabel: string };
  /** Theme switch; omitted when the page has none. */
  themeSwitch?: { value: ThemeChoice; onChange: (next: ThemeChoice) => void };
  /** Show `loginAction` as a ghost button at every width (default: large screens only; the drawer holds it below). */
  loginAlwaysVisible?: boolean;
  /** Show `primaryAction` on large screens only (the drawer's links carry the same destination). Default false. */
  primaryActionDesktopOnly?: boolean;
}

const THEMES: { value: ThemeChoice; label: string; Icon: typeof Sun }[] = [
  { value: "system", label: "Tema do sistema", Icon: Monitor },
  { value: "light", label: "Tema claro", Icon: Sun },
  { value: "dark", label: "Tema escuro", Icon: Moon },
];

/** 3-state theme control (sistema / claro / escuro). A group of toggle buttons with `aria-pressed`. */
export function ThemeSwitch({ value, onChange }: NonNullable<LandingNavProps["themeSwitch"]>) {
  return (
    <div role="group" aria-label="Tema" className="inline-flex rounded-md border border-input p-0.5">
      {THEMES.map(({ value: v, label, Icon }) => (
        <button
          key={v}
          type="button"
          aria-label={label}
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={cn(
            "inline-flex h-7 w-7 items-center justify-center rounded-sm focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
            value === v ? "bg-foreground text-background" : "text-muted-foreground hover:bg-accent",
          )}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

/**
 * Public site header: brand, a "Produtos" disclosure (button + `aria-expanded`,
 * NOT a menu role), plain links, and a mobile drawer. No breadcrumb: that bar
 * belongs to the authenticated app. Escape closes whichever is open and returns
 * focus to its button; a click outside closes the disclosure.
 */
export function LandingNav({
  brand, links, products, productsLabel = "Produtos", allProductsHref,
  loginAction, primaryAction, languageLink, themeSwitch, loginAlwaysVisible = false, primaryActionDesktopOnly = false,
}: LandingNavProps) {
  const productsHref = products !== undefined ? allProductsHref : undefined;
  const [menuOpen, setMenuOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuId = useId();
  const drawerId = useId();
  const menuBtn = useRef<HTMLButtonElement>(null);
  const drawerBtn = useRef<HTMLButtonElement>(null);
  const menuWrap = useRef<HTMLDivElement>(null);

  // Document-level listeners sync with the browser (an external system).
  useEffect(() => {
    if (!menuOpen && !drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (menuOpen) {
        setMenuOpen(false);
        menuBtn.current?.focus();
      }
      if (drawerOpen) {
        setDrawerOpen(false);
        drawerBtn.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (menuOpen && menuWrap.current && !menuWrap.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [menuOpen, drawerOpen]);

  const ghost = linkButtonClass("ghost", "md");

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-card">
      <div className={`${wrapClass} flex h-14 items-center gap-4`}>
        <a href={brand.href} aria-label={brand.ariaLabel ?? brand.label} className="inline-flex items-center gap-2 rounded-md font-semibold text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring">
          {brand.mark}
          {brand.label}
        </a>

        <nav aria-label="Principal" className="hidden items-center gap-1 lg:flex">
          {productsHref && products ? (
          <div ref={menuWrap} className="relative">
            <Button
              ref={menuBtn}
              variant="ghost"
              aria-expanded={menuOpen}
              aria-controls={menuId}
              onClick={() => setMenuOpen((o) => !o)}
            >
              {productsLabel}
              <ChevronDown className="h-4 w-4" aria-hidden="true" />
            </Button>
            <div
              id={menuId}
              hidden={!menuOpen}
              className={cn(
                "absolute left-0 top-full mt-1 grid w-80 gap-1 rounded-lg border border-border bg-popover p-2 shadow-lg",
                HIDDEN_ATTR,
              )}
            >
              {products.map((p) => (
                <a key={p.nome} href={p.href} onClick={() => setMenuOpen(false)} className="flex items-start gap-3 rounded-md p-2 hover:bg-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring">
                  <LandingIcon name={p.icone} className="mt-0.5 h-5 w-5 shrink-0" />
                  <span className="flex flex-col">
                    <strong className="text-sm text-foreground">{p.nome}</strong>
                    {p.descricao ? <small className="text-xs text-muted-foreground">{p.descricao}</small> : null}
                  </span>
                </a>
              ))}
              <a href={productsHref} onClick={() => setMenuOpen(false)} className="flex flex-col rounded-md p-2 hover:bg-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring">
                <strong className="text-sm text-foreground">Ver todos os produtos</strong>
                <small className="text-xs text-muted-foreground">Inclui os que estão em construção ou em pausa</small>
              </a>
            </div>
          </div>
          ) : null}
          {links.map((l) => (
            <a key={l.href + l.label} href={l.href} className={ghost}>{l.label}</a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {languageLink ? (
            <a href={languageLink.href} lang={languageLink.lang} aria-label={languageLink.ariaLabel} className={cn(linkButtonClass("ghost", "sm"), "hidden lg:inline-flex")}>
              {languageLink.label}
            </a>
          ) : null}
          {themeSwitch ? <div className="hidden lg:block"><ThemeSwitch {...themeSwitch} /></div> : null}
          {loginAction ? (
            <a href={loginAction.href} className={loginAlwaysVisible ? ghost : cn(ghost, "hidden lg:inline-flex")}>{loginAction.label}</a>
          ) : null}
          <a href={primaryAction.href} className={primaryActionDesktopOnly ? cn(linkButtonClass("primary", "md"), "hidden lg:inline-flex") : linkButtonClass("primary", "md")}>{primaryAction.label}</a>
          <Button
            ref={drawerBtn}
            variant="outline"
            size="icon"
            className="lg:hidden"
            aria-expanded={drawerOpen}
            aria-controls={drawerId}
            aria-label={drawerOpen ? "Fechar menu" : "Abrir menu"}
            onClick={() => setDrawerOpen((o) => !o)}
          >
            {drawerOpen ? <X className="h-4 w-4" aria-hidden="true" /> : <Menu className="h-4 w-4" aria-hidden="true" />}
          </Button>
        </div>
      </div>

      <div id={drawerId} hidden={!drawerOpen} className={cn("border-t border-border bg-card lg:hidden", HIDDEN_ATTR)}>
        <div className={`${wrapClass} flex flex-col gap-3 py-3`}>
          <nav aria-label="Principal (celular)" className="flex flex-col">
            {[...(productsHref ? [{ label: productsLabel, href: productsHref }] : []), ...links].map((l) => (
              <a key={l.href + l.label} href={l.href} onClick={() => setDrawerOpen(false)} className="rounded-md px-2 py-2.5 text-sm font-medium text-foreground hover:bg-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring">
                {l.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            {languageLink ? (
              <a href={languageLink.href} lang={languageLink.lang} aria-label={languageLink.ariaLabel} className={linkButtonClass("ghost", "sm")}>
                {languageLink.label}
              </a>
            ) : null}
            {themeSwitch ? <ThemeSwitch {...themeSwitch} /> : null}
          </div>
          {loginAction && !loginAlwaysVisible ? (
            <a href={loginAction.href} className={linkButtonClass("outline", "lg", "w-full")}>{loginAction.label}</a>
          ) : null}
        </div>
      </div>
    </header>
  );
}
