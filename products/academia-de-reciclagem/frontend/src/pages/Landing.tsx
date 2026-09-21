/**
 * Public landing for academia.noctusai.com — the seed `Landing` slot
 * (`createProductApp({ Landing })`), rendered at `/` for signed-out visitors.
 *
 * Ported from the designer repo (github.com/jraphaelsst/academia-de-reciclagem,
 * `artifacts/academia-da-reciclagem/src/App.tsx` → `Home`). Content and markup are
 * kept as designed; the only additions are the `.academia-landing` style scope and the
 * "Entrar" link into the seed `/login`. Its providers (QueryClient, Tooltip, Toaster,
 * wouter, NotFound) are dropped — the seed app shell already supplies all of them.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDownRight, ArrowRight, BookOpen, ChevronDown, Circle, CircleDot, Factory, HandHeart, Leaf, LogIn, Menu, Recycle, School, Sparkles, Users, X } from 'lucide-react';

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

function Brand() {
  return (
    <a className="brand" href="#inicio" data-testid="link-brand">
      <span className="brand-mark" aria-hidden="true"><Recycle /></span>
      <span className="brand-name">Academia da<br />Reciclagem<small>aprender · agir · circular</small></span>
    </a>
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

export default function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);
  useSmoothScroll();

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="academia-landing">
    <main className="site-shell">
      <header className="site-header">
        <div className="container-xl nav-inner">
          <Brand />
          <nav className={`nav-links ${menuOpen ? 'is-open' : ''}`} aria-label="Navegação principal">
            <a className="nav-link" href="#projeto" onClick={closeMenu} data-testid="link-projeto">O projeto</a>
            <a className="nav-link" href="#como-funciona" onClick={closeMenu} data-testid="link-como-funciona">Como funciona</a>
            <a className="nav-link" href="#impacto" onClick={closeMenu} data-testid="link-impacto">Impacto</a>
            <a className="nav-cta" href="#participar" onClick={closeMenu} data-testid="link-participar">Quero participar <ArrowRight size={14} /></a>
            <Link className="nav-login" to="/login" onClick={closeMenu} data-testid="link-entrar">Entrar <LogIn size={14} /></Link>
          </nav>
          <button className="menu-toggle" type="button" aria-label={menuOpen ? 'Fechar menu' : 'Abrir menu'} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)} data-testid="button-menu">
            {menuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </header>

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
              <a className="button-quiet" href="#como-funciona" data-testid="button-ver-metodo">Ver como funciona</a>
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

      <section id="como-funciona" className="section dark-section">
        <div className="container-xl">
          <Reveal>
            <div className="eyebrow">02 / o nosso jeito</div>
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
            <div className="eyebrow">03 / sinais de impacto</div>
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
              <div className="eyebrow">04 / uma academia de verdade</div>
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

      <section className="section story-section">
        <div className="container-xl story-grid">
          <Reveal>
            <div className="eyebrow">05 / uma outra narrativa</div>
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
            <div className="eyebrow">06 / vem com a gente</div>
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

      <footer className="site-footer">
        <div className="container-xl footer-inner">
          <div>
            <Brand />
            <p className="footer-brand-note">Conhecimento que circula. Valor que permanece.</p>
          </div>
          <div className="footer-meta">
            <span>projeto público independente</span>
            <a href="#inicio" data-testid="link-voltar-topo">voltar ao início <ChevronDown size={11} style={{ transform: 'rotate(180deg)', verticalAlign: 'middle' }} /></a>
          </div>
        </div>
      </footer>
    </main>
    </div>
  );
}
