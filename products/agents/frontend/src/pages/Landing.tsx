/**
 * Agentes — public landing (agents.noctusai.com).
 *
 * Built from the seed landing organs (`@noctusai/lib/marketing`): nav, hero (media slot),
 * two feature grids, steps, lead form, CTA band, footer. Copy and structure follow the
 * owner-approved mockup. The hero panel is an ILLUSTRATION (labelled "Amostra"), not live data.
 * Legal links point to the seed-mounted /consent/* routes.
 */
import { useState } from "react";
import {
  Bot, FlaskConical, GitMerge, Lock, MessageCircle, Power, ShieldCheck, Target,
} from "lucide-react";
import { env } from "@noctusai/lib";
import {
  CtaBand, FeatureGrid, Hero, LandingFooter, LandingNav, LeadCaptureForm, MotionProvider, Steps,
} from "@noctusai/lib/marketing";
import type { ThemeChoice } from "@noctusai/lib/marketing";
import { submitAgentsLead } from "@/lib/landingLead";

const CORE = env.CORE_URL.replace(/\/+$/, "");
const SOCIAL_WIRING_URL = `${CORE}/produtos/social-wiring`;

const THEME_KEY = "theme"; // the seed's own key (useTheme) — the app picks the same choice up after login

function applyTheme(choice: ThemeChoice) {
  const dark =
    choice === "dark" || (choice === "system" && !!window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

/** Event-handler driven (no effect): the choice is applied where it is made. */
function useLandingTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(() => {
    const saved = typeof window !== "undefined" ? window.localStorage.getItem(THEME_KEY) : null;
    return saved === "light" || saved === "dark" ? saved : "system";
  });
  const change = (next: ThemeChoice) => {
    setChoice(next);
    if (next === "system") window.localStorage.removeItem(THEME_KEY);
    else window.localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  };
  return { choice, change };
}

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

/** Illustrative panel for the hero media slot. Sample data — says so on the panel. */
function AgentsPanel() {
  return (
    <div className="w-full space-y-3 p-2 text-left">
      <div className="flex items-center justify-between text-sm font-semibold text-foreground">
        <span>Agentes da organização</span>
        <span className="rounded-full border border-input px-2 py-0.5 text-xs font-medium text-muted-foreground">Amostra</span>
      </div>
      <div className="rounded-lg border border-border bg-card p-3">
        <div className="flex items-center gap-3">
          <MessageCircle className="h-5 w-5 text-primary" aria-hidden="true" />
          <div className="flex flex-col">
            <strong className="text-sm text-foreground">Julia</strong>
            <small className="text-xs text-muted-foreground">Qualificação de leads · WhatsApp</small>
          </div>
        </div>
        <Segmented />
      </div>
      <div className="rounded-lg border border-border bg-card p-3">
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
          <span><b>Fase de testes</b>: responde só a pessoas liberadas</span>
        </p>
      </div>
    </div>
  );
}

const HERO_MEDIA_LABEL =
  "Exemplo ilustrativo do painel de agentes: a Julia está ligada no WhatsApp; a Bia está em fase de testes, respondendo só a pessoas liberadas. Dados de amostra.";

const icon = (Icon: typeof Power) => <Icon className="h-5 w-5" aria-hidden="true" />;

export default function Landing() {
  const { choice, change } = useLandingTheme();

  return (
    <MotionProvider>
      <div className="min-h-screen bg-background text-foreground">
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
          primaryAction={{ label: "Falar com a gente", href: "#contato" }}
          themeSwitch={{ value: choice, onChange: change }}
        />

        <main id="main" tabIndex={-1}>
          <Hero
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
            eyebrow="Os agentes"
            title="Cada agente tem um trabalho claro"
            description="Um agente faz uma coisa bem feita e sabe a hora de chamar uma pessoa."
            items={[
              {
                icon: icon(MessageCircle),
                title: "Julia · qualificação de leads",
                description:
                  "WhatsApp. Responde quem chega pelo WhatsApp, faz as perguntas de qualificação e passa para a equipe quem está pronto. " +
                  "Dá nota ao lead por regras fixas: o mesmo lead recebe sempre a mesma nota. " +
                  "Consulta os imóveis cadastrados antes de responder. " +
                  "Quando um cliente reclama, avisa a equipe.",
                cta: { label: "A Julia atende pelo Social Wiring", href: SOCIAL_WIRING_URL },
              },
              {
                icon: icon(Bot),
                title: "Bia · assistente da equipe",
                description:
                  "Web. Consulta a base de conhecimento da organização e propõe alterações. Nada é gravado sem a sua aprovação. " +
                  "Responde dentro do navegador, para a equipe. " +
                  "Cada alteração vira um pedido que você aprova ou recusa.",
              },
            ]}
          />

          <FeatureGrid
            id="controle"
            eyebrow="Controle"
            title="Você decide quando e com quem cada agente fala"
            items={[
              { icon: icon(Power), title: "Ligado, drenando ou desligado", description: "Drenando: o agente termina as conversas em andamento e não começa novas." },
              { icon: icon(FlaskConical), title: "Fase de testes", description: "Antes de abrir para todos, o agente só responde às pessoas que você liberou." },
              { icon: icon(GitMerge), title: "Uma conversa por lead", description: "Quando o lead passa de um agente para outro, ou para a equipe, a conversa continua no mesmo histórico." },
              { icon: icon(Target), title: "Regras que não mudam no meio do caminho", description: "Cada agente segue uma versão definida das regras, e cada resposta é conferida antes de sair." },
              { icon: icon(Lock), title: "Dados do lead protegidos", description: "Nome e contato do lead ficam criptografados no banco. O consentimento fica registrado na conversa." },
              { icon: icon(ShieldCheck), title: "Proteção contra abuso", description: "Limites por conversa e respostas que não revelam as instruções internas do agente." },
            ]}
          />

          <Steps
            id="como-funciona"
            eyebrow="Como funciona"
            title="Do primeiro teste ao atendimento de verdade"
            steps={[
              { title: "Escolha o agente", description: "Defina qual trabalho ele vai fazer e em qual canal." },
              { title: "Ligue em fase de testes", description: "Só a sua equipe conversa com ele no começo." },
              { title: "Acompanhe as conversas", description: "Leia o que ele respondeu e ajuste antes de abrir." },
              { title: "Abra para todos", description: "E pause ou desligue quando quiser, na hora." },
            ]}
          />

          <LeadCaptureForm
            id="contato"
            variant="brief"
            eyebrow="Fale com a gente"
            title="Quer um agente trabalhando na sua empresa?"
            description="Deixe o seu WhatsApp. Uma pessoa da equipe responde em horário comercial para entender o que o agente precisa fazer."
            heading="Pedir contato"
            onSubmit={submitAgentsLead}
          />

          <CtaBand
            id="entrar"
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
          tagline="Um produto NoctusAI."
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
  );
}
