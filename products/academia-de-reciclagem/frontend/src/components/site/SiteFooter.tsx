/**
 * The public-site footer — extracted from `pages/Landing.tsx` so
 * `/como-funciona` and `/a-carta` share the exact same sponsor credit +
 * "voltar ao início" link.
 */
import { ChevronDown } from 'lucide-react';

import { Brand } from './Brand';
import { SectionLink } from './SectionLink';
import oneLogo from '@/assets/landing/logo-one-consultoria.png';

export function SiteFooter() {
  return (
    <footer id="footer" className="site-footer">
      <div className="container-xl footer-inner">
        <div className="footer-brand-group">
          <div className="footer-brand-row">
            <Brand />
            <a
              className="footer-sponsor"
              href="https://oneconsultoriaimobiliaria.com.br/"
              target="_blank"
              rel="noreferrer"
              aria-label="Patrocínio: One Consultoria Imobiliária — abrir site oficial"
              data-testid="link-one-sponsor"
            >
              <img className="footer-sponsor-logo" src={oneLogo} alt="One Consultoria Imobiliária" />
              <span className="footer-sponsor-copy">
                <span>patrocínio</span>
                <strong>One Consultoria Imobiliária</strong>
              </span>
            </a>
          </div>
          <p className="footer-brand-note">Conhecimento que circula. Valor que permanece.</p>
        </div>
        <div className="footer-meta">
          <span>projeto público independente</span>
          <SectionLink hash="inicio" data-testid="link-voltar-topo">
            voltar ao início <ChevronDown size={11} style={{ transform: 'rotate(180deg)', verticalAlign: 'middle' }} />
          </SectionLink>
        </div>
      </div>
    </footer>
  );
}
