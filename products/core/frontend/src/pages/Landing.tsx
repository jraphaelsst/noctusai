/**
 * NoctusAI Core — public landing page (the apex / front door at noctusai.com).
 *
 * Rendered at `/landing`; the seed framework redirects unauthenticated visitors
 * here (`unauthRedirect: '/landing'` in main.tsx). The login form lives at
 * `/login`. Authenticated users land on the dashboard (`/`).
 *
 * Platform-level marketing (core is the platform shell / SSO hub), distinct
 * from per-product landings like ERP's.
 */
import { Link } from "react-router-dom";
import { Button } from "@noctusai/seed/components/ui/button";
import {
  Zap, Building2, Wallet, HeartPulse, Share2, CalendarCheck,
  ShieldCheck, Brain, ArrowRight,
} from "lucide-react";
import { LandingFooter } from "../components/LandingFooter";

const PRODUCTS = [
  {
    icon: Building2,
    title: "ERP Imobiliário",
    description: "CRM, funil de vendas, financeiro, documentos e matching com IA para imobiliárias.",
  },
  {
    icon: Wallet,
    title: "Finanças Pessoais",
    description: "Contas, transações, orçamentos, investimentos e patrimônio em um só lugar.",
  },
  {
    icon: HeartPulse,
    title: "Plataforma de Terapia",
    description: "Sessões por vídeo, agendamento, prontuário digital e gestão financeira clínica.",
  },
  {
    icon: Share2,
    title: "Social Wiring",
    description: "E-mail marketing e agendamento de WhatsApp com IA conversacional integrada.",
  },
  {
    icon: CalendarCheck,
    title: "Daily Life",
    description: "Hub de produtividade pessoal: tarefas, metas, hábitos, agenda e notas.",
  },
] as const;

const PILLARS = [
  {
    icon: Brain,
    title: "AI-First",
    description: "Inteligência artificial embarcada em cada produto — não um add-on, mas o núcleo.",
  },
  {
    icon: ShieldCheck,
    title: "Seguro e conforme",
    description: "Multi-tenant com isolamento por organização (RLS) e conformidade com a LGPD.",
  },
  {
    icon: Zap,
    title: "Um login, todos os produtos",
    description: "Single sign-on: acesse todo o portfólio com uma única conta NoctusAI.",
  },
] as const;

export default function Landing() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ── Navbar ──────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-4 h-14">
          <div className="flex items-center gap-2">
            <Zap className="h-6 w-6 text-primary" />
            <span className="font-semibold text-lg">NoctusAI</span>
          </div>
          <Link
            to="/login"
            className="text-sm font-medium text-muted-foreground hover:text-foreground focus-visible:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm transition-colors px-1"
          >
            Entrar
          </Link>
        </div>
      </nav>

      {/* ── Hero ────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-4 py-20 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm text-muted-foreground mb-6">
          <Zap className="h-4 w-4 text-primary" />
          Plataforma de Produtos Digitais AI-First
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight max-w-3xl mx-auto">
          Um portfólio de produtos, uma única plataforma inteligente
        </h1>
        <p className="mt-6 text-lg text-muted-foreground max-w-2xl mx-auto">
          ERP imobiliário, finanças pessoais, terapia online, social media e produtividade —
          todos construídos sobre a mesma base, com IA no centro e um único login.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Button asChild size="lg">
            <Link to="/login">
              Entrar <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <a href="#produtos">Conhecer os produtos</a>
          </Button>
        </div>
      </section>

      {/* ── Products ────────────────────────────────────────── */}
      <section id="produtos" className="max-w-6xl mx-auto px-4 py-16">
        <h2 className="text-2xl font-bold text-center">Nossos produtos</h2>
        <p className="mt-2 text-center text-muted-foreground">
          Cada produto é completo por si só — e melhor ainda em conjunto.
        </p>
        <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {PRODUCTS.map(({ icon: Icon, title, description }) => (
            <div key={title} className="rounded-lg border p-6 bg-card">
              <Icon className="h-8 w-8 text-primary" />
              <h3 className="mt-4 text-lg font-semibold">{title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Pillars ─────────────────────────────────────────── */}
      <section className="border-t bg-muted/30">
        <div className="max-w-6xl mx-auto px-4 py-16 grid gap-8 sm:grid-cols-3">
          {PILLARS.map(({ icon: Icon, title, description }) => (
            <div key={title}>
              <Icon className="h-7 w-7 text-primary" />
              <h3 className="mt-3 font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer CTA ──────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-4 py-20 text-center">
        <h2 className="text-2xl font-bold">Pronto para começar?</h2>
        <p className="mt-2 text-muted-foreground">Acesse sua conta NoctusAI.</p>
        <Button asChild size="lg" className="mt-6">
          <Link to="/login">
            Entrar <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      </section>

      <LandingFooter />
    </div>
  );
}
