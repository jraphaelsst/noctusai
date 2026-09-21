/**
 * Renders a `Bloco[]` (`src/content/projeto.ts`) — shared by `/como-funciona`
 * (inside each `AccordionItem`) and `/a-carta` (the full letter body).
 *
 * `imagem` blocks all render the one "30 toneladas" infographic
 * (`content/projeto.ts`'s own module doc), lazy-loaded since every
 * `/como-funciona` topic panel can carry one and only the expanded ones are
 * visible at a time.
 */
import type { Key, ReactElement } from 'react';
import type { Bloco } from '@/content/projeto';
import infografico from '@/assets/landing/infografico-30-toneladas.jpg';

export function renderBloco(bloco: Bloco, key: Key): ReactElement {
  if (bloco.tipo === 'destaque') {
    return (
      <p key={key} className="content-destaque">
        {bloco.texto}
      </p>
    );
  }
  if (bloco.tipo === 'imagem') {
    return (
      <figure key={key} className="content-figure">
        <img src={infografico} alt={bloco.legenda ?? ''} loading="lazy" />
        {bloco.legenda ? <figcaption>{bloco.legenda}</figcaption> : null}
      </figure>
    );
  }
  return (
    <p key={key} className="content-paragrafo">
      {bloco.texto}
    </p>
  );
}

export function ContentBlocks({ blocos }: { blocos: Bloco[] }) {
  return <>{blocos.map((bloco, i) => renderBloco(bloco, i))}</>;
}
