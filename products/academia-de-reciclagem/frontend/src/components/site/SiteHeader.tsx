/**
 * The public-site header — nav + mobile menu, shared by `/`, `/o-projeto`
 * and `/a-carta` so the three public pages present one identical nav
 * (extracted from `pages/Landing.tsx`, which owned this markup alone before
 * the sub-pages existed).
 *
 * "O Projeto" and "A Carta" are real routes (`Link`) — the two reading
 * pages, and the first two items by design. The rest are landing sections,
 * resolved by `SectionLink` to either an in-page anchor (on the landing) or
 * `/#<hash>` (everywhere else) — including "Como funciona", which scrolls to
 * the landing's own section rather than opening a page of its own.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, LogIn, Menu, X } from 'lucide-react';

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
          <Link className="nav-login" to="/login" onClick={closeMenu} data-testid="link-entrar">
            Entrar <LogIn size={14} />
          </Link>
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
