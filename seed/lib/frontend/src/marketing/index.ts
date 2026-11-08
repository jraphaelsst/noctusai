/**
 * `@noctusai/lib/marketing` — the ONLY entry point that exposes Motion.
 *
 * Never re-export from the root barrel (`src/index.ts`): the authenticated
 * app must not pay for animation code. Landing pages import this subpath
 * from a lazy route chunk.
 */
export { MotionProvider } from "./MotionProvider";
export type { MotionProviderProps } from "./MotionProvider";
export { Reveal, Stagger } from "./primitives";
export type { RevealProps, StaggerProps } from "./primitives";

// ── Landing organs (public website sections) ─────────────────────────────────
export { LandingNav, ThemeSwitch } from "./LandingNav";
export type { LandingNavProps, NavLink, NavProduct, ThemeChoice } from "./LandingNav";
export { Hero } from "./Hero";
export type { HeroProps, HeroChip, HeroStat } from "./Hero";
export { FeatureGrid } from "./FeatureGrid";
export type { FeatureGridProps, FeatureItem } from "./FeatureGrid";
export { ProductCatalogGrid, selectFeaturedProducts, sortCatalog } from "./ProductCatalogGrid";
export type { ProductCatalogGridProps, CatalogProduct, CatalogStatus } from "./ProductCatalogGrid";
export { Steps } from "./Steps";
export type { StepsProps, StepItem } from "./Steps";
export { LeadCaptureForm, LEAD_MESSAGES } from "./LeadCaptureForm";
export type { LeadCaptureFormProps, LeadFormValues, LeadInterest } from "./LeadCaptureForm";
export type { TurnstileApi } from "./TurnstileSlot";
export { CtaBand } from "./CtaBand";
export type { CtaBandProps } from "./CtaBand";
export { Faq } from "./Faq";
export type { FaqProps, FaqItem } from "./Faq";
export { LandingFooter } from "./LandingFooter";
export type { LandingFooterProps, FooterColumn, FooterLink } from "./LandingFooter";
export type { LandingAction } from "./shared";
export { LandingIcon } from "./shared";

// ── Landing v2 additions ─────────────────────────────────────────────────────
export { ProductBrandScope, productBrandCss, productBrandVars } from "./productBrand";
export type { ProductBrand, ProductBrandScopeProps } from "./productBrand";
export { LandingThemeProvider, useLandingTheme, useLandingThemeSwitch, createThemeInlineScript, THEME_INLINE_SCRIPT, THEME_STORAGE_KEY } from "./theme";
export type { LandingThemeValue, LandingThemeProviderProps, ResolvedTheme } from "./theme";
export { submitCoreLead, createCoreLeadSubmit, toCoreLeadPayload, LANDING_CONSENT_TEXT_VERSION } from "./coreLead";
export type { CoreLeadOptions, CoreLeadPayload } from "./coreLead";
