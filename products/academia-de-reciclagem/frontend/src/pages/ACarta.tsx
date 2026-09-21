/**
 * `/a-carta` — the seed `publicRoutes` slot (`createProductApp({
 * publicRoutes })`). Letter-style reading layout for `CARTA` (`src/content/
 * projeto.ts`).
 *
 * `CARTA.blocos`' last two entries are, by the source document's own fixed
 * shape (see `content/projeto.ts`'s header note), the closing destaque +
 * the "Gilson Tangerino" / "Idealizador ..." signature — split out here so
 * they can be styled as a signature block instead of one more paragraph.
 * If a future revision of the letter changes that ending shape, update the
 * split here too.
 */
import { SiteHeader } from '@/components/site/SiteHeader';
import { SiteFooter } from '@/components/site/SiteFooter';
import { InterestPopup } from '@/components/InterestPopup';
import { renderBloco } from '@/components/ContentBlocks';
import { CARTA } from '@/content/projeto';
import './landing.css';

const SIGNATURE_BLOCK_COUNT = 2;

export default function ACarta() {
  const bodyBlocos = CARTA.blocos.slice(0, -SIGNATURE_BLOCK_COUNT);
  const signatureBlocos = CARTA.blocos.slice(-SIGNATURE_BLOCK_COUNT);

  return (
    <div className="academia-landing">
      <SiteHeader />

      <section className="sub-hero">
        <div className="container-xl">
          <div className="eyebrow">uma carta pessoal</div>
          <h1 className="display section-title">{CARTA.titulo}</h1>
        </div>
      </section>

      <section className="section carta-section">
        <div className="container-xl carta-page">
          {bodyBlocos.map((bloco, i) => renderBloco(bloco, i))}
          <div className="carta-signature" data-testid="carta-signature">
            {signatureBlocos.map((bloco, i) => renderBloco(bloco, `sig-${i}`))}
          </div>
        </div>
      </section>

      <SiteFooter />
      <InterestPopup />
    </div>
  );
}
