/**
 * Social Wiring — public landing (social.noctusai.com).
 *
 * Built from the owner-approved mockup (L2, 2026-11-07) with the seed landing
 * organs (`@noctusai/lib/marketing`). The hero conversation is an illustration
 * and is labelled "Amostra"; no metric, client or testimonial is shown because
 * none exists yet. Legal links are the seed-mounted `/consent/*` routes.
 * Leads go to core's public `POST /api/website/leads` (`env.CORE_API_URL`).
 */
import { useCallback } from "react";
import {
  Bot, Building2, CalendarCheck, FileText, Kanban, Megaphone, MessageCircle, ShieldCheck, UsersRound, WandSparkles,
} from "lucide-react";
import { env } from "@noctusai/lib";
import {
  CtaBand, FeatureGrid, Hero, LandingFooter, LandingNav, LeadCaptureForm, MotionProvider, Steps,
  type FeatureItem, type LeadFormValues,
} from "@noctusai/lib/marketing";

const CONSENT_TEXT_VERSION = "2026-09-23.v1";

const stripSlash = (u: string) => u.replace(/\/+$/, "");
const CORE_URL = stripSlash(env.CORE_URL);
const CORE_API_URL = stripSlash(env.CORE_API_URL);
// Agentes is a separate product with no shared FE URL seam yet: the link renders
// only when the deploy bakes VITE_AGENTS_URL (never a hardcoded host).
const AGENTS_URL: string = stripSlash((import.meta.env.VITE_AGENTS_URL as string | undefined) ?? "");

const ic = "h-5 w-5";
const FEATURES: FeatureItem[] = [
  { icon: <MessageCircle className={ic} aria-hidden="true" />, title: "Julia no WhatsApp", description: "Responde os leads no número da imobiliária, tira dúvidas sobre os imóveis e registra quem quer visitar." },
  { icon: <Kanban className={ic} aria-hidden="true" />, title: "Leads e funil de vendas", description: "Cada lead entra no funil com a origem registrada. Você acompanha etapa por etapa até o fechamento." },
  { icon: <Building2 className={ic} aria-hidden="true" />, title: "Imóveis", description: "Imóveis, condomínios e permutas num cadastro só. É dele que a Julia tira as respostas." },
  { icon: <FileText className={ic} aria-hidden="true" />, title: "Clientes e contratos", description: "Clientes sem cadastro duplicado e contratos ligados ao cliente e ao imóvel." },
  { icon: <Megaphone className={ic} aria-hidden="true" />, title: "Marketing", description: "E-mail marketing, campanhas e o retorno de cada portal: quanto custou e quantos leads trouxe." },
  { icon: <WandSparkles className={ic} aria-hidden="true" />, title: "CoreStudio", description: "Roteiros, títulos e carrosséis para as redes, a partir da sua pesquisa e da sua marca." },
];

const JULIA: FeatureItem[] = [
  { icon: <UsersRound className={ic} aria-hidden="true" />, title: "Passa para a equipe na hora certa", description: "Cada etapa do atendimento tem um responsável, que pode ser a Julia ou uma pessoa da equipe." },
  { icon: <ShieldCheck className={ic} aria-hidden="true" />, title: "Protege o número da imobiliária", description: "Lista da equipe, limites por organização e bloqueio de contatos indesejados." },
  {
    icon: <Bot className={ic} aria-hidden="true" />,
    title: "Você controla quando ela atende",
    description: "Ligar, pausar, desligar e a fase de testes ficam no produto Agentes.",
    ...(AGENTS_URL ? { cta: { label: "Ver os controles em Agentes", href: AGENTS_URL } } : {}),
  },
];

const STEPS = [
  { title: "Conecte o WhatsApp", description: "Ligue o número da imobiliária ao Social Wiring lendo um QR code." },
  { title: "Cadastre os imóveis", description: "A Julia só fala do que está no cadastro, com os dados que você informou." },
  { title: "Teste com a sua equipe", description: "Na fase de testes, a Julia só responde às pessoas que você liberar." },
  { title: "Abra para os leads", description: "Acompanhe tudo no funil e assuma qualquer conversa quando quiser." },
];

function Bubble({ who, mine, children }: { who: string; mine?: boolean; children: string }) {
  return (
    <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${mine ? "ml-auto bg-primary text-primary-foreground" : "bg-muted text-foreground"}`}>
      <small className="mb-0.5 block text-[11px] font-semibold">{who}</small>
      {children}
    </div>
  );
}

/** Illustrative WhatsApp conversation + handoff (sample data, labelled as such). */
function HeroConversation() {
  return (
    <div aria-hidden="true" className="grid w-full gap-2.5 p-1 text-left">
      <div className="flex items-center justify-between text-sm font-semibold text-foreground">
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
  );
}

/** Seed `LeadCaptureForm` values -> core's public `POST /api/website/leads` (a refusal throws: the organ shows the error and keeps the typed values). */
async function submitLead(values: LeadFormValues): Promise<void> {
  const res = await fetch(`${CORE_API_URL}/api/website/leads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source: "contact",
      name: values.nome,
      phone: values.whatsapp,
      email: values.email,
      company: values.empresa,
      product_interest: ["social-wiring"],
      message: values.mensagem,
      locale: "pt-BR",
      consent_marketing: values.consentimento,
      consent_text_version: CONSENT_TEXT_VERSION,
      landing_path: window.location.pathname,
      referrer: document.referrer || undefined,
      turnstile_token: values.turnstileToken,
    }),
  });
  if (!res.ok) throw new Error(`lead_http_${res.status}`);
}

export default function Landing() {
  const onSubmit = useCallback((values: LeadFormValues) => submitLead(values), []);
  return (
    <MotionProvider>
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
          primaryAction={{ label: "Falar com a gente", href: "#contato-form" }}
        />
        <main id="main">
          <Hero
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
            items={FEATURES}
          />
          <FeatureGrid
            id="julia"
            eyebrow="A Julia"
            title="Uma atendente que não deixa lead esperando"
            description="A Julia atende no WhatsApp da imobiliária. Quando o lead quer visitar ou negociar, a conversa vai para uma pessoa da equipe."
            items={JULIA}
          />
          <Steps
            id="como-funciona"
            eyebrow="Como funciona"
            title="Do cadastro ao primeiro lead atendido"
            steps={STEPS}
          />
          <LeadCaptureForm
            variant="brief"
            id="contato-form"
            eyebrow="Fale com a gente"
            title="Quer ver o Social Wiring na sua imobiliária?"
            description="Deixe o seu WhatsApp. Uma pessoa da equipe responde em horário comercial para entender a sua operação."
            heading="Pedir contato"
            onSubmit={onSubmit}
            privacyHref="/consent/privacy-policy"
          />
          <CtaBand
            id="entrar"
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
          tagline="Um produto NoctusAI."
          columns={[
            {
              heading: "NoctusAI",
              links: [
                { label: "noctusai.com", href: CORE_URL },
                ...(AGENTS_URL ? [{ label: "Agentes", href: AGENTS_URL }] : []),
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
    </MotionProvider>
  );
}
