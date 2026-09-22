/**
 * Renders a `Bloco[]` (`src/content/projeto.ts`) — shared by `/o-projeto`
 * (inside each `AccordionItem`) and `/a-carta` (the full letter body).
 *
 * TEXT ONLY. The "30 toneladas" infographic used to be interleaved here as
 * an `imagem` block; it now lives in its own landing section
 * (`pages/Landing.tsx`, `#trinta-toneladas`), where it gets the space and
 * the supporting numbers it needs. The reading pages stay uninterrupted.
 */
import type { Key, ReactElement } from 'react';
import type { Bloco } from '@/content/projeto';

export function renderBloco(bloco: Bloco, key: Key): ReactElement {
  if (bloco.tipo === 'destaque') {
    return (
      <p key={key} className="content-destaque">
        {bloco.texto}
      </p>
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
