/**
 * Public landing for academia.noctusai.com — the seed `Landing` slot
 * (`createProductApp({ Landing })`), rendered at `/` for signed-out visitors.
 *
 * Ported from the designer repo (github.com/jraphaelsst/academia-de-reciclagem @ f1247bf,
 * `artifacts/academia-da-reciclagem/src/App.tsx` → `Home`; re-port = apply the designer's
 * App.tsx diff since that sha here, and regenerate landing.css from their index.css). Content and markup are
 * kept as designed; the only additions are the `.academia-landing` style scope and the
 * "Entrar" link into the seed `/login`. Its providers (QueryClient, Tooltip, Toaster,
 * wouter, NotFound) are dropped — the seed app shell already supplies all of them.
 *
 * Header + footer live in `components/site/` (`SiteHeader`/`SiteFooter`) —
 * shared verbatim with `/o-projeto` and `/a-carta` so the public site
 * presents one identical nav everywhere. `useHashScroll` is what makes those
 * two pages' "back to a landing section" links (`/#pilares`, etc.) actually
 * land on the section: a client-side route change does not trigger the
 * browser's native on-navigation hash-scroll.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowDownRight, ArrowRight, BookOpen, Circle, CircleDot, Factory, HandHeart, Leaf, Recycle, School, Sparkles, Users } from 'lucide-react';

import { SiteHeader } from '@/components/site/SiteHeader';
import { SiteFooter } from '@/components/site/SiteFooter';
import { InterestPopup } from '@/components/InterestPopup';
import infografico from '@/assets/landing/infografico-30-toneladas.jpg';
import './landing.css';

function Reveal({ children, className = '', delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    }, { threshold: 0.12 });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`${className} ${visible ? 'reveal' : ''}`}
      style={visible ? { animationDelay: `${delay}ms` } : { opacity: 0 }}
    >
      {children}
    </div>
  );
}

/** The design's `html { scroll-behavior: smooth }`, applied only while the landing is mounted. */
function useSmoothScroll() {
  useEffect(() => {
    const html = document.documentElement;
    const previous = html.style.scrollBehavior;
    html.style.scrollBehavior = 'smooth';
    return () => { html.style.scrollBehavior = previous; };
  }, []);
}

/**
 * Scrolls to `location.hash`'s target on mount/change — what makes
 * `/#pilares`-style links from the sub-pages (`SectionLink`) actually land
 * on the section. A full page navigation does this natively via the
 * browser; a client-side route change does not.
 */
function useHashScroll() {
  const location = useLocation();
  useEffect(() => {
    if (!location.hash) return;
    const id = location.hash.slice(1);
    const el = document.getElementById(id);
    // `scrollIntoView` doesn't exist in jsdom (test env only — every real
    // browser has it); the optional call guards that gap, not an error.
    el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [location.hash]);
}

export default function Landing() {
  useSmoothScroll();
  useHashScroll();

  return (
    <div className="academia-landing">
    <main className="site-shell">
      <SiteHeader />

      <section id="inicio" className="hero">
        <div className="container-xl hero-content">
          <div className="hero-copy">
            <Reveal className="eyebrow" delay={60}>educação que vira território</Reveal>
            <Reveal delay={150}>
              <h1 className="display hero-title">O futuro se<br />separa <em>agora.</em></h1>
            </Reveal>
            <Reveal delay={250}>
              <p className="hero-lede">A Academia da Reciclagem transforma dúvida em prática e descarte em aprendizado. Para que cada pessoa reconheça o valor que existe depois do uso.</p>
            </Reveal>
            <Reveal className="hero-actions" delay={350}>
              <a className="button-primary" href="#participar" data-testid="button-conhecer">Conheça a iniciativa <ArrowDownRight size={16} /></a>
              <Link className="button-quiet" to="/o-projeto" data-testid="button-ver-metodo">Ver o projeto</Link>
            </Reveal>
            <Reveal className="hero-footnote" delay={470}>
              <span className="hero-footnote-line" aria-hidden="true" />
              <span>Uma rede para quem acredita em fazer junto</span>
            </Reveal>
          </div>
          <Reveal className="hero-visual" delay={270}>
            <div className="orbit one" aria-hidden="true" />
            <div className="orbit two" aria-hidden="true" />
            <div className="scrap-card" aria-label="Ilustração de um cartão da Academia da Reciclagem">
              <Leaf size={42} />
              <div className="scrap-card-label">cartão de campo · 01</div>
              <div className="scrap-card-title">o que<br />fica?</div>
            </div>
            <div className="float-tag">
              <strong>resíduo</strong>
              recurso fora<br />do lugar
            </div>
            <div className="stamp">aprendizado<br />em circulação</div>
          </Reveal>
        </div>
        <div className="hero-scroll" aria-hidden="true">desça para descobrir</div>
      </section>

      <section id="projeto" className="section intro-section">
        <div className="container-xl intro-grid">
          <Reveal className="intro-aside">
            <p>“Reciclar não é decorar cores. É entender relações.”</p>
            <small>Conhecimento prático para decisões que cabem na rotina e melhoram o lugar onde a vida acontece.</small>
          </Reveal>
          <Reveal delay={160}>
            <div className="section-heading">
              <div className="eyebrow">01 / por que existimos</div>
              <h2 className="display section-title">A coleta começa antes da lixeira.</h2>
              <p className="section-intro">Separar materiais é um gesto pequeno com uma inteligência enorme por trás. A Academia aproxima essa inteligência de escolas, cooperativas, comunidades e empresas — sem culpa, sem jargão, sem deixar ninguém para trás.</p>
            </div>
          </Reveal>
        </div>
      </section>

      {/* The project's symbolic piece. It used to sit inline in the reading
          pages, where it competed with the text; here it gets a section of
          its own, with the numbers it is meant to make tangible. Every
          figure below comes from `content/projeto.ts` (the source .docx) —
          no invented statistics.

          Layout: the "02 /" heading + lede read first (the argument), then
          the image — large, offset-shadowed, edge-anchored — illustrates it,
          then the sourced numbers land as a bordered ledger row directly
          under the image instead of stacked in a tall list beside it (the
          old side-by-side grid left a lot of vertical air when the image was
          shorter than the copy column). */}
      <section id="trinta-toneladas" className="section tonnage-section" aria-labelledby="tonnage-title">
        <div className="container-xl tonnage-head">
          <Reveal className="tonnage-heading">
            <div className="eyebrow">02 / a imagem que move o projeto</div>
            <h2 id="tonnage-title" className="display section-title">
              O lixo não<br />desaparece.
            </h2>
            <p className="section-intro">
              Ele continua existindo, segue um caminho — e esse caminho pode ser de abandono e poluição, ou de
              reciclagem, renda e dignidade. Números sozinhos não transmitem isso. Esta imagem transmite.
            </p>
          </Reveal>
        </div>

        <Reveal className="tonnage-visual" delay={140}>
          <div className="container-xl tonnage-visual-inner">
            <figure className="tonnage-figure">
              <img
                src={infografico}
                alt="Infográfico: a montanha de resíduos que uma única pessoa gera ao longo da vida, representada em contêineres empilhados."
                loading="lazy"
                /* the asset's intrinsic size — reserves the right box, no layout shift */
                width={1280}
                height={853}
                data-testid="infografico-30-toneladas"
              />
              <figcaption>
                Imagem estratégica do projeto — as mais de 30 toneladas de resíduos que uma pessoa gera ao
                longo da vida.
              </figcaption>
            </figure>
          </div>
        </Reveal>

        <div className="container-xl">
          <Reveal className="tonnage-footer" delay={230}>
            <dl className="tonnage-metrics" aria-label="A conta de uma vida">
              <div className="tonnage-metric" data-testid="tonnage-toneladas">
                <dt className="tonnage-value">+30 t</dt>
                <dd className="tonnage-label">de resíduos gerados por uma única pessoa ao longo da vida</dd>
              </div>
              <div className="tonnage-metric" data-testid="tonnage-conteineres">
                <dt className="tonnage-value">+70</dt>
                <dd className="tonnage-label">contêineres empilhados — a imagem que deu origem ao projeto</dd>
              </div>
              <div className="tonnage-metric" data-testid="tonnage-municipios">
                <dt className="tonnage-value">4</dt>
                <dd className="tonnage-label">municípios no território inicial: Cotia, Carapicuíba, Embu das Artes e Jandira</dd>
              </div>
            </dl>

            <Link className="button-quiet tonnage-cta" to="/o-projeto" data-testid="link-tonnage-projeto">
              Ver o projeto inteiro <ArrowRight size={16} />
            </Link>
          </Reveal>
        </div>
      </section>

      <section id="como-funciona" className="section dark-section">
        <div className="container-xl">
          <Reveal>
            <div className="eyebrow">03 / o nosso jeito</div>
            <h2 className="display section-title">Menos palestra.<br />Mais mão na massa.</h2>
          </Reveal>
          <div className="steps">
            <Reveal className="step" delay={90}>
              <div className="step-number">01 — entender</div>
              <BookOpen className="step-icon" size={25} strokeWidth={1.5} />
              <h3>Aprender no contexto</h3>
              <p>Mapeamos os hábitos e desafios de cada território para falar de resíduos com exemplos que fazem sentido.</p>
            </Reveal>
            <Reveal className="step" delay={180}>
              <div className="step-number">02 — experimentar</div>
              <HandHeart className="step-icon" size={25} strokeWidth={1.5} />
              <h3>Testar na rotina</h3>
              <p>Oficinas, materiais abertos e desafios simples convidam todo mundo a testar uma mudança possível.</p>
            </Reveal>
            <Reveal className="step" delay={270}>
              <div className="step-number">03 — compartilhar</div>
              <Users className="step-icon" size={25} strokeWidth={1.5} />
              <h3>Fazer a rede girar</h3>
              <p>Registramos o que funcionou, reconhecemos saberes locais e espalhamos soluções que podem ser replicadas.</p>
            </Reveal>
          </div>
        </div>
      </section>

      <section id="impacto" className="section impact-section">
        <div className="container-xl impact-layout">
          <Reveal>
            <div className="eyebrow">04 / sinais de impacto</div>
            <h2 className="display section-title">Mudança boa<br />deixa rastro.</h2>
            <p className="impact-note">Acompanhamos aquilo que importa: gente mais segura para decidir, espaços mais preparados para separar e valor reconhecido em cada etapa.</p>
          </Reveal>
          <Reveal delay={170}>
            <div className="impact-numbers" aria-label="Indicadores de impacto da iniciativa">
              <div className="metric" data-testid="metric-pessoas"><div className="metric-value">3,8 mil</div><span className="metric-label">pessoas em jornadas de aprendizagem</span></div>
              <div className="metric" data-testid="metric-territorios"><div className="metric-value">27</div><span className="metric-label">territórios com ações ativas</span></div>
              <div className="metric" data-testid="metric-materiais"><div className="metric-value">14 t</div><span className="metric-label">de materiais encaminhados corretamente</span></div>
              <div className="metric" data-testid="metric-parcerias"><div className="metric-value">46</div><span className="metric-label">parcerias entre quem aprende e quem faz</span></div>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="section audience-section" aria-labelledby="audience-title">
        <div className="container-xl">
          <Reveal className="audience-heading">
            <div>
              <div className="eyebrow">05 / uma academia de verdade</div>
              <h2 id="audience-title" className="display section-title">Cabe muita gente<br />nesta conversa.</h2>
            </div>
            <p className="section-intro">Cada participante chega com uma pergunta. Sai com uma ferramenta — e com vontade de passar adiante.</p>
          </Reveal>
          <div className="audience-grid">
            <Reveal className="audience-card" delay={80}>
              <Sparkles className="audience-icon" size={28} strokeWidth={1.4} />
              <h3>Comunidade é o nosso ponto de partida.</h3>
              <p>Mutirões, conversas e mapas locais para transformar preocupação em organização coletiva.</p>
            </Reveal>
            <Reveal className="audience-card" delay={140}>
              <School className="audience-icon" size={22} strokeWidth={1.5} />
              <h3>Escolas</h3>
              <p>Projetos que conectam sala de aula e pátio.</p>
            </Reveal>
            <Reveal className="audience-card" delay={200}>
              <Factory className="audience-icon" size={22} strokeWidth={1.5} />
              <h3>Empresas</h3>
              <p>Times que fazem a circularidade caber na operação.</p>
            </Reveal>
            <Reveal className="audience-card" delay={260}>
              <CircleDot className="audience-icon" size={22} strokeWidth={1.5} />
              <h3>Cooperativas</h3>
              <p>Conhecimento de quem sustenta a reciclagem todos os dias.</p>
            </Reveal>
            <Reveal className="audience-card" delay={320}>
              <Circle className="audience-icon" size={22} strokeWidth={1.5} />
              <h3>Você</h3>
              <p>Uma escolha melhor começa com uma pergunta.</p>
            </Reveal>
          </div>
        </div>
      </section>

      <section id="pilares" className="section pillars-section" aria-labelledby="pillars-title">
        <div className="container-xl">
          <div className="pillars-intro">
            <Reveal>
              <div className="eyebrow">06 / o que sustenta o projeto</div>
              <h2 id="pillars-title" className="display section-title">Um propósito.<br /><em>Três caminhos.</em></h2>
            </Reveal>
            <Reveal className="pillars-context" delay={150}>
              <div className="sponsor-label">patrocínio que acredita no futuro</div>
              <p><strong>Este projeto tem como patrocinadora a One Consultoria Imobiliária</strong> e nasce de um propósito transformador: unir conhecimento, responsabilidade e ação social para mudar realidades, criar oportunidades e construir um futuro mais sustentável.</p>
            </Reveal>
          </div>
          <div className="pillars-grid">
            <Reveal className="pillar-card" delay={80}>
              <div className="pillar-topline"><span>01</span><Recycle size={23} strokeWidth={1.5} /></div>
              <h3>Economia<br />circular</h3>
              <p>Valorizar materiais que ainda são vistos como lixo e devolver a eles um novo significado.</p>
              <div className="pillar-highlight">Resíduo pode virar matéria-prima, oportunidade, trabalho e renda.</div>
            </Reveal>
            <Reveal className="pillar-card" delay={160}>
              <div className="pillar-topline"><span>02</span><BookOpen size={23} strokeWidth={1.5} /></div>
              <h3>Educação e<br />responsabilidade</h3>
              <p>Mobilizar condomínios, escolas, empresas e comunidades para aprender, praticar e multiplicar a separação correta.</p>
              <div className="pillar-highlight">Cada escolha faz diferença. Cada atitude inspira outra.</div>
            </Reveal>
            <Reveal className="pillar-card" delay={240}>
              <div className="pillar-topline"><span>03</span><Sparkles size={23} strokeWidth={1.5} /></div>
              <h3>O belo</h3>
              <p>A síntese do projeto: o mundo que queremos construir e deixar como legado para as próximas gerações.</p>
              <div className="pillar-highlight">O Brasil recicla menos de 10%. Não falta material: falta estrutura, educação ambiental e participação.</div>
            </Reveal>
          </div>
        </div>
      </section>

      <section className="section story-section">
        <div className="container-xl story-grid">
          <Reveal>
            <div className="eyebrow">07 / uma outra narrativa</div>
            <p className="story-quote">O que era “lixo” pode ser <em>começo</em> de muita coisa.</p>
          </Reveal>
          <Reveal className="story-detail" delay={170}>
            <p>Quando uma criança pergunta para onde vai uma embalagem, uma cadeia inteira ganha visibilidade. Quando uma cooperativa compartilha seu saber, a cidade aprende. É assim que construímos uma cultura de cuidado: tornando visível o trabalho, o valor e as possibilidades escondidas no que descartamos.</p>
            <cite>— manifesto da Academia da Reciclagem</cite>
          </Reveal>
        </div>
      </section>

      <section id="participar" className="join-section">
        <div className="container-xl join-content">
          <Reveal>
            <div className="eyebrow">08 / vem com a gente</div>
            <h2 className="display join-title">Toda mudança<br />precisa de uma primeira volta.</h2>
          </Reveal>
          <Reveal delay={170}>
            <div>
              <p className="join-copy">Se você quer levar a Academia para sua escola, organização, empresa ou bairro, conte para nós. As próximas práticas podem começar na sua rua.</p>
              <a className="join-link" href="mailto:oi@academiadareciclagem.org.br" data-testid="link-email">Falar com a Academia <ArrowRight size={16} /></a>
            </div>
          </Reveal>
        </div>
      </section>

      <SiteFooter />
    </main>
    <InterestPopup />
    </div>
  );
}
