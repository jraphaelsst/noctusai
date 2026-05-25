import { Link } from "react-router-dom";
import {
  DollarSign,
  Wallet,
  ArrowLeftRight,
  Target,
  TrendingUp,
  PieChart,
  BarChart3,
  ArrowRight,
  Shield,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { env } from "@noctusai/lib";

// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;

// ── Features ──────────────────────────────────────────────

interface Feature {
  icon: LucideIcon;
  title: string;
  description: string;
}

const FEATURES: Feature[] = [
  {
    icon: Wallet,
    title: "Contas",
    description:
      "Gerencie todas as suas contas bancarias, carteiras e cartoes em um unico lugar.",
  },
  {
    icon: ArrowLeftRight,
    title: "Transacoes",
    description:
      "Registre receitas e despesas com categorias, tags e busca inteligente.",
  },
  {
    icon: Target,
    title: "Orcamentos",
    description:
      "Defina limites por categoria e acompanhe seus gastos em tempo real.",
  },
  {
    icon: TrendingUp,
    title: "Investimentos",
    description:
      "Acompanhe carteiras, rendimentos e alocacao de ativos com cotacoes atualizadas.",
  },
  {
    icon: PieChart,
    title: "Metas",
    description:
      "Crie metas financeiras e visualize seu progresso ate atingi-las.",
  },
  {
    icon: BarChart3,
    title: "Relatorios",
    description:
      "Analise seus dados com graficos, tendencias e comparativos mensais.",
  },
];

// ── Feature Card ──────────────────────────────────────────

function FeatureCard({ icon: Icon, title, description }: Feature) {
  return (
    <div className="rounded-lg border border-border bg-card p-6 text-center space-y-3 hover:shadow-md transition-shadow">
      <div className="inline-flex items-center justify-center p-3 rounded-full bg-primary/10 mx-auto">
        <Icon className="h-6 w-6 text-primary" />
      </div>
      <h3 className="font-semibold text-foreground">{title}</h3>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  );
}

// ── Landing Page ──────────────────────────────────────────

export default function Landing() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* ── Navbar ─────────────────────────────────────── */}
      <header className="h-16 border-b border-border bg-card px-4 sm:px-8 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <DollarSign className="h-7 w-7 text-primary" />
          <span className="text-xl font-bold text-primary">
            Financas Pessoais
          </span>
        </Link>
        <Link
          to="/login"
          className="inline-flex items-center justify-center h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Entrar
        </Link>
      </header>

      {/* ── Hero ───────────────────────────────────────── */}
      <section className="py-20 sm:py-28 px-4 text-center bg-gradient-to-b from-primary/5 to-background">
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 text-primary text-sm font-medium">
            <DollarSign className="h-4 w-4" />
            Controle Financeiro Inteligente
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-foreground">
            Suas financas sob controle
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Organize contas, acompanhe investimentos e atinja suas metas
            financeiras com uma plataforma completa e intuitiva.
          </p>
          <div className="flex items-center justify-center gap-3 pt-2">
            <Link
              to="/login"
              className="inline-flex items-center justify-center gap-2 h-11 px-6 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              Comecar Agora
              <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href={CORE_URL}
              className="inline-flex items-center justify-center h-11 px-6 rounded-md border border-input bg-background text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              Conhecer NoctusAI
            </a>
          </div>
        </div>
      </section>

      {/* ── Features ───────────────────────────────────── */}
      <section className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-4 text-foreground">
            Tudo que voce precisa
          </h2>
          <p className="text-center text-muted-foreground mb-12 max-w-2xl mx-auto">
            Ferramentas completas para gerenciar cada aspecto da sua vida
            financeira.
          </p>
          <div className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <FeatureCard key={f.title} {...f} />
            ))}
          </div>
        </div>
      </section>

      {/* ── Highlights ─────────────────────────────────── */}
      <section className="py-20 px-4 bg-muted/50">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12 text-foreground">
            Por que usar?
          </h2>
          <div className="grid gap-8 grid-cols-1 md:grid-cols-3">
            <div className="text-center space-y-3">
              <div className="inline-flex items-center justify-center h-14 w-14 rounded-full bg-primary/10 mx-auto">
                <Shield className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-semibold text-foreground">Seguro</h3>
              <p className="text-sm text-muted-foreground">
                Seus dados protegidos com criptografia e isolamento por
                organizacao.
              </p>
            </div>
            <div className="text-center space-y-3">
              <div className="inline-flex items-center justify-center h-14 w-14 rounded-full bg-primary/10 mx-auto">
                <Zap className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-semibold text-foreground">Rapido</h3>
              <p className="text-sm text-muted-foreground">
                Interface leve e responsiva. Acesse de qualquer dispositivo, a
                qualquer momento.
              </p>
            </div>
            <div className="text-center space-y-3">
              <div className="inline-flex items-center justify-center h-14 w-14 rounded-full bg-primary/10 mx-auto">
                <TrendingUp className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-semibold text-foreground">Inteligente</h3>
              <p className="text-sm text-muted-foreground">
                Cotacoes em tempo real, categorizacao automatica e relatorios que
                ajudam na tomada de decisao.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA ────────────────────────────────────────── */}
      <section className="py-20 px-4 text-center">
        <div className="max-w-2xl mx-auto space-y-6">
          <h2 className="text-3xl font-bold text-foreground">
            Comece a organizar suas financas
          </h2>
          <p className="text-muted-foreground">
            Crie sua conta gratuitamente e tenha visibilidade total sobre seu
            dinheiro.
          </p>
          <Link
            to="/login"
            className="inline-flex items-center justify-center gap-2 h-11 px-6 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            Comecar Agora
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────── */}
      <footer className="border-t bg-card py-8 px-4 mt-auto">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <DollarSign className="h-5 w-5 text-primary" />
            <span className="font-semibold text-primary">
              NoctusAI Financas
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {new Date().getFullYear()} NoctusAI. Todos os direitos reservados.
          </p>
        </div>
      </footer>
    </div>
  );
}
