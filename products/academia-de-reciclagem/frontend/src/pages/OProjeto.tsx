/**
 * `/como-funciona` — the seed `publicRoutes` slot (`createProductApp({
 * publicRoutes })`), reachable for both signed-out AND signed-in visitors
 * (mounted ahead of the auth-gated catch-all in `seed/framework/frontend/
 * src/app.tsx`, same as the platform's consent pages).
 *
 * All seven `TOPICOS` (`src/content/projeto.ts`) as independent expand/
 * collapse sections (`components/Accordion.tsx`). Supports a
 * `/como-funciona#<id>` deep link: the matching section opens on mount and
 * the page scrolls to it.
 */
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

import { SiteHeader } from '@/components/site/SiteHeader';
import { SiteFooter } from '@/components/site/SiteFooter';
import { InterestPopup } from '@/components/InterestPopup';
import { AccordionItem } from '@/components/Accordion';
import { ContentBlocks } from '@/components/ContentBlocks';
import { TOPICOS } from '@/content/projeto';
import './landing.css';

export default function ComoFunciona() {
  const location = useLocation();
  // Read once, at mount — `defaultOpen` only affects the section's INITIAL
  // render, so re-computing this on every hash change would do nothing.
  const deepLinkId = location.hash ? location.hash.slice(1) : null;

  useEffect(() => {
    if (!deepLinkId) return;
    // The matching AccordionItem mounts open (`defaultOpen`) in the same
    // render, so it's already in the DOM by the time this effect runs.
    // `scrollIntoView` doesn't exist in jsdom (test env only — every real
    // browser has it); the optional call guards that gap, not an error.
    document.getElementById(deepLinkId)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="academia-landing">
      <SiteHeader />

      <section className="sub-hero">
        <div className="container-xl">
          <div className="eyebrow">como funciona</div>
          <h1 className="display section-title">
            Os sete passos do<br />Projeto Academia da Reciclagem.
          </h1>
          <p className="section-intro">
            Do plano diretor à carta às próximas gerações — o roteiro completo, tópico por tópico. Toque em um
            título para abrir.
          </p>
        </div>
      </section>

      <section className="section como-funciona-section">
        <div className="container-xl">
          <div className="accordion-list">
            {TOPICOS.map((topico) => (
              <AccordionItem
                key={topico.id}
                id={topico.id}
                numero={topico.numero}
                titulo={topico.titulo}
                defaultOpen={topico.id === deepLinkId}
              >
                <ContentBlocks blocos={topico.blocos} />
              </AccordionItem>
            ))}
          </div>
        </div>
      </section>

      <SiteFooter />
      <InterestPopup />
    </div>
  );
}
