/**
 * The public-site header — nav + mobile menu, shared by `/`, `/o-projeto`
 * and `/a-carta` so the three public pages present one identical nav
 * (extracted from `pages/Landing.tsx`, which owned this markup alone before
 * the sub-pages existed).
 *
 * "O Projeto" and "A Carta" are real routes (`Link`) — the two reading
 * pages, and the first two items by design — followed by "Dias de coleta"
 * (`/coleta`, the per-município collection calendar). The rest are landing sections,
 * resolved by `SectionLink` to either an in-page anchor (on the landing) or
 * `/#<hash>` (everywhere else) — including "Como funciona", which scrolls to
 * the landing's own section rather than opening a page of its own.
 *
 * NO "Entrar" LINK, by the owner's decision (2026-09-29). The public site is
 * about to be served at its own brand hostname `academiadareciclagem.eco`,
 * where a sign-in affordance addresses nobody in the audience; the team signs
 * in by typing `academia.noctusai.com/login`. Both hostnames serve this same
 * header, so the link is gone from both — that is intended, not an oversight.
 *
 * ⚠️  This is PRESENTATION ONLY — it hides an entrance, it does not guard one.
 * `/login` still resolves, and every authenticated route stays protected by
 * the seed's auth guard plus the backend's own checks. Never treat the missing
 * link as access control: the day a route needs protecting, protect the route.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Menu, X } from 'lucide-react';

import { Brand } from './Brand';
import { SectionLink } from './SectionLink';

export function SiteHeader() {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  return (
    <header className="site-header">
      <div className="container-xl nav-inner">
        <Brand />
        <nav className={`nav-links ${menuOpen ? 'is-open' : ''}`} aria-label="Navegação principal">
          <Link className="nav-link" to="/o-projeto" onClick={closeMenu} data-testid="link-projeto">
            O Projeto
          </Link>
          <Link className="nav-link" to="/a-carta" onClick={closeMenu} data-testid="link-a-carta">
            A Carta
          </Link>
          <Link className="nav-link" to="/coleta" onClick={closeMenu} data-testid="link-coleta">
            Dias de coleta
          </Link>
          <SectionLink hash="como-funciona" className="nav-link" onClick={closeMenu} data-testid="link-como-funciona">
            Como funciona
          </SectionLink>
          <SectionLink hash="impacto" className="nav-link" onClick={closeMenu} data-testid="link-impacto">
            Impacto
          </SectionLink>
          <SectionLink hash="pilares" className="nav-link" onClick={closeMenu} data-testid="link-pilares">
            Pilares
          </SectionLink>
          <SectionLink hash="participar" className="nav-cta" onClick={closeMenu} data-testid="link-participar">
            Quero participar <ArrowRight size={14} />
          </SectionLink>
        </nav>
        <button
          className="menu-toggle"
          type="button"
          aria-label={menuOpen ? 'Fechar menu' : 'Abrir menu'}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
          data-testid="button-menu"
        >
          {menuOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>
    </header>
  );
}
