import { Link } from "react-router-dom";
import { Button } from "@noctusai/seed/components/ui/button";
import {
  Building2, Users, Filter, Brain, MessageSquare,
  DollarSign, FileText, ArrowRight,
} from "lucide-react";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

const FEATURES = [
  {
    icon: Users,
    title: "CRM Imobiliario",
    description: "Gestao completa de clientes, leads e proprietarios com historico de interacoes e scoring automatico.",
  },
  {
    icon: Filter,
    title: "Funil de Vendas",
    description: "Acompanhe negociacoes do primeiro contato ao fechamento. Visao Kanban com etapas personalizaveis.",
  },
  {
    icon: Brain,
    title: "IA Matching",
    description: "Algoritmo inteligente que cruza imoveis e interesses de clientes automaticamente.",
  },
  {
    icon: MessageSquare,
    title: "WhatsApp Integrado",
    description: "Envie mensagens, receba leads e gerencie conversas direto da plataforma.",
  },
  {
    icon: DollarSign,
    title: "Financeiro",
    description: "Comissoes, propostas, contratos e fluxo de caixa em um unico lugar.",
  },
  {
    icon: FileText,
    title: "Documentos e Certidoes",
    description: "Gerencie contratos, vistorias, assinaturas digitais e certidoes negativas.",
  },
] as const;

export default function Landing() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ── Navbar ──────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-4 h-14">
          <div className="flex items-center gap-2">
            <Building2 className="h-6 w-6 text-primary" />
            <span className="font-semibold text-lg">ERP Imobiliario</span>
          </div>
          <Button asChild size="sm">
            <Link to="/login">Entrar</Link>
          </Button>
        </div>
      </nav>

      {/* ── Hero ───────────────────────────────────────── */}
      <section className="py-20 sm:py-28 px-4 text-center bg-gradient-to-b from-primary/5 to-background">
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 text-primary text-sm font-medium">
            <Building2 className="h-4 w-4" />
            Gestao Imobiliaria Inteligente
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">
            Seu ERP imobiliario completo
          </h1>
          <p className="text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto">
            CRM, funil de vendas, financeiro, documentos e inteligencia artificial
            em uma unica plataforma para imobiliarias e corretores.
          </p>
          <div className="flex items-center justify-center gap-3 pt-2">
            <Button size="lg" asChild>
              <Link to="/login">
                Entrar <ArrowRight className="h-4 w-4 ml-2" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <a href="#funcionalidades">Conhecer</a>
            </Button>
          </div>
        </div>
      </section>

      {/* ── Features ───────────────────────────────────── */}
      <section id="funcionalidades" className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-4">Funcionalidades</h2>
          <p className="text-center text-muted-foreground mb-12 max-w-2xl mx-auto">
            Tudo o que sua imobiliaria precisa para operar com eficiencia.
          </p>
          <div className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature) => (
              <div
                key={feature.title}
                className="rounded-lg border bg-card p-6 space-y-3 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="inline-flex items-center justify-center p-3 rounded-full bg-primary/10">
                  <feature.icon className="h-6 w-6 text-primary" />
                </div>
                <h3 className="font-semibold text-lg">{feature.title}</h3>
                <p className="text-sm text-muted-foreground">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────── */}
      <footer className="border-t bg-card py-8 px-4">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" />
            <span className="font-semibold text-primary">ERP Imobiliario</span>
          </div>
          <a
            href={CORE_URL}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            NoctusAI
          </a>
          <p className="text-xs text-muted-foreground">
            {new Date().getFullYear()} NoctusAI. Todos os direitos reservados.
          </p>
        </div>
      </footer>
    </div>
  );
}
