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
export { LandingNav } from "./LandingNav";
export type { LandingNavProps, NavLink, NavProduct, ThemeChoice } from "./LandingNav";
export { Hero } from "./Hero";
export type { HeroProps, HeroChip } from "./Hero";
export { FeatureGrid } from "./FeatureGrid";
export type { FeatureGridProps, FeatureItem } from "./FeatureGrid";
export { ProductCatalogGrid, selectFeaturedProducts, sortCatalog } from "./ProductCatalogGrid";
export type { ProductCatalogGridProps, CatalogProduct, CatalogStatus } from "./ProductCatalogGrid";
export { Steps } from "./Steps";
export type { StepsProps, StepItem } from "./Steps";
export { LeadCaptureForm, LEAD_MESSAGES } from "./LeadCaptureForm";
export type { LeadCaptureFormProps, LeadFormValues, LeadInterest } from "./LeadCaptureForm";
export { CtaBand } from "./CtaBand";
export type { CtaBandProps } from "./CtaBand";
export { Faq } from "./Faq";
export type { FaqProps, FaqItem } from "./Faq";
export { LandingFooter } from "./LandingFooter";
export type { LandingFooterProps, FooterColumn, FooterLink } from "./LandingFooter";
export type { LandingAction } from "./shared";
export { LandingIcon } from "./shared";
