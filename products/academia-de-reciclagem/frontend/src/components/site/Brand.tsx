/**
 * The landing's brand mark — extracted verbatim from `pages/Landing.tsx` so
 * `SiteHeader` and `SiteFooter` (and any future public page) render the
 * identical logo. Anchors to `#inicio` on the landing itself and to
 * `/#inicio` everywhere else, via `SectionLink`.
 */
import { SectionLink } from './SectionLink';
import logo from '@/assets/landing/logo-academia-da-reciclagem.png';

export function Brand() {
  return (
    <SectionLink hash="inicio" className="brand" data-testid="link-brand">
      <span className="brand-logo-frame">
        <img className="brand-logo" src={logo} alt="Academia da Reciclagem" />
      </span>
    </SectionLink>
  );
}
