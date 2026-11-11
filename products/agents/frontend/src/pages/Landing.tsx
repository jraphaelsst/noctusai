/**
 * Agentes — public landing (agents.noctusai.com).
 *
 * Built from the seed landing organs (`@noctusai/lib/marketing`): nav, hero (media slot),
 * two feature grids, steps, lead form, CTA band, footer. Copy and structure follow the
 * owner-approved mockup. The hero panel is an ILLUSTRATION (labelled "Amostra"), not live data.
 * The page wears the Agentes indigo through the seed `ProductBrandScope`.
 * Legal links point to the seed-mounted /consent/* routes.
 */
import { Bot, FlaskConical, MessageCircle } from "lucide-react";
import { env, productUrl } from "@noctusai/lib";
import {
  CtaBand, FeatureGrid, Hero, LandingFooter, LandingIcon, LandingNav, LandingThemeProvider, LeadCaptureForm,
  MotionProvider, ProductBrandScope, Steps, createCoreLeadSubmit, useLandingThemeSwitch,
} from "@noctusai/lib/marketing";
import type { ProductBrand } from "@noctusai/lib/marketing";

const CORE = env.CORE_URL.replace(/\/+$/, "");

/** Agentes' brand (indigo), applied to this page only. */
const AGENTS_BRAND: ProductBrand = { primary: "232 45% 42%", primaryLight: "230 80% 78%", primaryDark: "232 50% 28%" };
/** Social Wiring's own accent, for the cross-product link on the Julia card. */
const SOCIAL_WIRING_BRAND: ProductBrand = { primary: "174 70% 26%", primaryLight: "170 55% 62%", primaryDark: "174 70% 18%" };
const SOCIAL_WIRING_URL = productUrl("social-wiring");

const submitLead = createCoreLeadSubmit({ productInterest: "agents" });

const SEGMENT = ["Ligado", "Drenando", "Desligado"] as const;

function Segmented() {
  return (
    <div className="mt-3 grid grid-cols-3 gap-1 rounded-md bg-muted p-1 text-xs">
      {SEGMENT.map((s, i) => (
        <span
          key={s}
          className={`rounded-sm px-2 py-1 text-center font-medium ${i === 0 ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
        >
          {s}
        </span>
      ))}
    </div>
  );
}

/** Illustrative panel for the hero media slot (bare: it draws its own surface). Sample data, says so. */
function AgentsPanel() {
  return (
    <div className="w-full space-y-3 rounded-xl border border-border bg-card p-4 text-left shadow-lg">
      <div className="flex items-center justify-between text-sm font-semibold text-foreground">
        <span>Agentes da organização</span>
        <span className="rounded-full border border-input px-2 py-0.5 text-xs font-medium text-muted-foreground">Amostra</span>
      </div>
      <div className="rounded-lg border border-border bg-background p-3">
        <div className="flex items-center gap-3">
          <MessageCircle className="h-5 w-5 text-primary" aria-hidden="true" />
          <div className="flex flex-col">
            <strong className="text-sm text-foreground">Julia</strong>
            <small className="text-xs text-muted-foreground">Qualificação de leads · WhatsApp</small>
          </div>
        </div>
        <Segmented />
      </div>
      <div className="rounded-lg border border-border bg-background p-3">
        <div className="flex items-center gap-3">
          <Bot className="h-5 w-5 text-primary" aria-hidden="true" />
          <div className="flex flex-col">
            <strong className="text-sm text-foreground">Bia</strong>
            <small className="text-xs text-muted-foreground">Assistente da equipe · Web</small>
          </div>
        </div>
        <Segmented />
        <p className="mt-3 flex items-center gap-2 rounded-md border border-warning bg-warning-light p-2 text-xs text-foreground">
          <FlaskConical className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span><b>Modo de avaliação</b>: responde só a pessoas liberadas</span>
        </p>
      </div>
    </div>
  );
}

const HERO_MEDIA_LABEL =
  "Exemplo ilustrativo do painel de agentes: a Julia está ligada no WhatsApp; a Bia está em modo de avaliação, respondendo só a pessoas liberadas. Dados de amostra.";

const icon = (name: string) => <LandingIcon name={name} className="h-5 w-5" />;

function LandingNavBar() {
  const themeSwitch = useLandingThemeSwitch();
  return (
    <LandingNav
      brand={{ label: "Agentes", href: "#top", ariaLabel: "Agentes, início", mark: <Bot className="h-5 w-5 text-primary" aria-hidden="true" /> }}
      links={[
        { label: "Os agentes", href: "#agentes" },
        { label: "Controle", href: "#controle" },
        { label: "Como funciona", href: "#como-funciona" },
        { label: "Contato", href: "#contato" },
      ]}
      allProductsHref={`${CORE}/produtos`}
      loginAction={{ label: "Entrar", href: "/login" }}
      loginAlwaysVisible
      primaryAction={{ label: "Falar com a gente", href: "#contato" }}
      primaryActionDesktopOnly
      themeSwitch={themeSwitch}
    />
  );
}

export default function Landing() {
  return (
    <LandingThemeProvider>
      <ProductBrandScope brand={AGENTS_BRAND}>
        <MotionProvider>
          <div className="min-h-screen bg-background text-foreground">
            <LandingNavBar />

            <main id="main" tabIndex={-1}>
              <Hero
                variant="inverse"
                bareMedia
                accentEmphasis
                entrance="staggered"
                eyebrow="Agentes NoctusAI"
                title="Agentes de IA que atendem por você,"
                titleEmphasis="sob o seu controle."
                lede="A Julia qualifica leads no WhatsApp e a Bia ajuda a sua equipe na web. Você liga, pausa ou desliga cada agente e acompanha cada conversa."
                actions={[
                  { label: "Falar com a gente", href: "#contato", variant: "primary" },
                  { label: "Ver como você controla", href: "#controle", variant: "outline" },
                ]}
                media={<AgentsPanel />}
                mediaLabel={HERO_MEDIA_LABEL}
              />

              <FeatureGrid
                id="agentes"
                columns={2}
                cardVariant="large"
                accent
                eyebrow="Os agentes"
                title="Cada agente tem um trabalho claro"
                description="Um agente faz uma coisa bem feita e sabe a hora de chamar uma pessoa."
                items={[
                  {
                    tag: "WhatsApp",
                    title: "Julia · qualificação de leads",
                    description: "Responde quem chega pelo WhatsApp, faz as perguntas de qualificação e passa para a equipe quem está pronto.",
                    bullets: [
                      "Dá nota ao lead por regras fixas: o mesmo lead recebe sempre a mesma nota",
                      "Consulta os imóveis cadastrados antes de responder",
                      "Quando um cliente reclama, avisa a equipe",
                    ],
                    link: { label: "A Julia atende pelo Social Wiring", href: SOCIAL_WIRING_URL, brand: SOCIAL_WIRING_BRAND },
                  },
                  {
                    tag: "Web",
                    title: "Bia · assistente da equipe",
                    description: "Consulta a base de conhecimento da organização e propõe alterações. Nada é gravado sem a sua aprovação.",
                    bullets: [
                      "Responde dentro do navegador, para a equipe",
                      "Cada alteração vira um pedido que você aprova ou recusa",
                    ],
                  },
                ]}
              />

              <FeatureGrid
                id="controle"
                columns={3}
                accent
                eyebrow="Controle"
                title="Você decide quando e com quem cada agente fala"
                items={[
                  { icon: icon("Power"), title: "Ligado, drenando ou desligado", description: "Drenando: o agente termina as conversas em andamento e não começa novas." },
                  { icon: icon("FlaskConical"), title: "Modo de avaliação", description: "Antes de abrir para todos, o agente só responde às pessoas que você liberou." },
                  { icon: icon("GitMerge"), title: "Uma conversa por lead", description: "Quando o lead passa de um agente para outro, ou para a equipe, a conversa continua no mesmo histórico." },
                  { icon: icon("Target"), title: "Regras que não mudam no meio do caminho", description: "Cada agente segue uma versão definida das regras, e cada resposta é conferida antes de sair." },
                  { icon: icon("Lock"), title: "Dados do lead protegidos", description: "Nome e contato do lead ficam criptografados no banco. O consentimento fica registrado na conversa." },
                  { icon: icon("ShieldCheck"), title: "Proteção contra abuso", description: "Limites por conversa e respostas que não revelam as instruções internas do agente." },
                ]}
              />

              <Steps
                id="como-funciona"
                eyebrow="Como funciona"
                title="Do primeiro teste ao atendimento de verdade"
                steps={[
                  { title: "Escolha o agente", description: "Defina qual trabalho ele vai fazer e em qual canal." },
                  { title: "Ligue em modo de avaliação", description: "Só a sua equipe conversa com ele no começo." },
                  { title: "Acompanhe as conversas", description: "Leia o que ele respondeu e ajuste antes de abrir." },
                  { title: "Abra para todos", description: "E pause ou desligue quando quiser, na hora." },
                ]}
              />

              <LeadCaptureForm
                id="contato"
                variant="product"
                productInterest="agents"
                consentSubject="os Agentes"
                eyebrow="Fale com a gente"
                title="Quer um agente trabalhando na sua empresa?"
                description="Deixe o seu WhatsApp. Uma pessoa da equipe responde em horário comercial para entender o que o agente precisa fazer."
                heading="Pedir contato"
                submitLabel="Pedir contato"
                messageHint="Ex.: “Quero que alguém responda os leads do WhatsApp fora do horário.”"
                successTitle="Pedido recebido."
                successBody="Uma pessoa da equipe vai chamar você no WhatsApp informado, em horário comercial."
                againLabel="Enviar outro pedido"
                onSubmit={submitLead}
              />

              <CtaBand
                id="entrar"
                variant="inverse"
                title="Já tem agentes na sua organização?"
                description="Entre com a sua conta NoctusAI para ver e controlar cada um."
                actions={[
                  { label: "Entrar", href: "/login", variant: "primary" },
                  { label: "Falar com a gente", href: "#contato", variant: "outline" },
                ]}
              />
            </main>

            <LandingFooter
              id="rodape"
              brand={
                <a href="#top" className="inline-flex items-center gap-2 font-semibold text-foreground">
                  <Bot className="h-5 w-5 text-primary" aria-hidden="true" />
                  Agentes
                </a>
              }
              tagline={<>Um produto <a href={CORE} className="underline">NoctusAI</a>.</>}
              columns={[
                {
                  heading: "NoctusAI",
                  links: [
                    { label: "noctusai.com", href: CORE },
                    { label: "Social Wiring", href: SOCIAL_WIRING_URL },
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
      </ProductBrandScope>
    </LandingThemeProvider>
  );
}
