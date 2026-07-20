import { Link } from "react-router-dom";
import { Box, ArrowRight } from "lucide-react";
import { env } from "@noctusai/lib";

// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;

export default function Landing() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* ── Navbar ─────────────────────────────────────── */}
      <header className="h-16 border-b border-border bg-card px-4 sm:px-8 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <Box className="h-7 w-7 text-primary" />
          <span className="text-xl font-bold text-primary">
            Orbity
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
      <section className="py-20 sm:py-28 px-4 text-center bg-gradient-to-b from-primary/5 to-background flex-1 flex flex-col items-center justify-center">
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 text-primary text-sm font-medium">
            <Box className="h-4 w-4" />
            NoctusAI Orbity
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-foreground">
            Gestão completa para agências, em um só lugar
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Clientes, funil de vendas, tarefas, agenda, financeiro, tráfego
            (Meta Ads), automação de WhatsApp e conteúdo — sua agência
            organizada do primeiro contato à entrega.
          </p>
          <div className="flex items-center justify-center gap-3 pt-2">
            <Link
              to="/login"
              className="inline-flex items-center justify-center gap-2 h-11 px-6 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              Começar Agora
              <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href={CORE_URL}
              className="inline-flex items-center justify-center h-11 px-6 rounded-md border border-input bg-background text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              Conhecer a NoctusAI
            </a>
          </div>
        </div>
      </section>

      {/* ── Módulos ────────────────────────────────────── */}
      <section className="py-16 px-4 border-t border-border bg-card">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl sm:text-3xl font-bold text-center text-foreground mb-10">
            Tudo o que sua agência precisa para operar
          </h2>
          <div className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature) => (
              <div
                key={feature.title}
                className="rounded-lg border border-border bg-background p-6 space-y-2"
              >
                <h3 className="font-semibold text-foreground">
                  {feature.title}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────── */}
      <footer className="border-t bg-card py-8 px-4 mt-auto">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Box className="h-5 w-5 text-primary" />
            <span className="font-semibold text-primary">
              Orbity
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

const FEATURES = [
  {
    title: "CRM e Funil de Vendas",
    description:
      "Cadastre clientes, acompanhe leads em um funil kanban e nunca perca uma oportunidade.",
  },
  {
    title: "Tarefas, Agenda e Rotinas",
    description:
      "Organize entregas, compromissos e processos recorrentes da equipe em um só painel.",
  },
  {
    title: "Financeiro",
    description:
      "Contratos, despesas, receitas e fluxo de caixa mensal sempre à mão.",
  },
  {
    title: "Tráfego (Meta Ads)",
    description:
      "Conecte contas de anúncio, acompanhe campanhas e métricas de investimento por cliente.",
  },
  {
    title: "Automação de WhatsApp",
    description:
      "Fluxos automáticos de mensagens para cada etapa da jornada do cliente.",
  },
  {
    title: "Conteúdo e Relatórios",
    description:
      "Aprovação de posts com clientes e relatórios compartilháveis por link público.",
  },
];
