/**
 * Social Wiring — public landing (social.noctusai.com).
 *
 * Built from the owner-approved mockup (L2, 2026-11-07) with the seed landing
 * organs (`@noctusai/lib/marketing`). The hero conversation is an illustration
 * and is labelled "Amostra"; no metric, client or testimonial is shown because
 * none exists yet. Legal links are the seed-mounted `/consent/*` routes.
 * Leads go to core's public lead endpoint through the seed `createCoreLeadSubmit`.
 */
import { CalendarCheck } from "lucide-react";
import { env, productUrl } from "@noctusai/lib";
import {
  CtaBand, FeatureGrid, Hero, LandingFooter, LandingIcon, LandingNav, LandingThemeProvider, LeadCaptureForm,
  MotionProvider, ProductBrandScope, Steps, createCoreLeadSubmit, useLandingThemeSwitch,
  type FeatureItem, type ProductBrand,
} from "@noctusai/lib/marketing";

const stripSlash = (u: string) => u.replace(/\/+$/, "");
const CORE_URL = stripSlash(env.CORE_URL);
const AGENTS_URL = productUrl("agents");

/** Social Wiring accent (verde-petróleo), declared once. */
const SOCIAL_WIRING_BRAND: ProductBrand = { primary: "174 70% 26%", primaryLight: "170 55% 62%", primaryDark: "174 70% 18%" };
/** Agentes accent, applied to the cross-product link only. */
const AGENTS_BRAND: ProductBrand = { primary: "232 45% 42%", primaryLight: "230 80% 78%", primaryDark: "232 50% 28%" };

const submitLead = createCoreLeadSubmit({ productInterest: "social-wiring" });

const FEATURES: FeatureItem[] = [
  { icon: <LandingIcon name="MessageCircle" />, title: "Julia no WhatsApp", description: "Responde os leads no número da imobiliária, tira dúvidas sobre os imóveis e registra quem quer visitar." },
  { icon: <LandingIcon name="Kanban" />, title: "Leads e funil de vendas", description: "Cada lead entra no funil com a origem registrada. Você acompanha etapa por etapa até o fechamento." },
  { icon: <LandingIcon name="Building" />, title: "Imóveis", description: "Imóveis, condomínios e permutas num cadastro só. É dele que a Julia tira as respostas." },
  { icon: <LandingIcon name="FileText" />, title: "Clientes e contratos", description: "Clientes sem cadastro duplicado e contratos ligados ao cliente e ao imóvel." },
  { icon: <LandingIcon name="Megaphone" />, title: "Marketing", description: "E-mail marketing, campanhas e o retorno de cada portal: quanto custou e quantos leads trouxe." },
  { icon: <LandingIcon name="Wand" />, title: "CoreStudio", description: "Roteiros, títulos e carrosséis para as redes, a partir da sua pesquisa e da sua marca." },
];

const JULIA: FeatureItem[] = [
  { icon: <LandingIcon name="UsersRound" />, title: "Passa para a equipe na hora certa", description: "Cada etapa do atendimento tem um responsável, que pode ser a Julia ou uma pessoa da equipe." },
  { icon: <LandingIcon name="ShieldCheck" />, title: "Protege o número da imobiliária", description: "Lista da equipe, limites por organização e bloqueio de contatos indesejados." },
  {
    icon: <LandingIcon name="Bot" />,
    title: "Você controla quando ela atende",
    description: "Ligar, pausar, desligar e o modo de avaliação ficam no produto Agentes.",
    link: { label: "Ver os controles em Agentes", href: AGENTS_URL, brand: AGENTS_BRAND },
  },
];

const STEPS = [
  { title: "Conecte o WhatsApp", description: "Ligue o número da imobiliária ao Social Wiring lendo um QR code." },
  { title: "Cadastre os imóveis", description: "A Julia só fala do que está no cadastro, com os dados que você informou." },
  { title: "Teste com a sua equipe", description: "No modo de avaliação, a Julia só responde às pessoas que você liberar." },
  { title: "Abra para os leads", description: "Acompanhe tudo no funil e assuma qualquer conversa quando quiser." },
];

function Bubble({ who, mine, children }: { who: string; mine?: boolean; children: string }) {
  return (
    <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${mine ? "ml-auto bg-primary text-primary-foreground" : "bg-sidebar-accent text-sidebar-foreground"}`}>
      <small className="mb-0.5 block text-[11px] font-semibold">{who}</small>
      {children}
    </div>
  );
}

/** Illustrative WhatsApp conversation + handoff (sample data, labelled as such). Draws its own dark surface (bareMedia). */
function HeroConversation() {
  return (
    <div className="w-full rounded-2xl border border-sidebar-border bg-sidebar-accent/50 p-5">
      <div aria-hidden="true" className="grid gap-2.5 text-left">
        <div className="flex items-center justify-between text-sm font-semibold text-sidebar-foreground">
          <span>WhatsApp da imobiliária</span>
          <span className="rounded-full border border-dashed border-foreground/40 bg-warning-light px-2 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider text-foreground">Amostra</span>
        </div>
        <Bubble who="Lead">Oi! A casa de 3 dormitórios do anúncio ainda está disponível?</Bubble>
        <Bubble who="Julia" mine>Está sim! Ela tem quintal e duas vagas. Quer visitar? Tenho sábado de manhã.</Bubble>
        <Bubble who="Lead">Sábado de manhã é ótimo.</Bubble>
        <div className="flex items-center gap-2.5 rounded-lg border border-border bg-card p-3 text-sm text-card-foreground">
          <CalendarCheck className="h-4 w-4 text-primary" aria-hidden="true" />
          Interesse em visita · sábado, manhã
          <span className="ml-auto whitespace-nowrap rounded-full bg-primary/15 px-2 py-0.5 text-xs">Para o corretor</span>
        </div>
      </div>
    </div>
  );
}

function LandingPage() {
  const themeSwitch = useLandingThemeSwitch();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <LandingNav
        brand={{ label: "Social Wiring", href: "#top", ariaLabel: "Social Wiring, início" }}
        links={[
          { label: "Recursos", href: "#recursos" },
          { label: "Julia", href: "#julia" },
          { label: "Como funciona", href: "#como-funciona" },
          { label: "Contato", href: "#contato-form" },
        ]}
        allProductsHref={CORE_URL}
        loginAction={{ label: "Entrar", href: "/login" }}
        loginAlwaysVisible
        primaryAction={{ label: "Falar com a gente", href: "#contato-form" }}
        primaryActionDesktopOnly
        themeSwitch={themeSwitch}
      />
      <main id="main">
        <Hero
          variant="inverse"
          bareMedia
          accentEmphasis
          entrance="staggered"
          eyebrow="Social Wiring · para imobiliárias"
          title="Do primeiro “oi” no WhatsApp ao"
          titleEmphasis="contrato, num lugar só."
          lede="Leads, funil de vendas, imóveis, contratos e marketing da imobiliária, com a Julia respondendo no WhatsApp e passando para o corretor quem quer visitar."
          actions={[
            { label: "Falar com a gente", href: "#contato-form", variant: "primary" },
            { label: "Ver o que tem dentro", href: "#recursos", variant: "outline" },
          ]}
          media={<HeroConversation />}
          mediaLabel="Exemplo ilustrativo: um lead pergunta no WhatsApp se a casa ainda está disponível, a Julia responde e combina a visita, e a conversa vai para o corretor. Dados de amostra."
        />
        <FeatureGrid
          id="recursos"
          eyebrow="O que tem dentro"
          title="Tudo o que a imobiliária usa no dia a dia"
          description="Cada lead, imóvel e contrato fica no mesmo cadastro. Ninguém precisa copiar dado de uma planilha para outra."
          columns={3}
          accent
          items={FEATURES}
        />
        <FeatureGrid
          id="julia"
          eyebrow="A Julia"
          title="Uma atendente que não deixa lead esperando"
          description="A Julia atende no WhatsApp da imobiliária. Quando o lead quer visitar ou negociar, a conversa vai para uma pessoa da equipe."
          columns={3}
          accent
          items={JULIA}
        />
        <Steps
          id="como-funciona"
          eyebrow="Como funciona"
          title="Do cadastro ao primeiro lead atendido"
          steps={STEPS}
        />
        <LeadCaptureForm
          variant="product"
          productInterest="social-wiring"
          consentSubject="o Social Wiring"
          id="contato-form"
          eyebrow="Fale com a gente"
          title="Quer ver o Social Wiring na sua imobiliária?"
          description="Deixe o seu WhatsApp. Uma pessoa da equipe responde em horário comercial para entender a sua operação."
          heading="Pedir contato"
          submitLabel="Pedir contato"
          messageHint="Ex.: “Somos 8 corretores e perdemos lead no WhatsApp à noite.”"
          messagePlaceholder="Somos 8 corretores e perdemos lead no WhatsApp à noite."
          successTitle="Pedido recebido."
          successBody="Uma pessoa da equipe vai chamar você no WhatsApp informado, em horário comercial."
          againLabel="Enviar outro pedido"
          onSubmit={submitLead}
          privacyHref="/consent/privacy-policy"
        />
        <CtaBand
          id="entrar"
          variant="inverse"
          title="Já usa o Social Wiring?"
          description="Entre com a sua conta NoctusAI. É a mesma em todos os produtos."
          actions={[
            { label: "Entrar", href: "/login", variant: "primary" },
            { label: "Falar com a gente", href: "#contato-form", variant: "outline" },
          ]}
        />
      </main>
      <LandingFooter
        id="rodape"
        brand={<span className="text-lg font-bold">Social Wiring</span>}
        tagline={<>Um produto <a href={CORE_URL} className="underline">NoctusAI</a>.</>}
        columns={[
          {
            heading: "NoctusAI",
            links: [
              { label: "noctusai.com", href: CORE_URL },
              { label: "Agentes", href: AGENTS_URL },
            ],
          },
          {
            heading: "Legal",
            links: [
              { label: "Central de Privacidade", href: "/consent" },
              { label: "Política de Privacidade", href: "/consent/privacy-policy" },
              { label: "Termos de Uso", href: "/consent/terms-of-use" },
            ],
          },
        ]}
        copyright={`© ${new Date().getFullYear()} NoctusAI. Todos os direitos reservados.`}
      />
    </div>
  );
}

export default function Landing() {
  return (
    <ProductBrandScope brand={SOCIAL_WIRING_BRAND}>
      <LandingThemeProvider>
        <MotionProvider>
          <LandingPage />
        </MotionProvider>
      </LandingThemeProvider>
    </ProductBrandScope>
  );
}
