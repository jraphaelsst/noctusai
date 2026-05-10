import { PublicLayout } from '@/components/layout/PublicLayout';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import {
  Heart, Users, Calendar, Brain, Shield, Building2,
  Search, Video, FileText, BarChart3, DollarSign,
  ChevronDown, ChevronUp, Star, ArrowRight,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@noctusai/seed/infra';
import { useState } from 'react';

// ── How it works steps ─────────────────────────────────────

const HOW_IT_WORKS = [
  {
    step: 1,
    icon: Search,
    title: 'Encontre',
    description: 'Busque terapeutas por especialidade, abordagem ou localizacao. Veja avaliacoes e perfis detalhados.',
  },
  {
    step: 2,
    icon: Calendar,
    title: 'Agende',
    description: 'Escolha o melhor horario na agenda do terapeuta. Confirmacao automatica e lembretes.',
  },
  {
    step: 3,
    icon: Video,
    title: 'Conecte',
    description: 'Realize sessoes online com seguranca. Audio, video e chat em um unico ambiente.',
  },
];

// ── Benefits ───────────────────────────────────────────────

const PATIENT_BENEFITS = [
  { icon: Users, title: 'Terapeutas qualificados', description: 'Todos os profissionais passam por processo de verificacao e aprovacao.' },
  { icon: Video, title: 'Sessoes online', description: 'Realize sessoes de qualquer lugar, com total privacidade e seguranca.' },
  { icon: Brain, title: 'Resumos com IA', description: 'Receba resumos automaticos das suas sessoes para acompanhar sua evolucao.' },
  { icon: Calendar, title: 'Agenda flexivel', description: 'Encontre horarios que se encaixam na sua rotina. Recorrencia automatica.' },
];

const THERAPIST_BENEFITS = [
  { icon: BarChart3, title: 'Gestao completa', description: 'Gerencie agenda, pacientes e financeiro em uma unica plataforma.' },
  { icon: FileText, title: 'Prontuario digital', description: 'Resumos clinicos automaticos, tags e acompanhamento longitudinal.' },
  { icon: Brain, title: 'IA assistente', description: 'Transcricao e resumo de sessoes. Mais tempo para o que importa: cuidar.' },
  { icon: DollarSign, title: 'Receba online', description: 'Pagamentos automaticos, carteira digital e saques simplificados.' },
];

const CLINIC_BENEFITS = [
  { icon: Users, title: 'Gerencie terapeutas', description: 'Convide, ative e acompanhe sua equipe de profissionais.' },
  { icon: DollarSign, title: 'Comissoes automaticas', description: 'Configure taxas por terapeuta e receba automaticamente.' },
  { icon: BarChart3, title: 'Relatorios financeiros', description: 'Acompanhe receita, sessoes e desempenho da clinica em tempo real.' },
];

// ── FAQ ────────────────────────────────────────────────────

const FAQ_ITEMS = [
  {
    question: 'Como funciona o agendamento de sessoes?',
    answer: 'Voce escolhe um terapeuta, seleciona um horario disponivel na agenda dele e confirma o agendamento. O pagamento e pre-autorizado no momento da reserva e capturado apos a sessao. Voce recebe lembretes automaticos.',
  },
  {
    question: 'As sessoes sao gravadas?',
    answer: 'As sessoes podem ser gravadas apenas com o consentimento explicito do paciente. As gravacoes sao processadas para gerar resumos automaticos e depois excluidas conforme a politica de retencao configurada.',
  },
  {
    question: 'Como funciona o pagamento?',
    answer: 'O pagamento e pre-autorizado no agendamento e capturado apos a sessao. Terapeutas recebem via carteira digital com opcao de saque para conta bancaria. A plataforma cobra uma taxa sobre cada sessao.',
  },
  {
    question: 'Posso cancelar uma sessao?',
    answer: 'Sim, voce pode cancelar com antecedencia (conforme politica configurada) sem penalidade. Cancelamentos tardios podem estar sujeitos a cobranca parcial.',
  },
  {
    question: 'Meus dados estao protegidos?',
    answer: 'Sim. Utilizamos criptografia em transito e em repouso. A plataforma esta em conformidade com a LGPD e respeita o sigilo profissional terapeutico. Voce pode solicitar exclusao dos seus dados a qualquer momento.',
  },
  {
    question: 'Sou terapeuta, como me cadastro?',
    answer: 'Crie uma conta selecionando "Sou Terapeuta", preencha seu CRP e perfil profissional. Seu cadastro sera analisado e aprovado pela equipe da plataforma.',
  },
];

// ── Testimonials ───────────────────────────────────────────

const TESTIMONIALS = [
  {
    name: 'Ana C.',
    role: 'Paciente',
    text: 'Encontrei minha terapeuta em menos de 5 minutos. A plataforma e super intuitiva e os resumos das sessoes me ajudam muito.',
    rating: 5,
  },
  {
    name: 'Dr. Marcos R.',
    role: 'Terapeuta',
    text: 'Finalmente uma plataforma que entende a rotina do terapeuta. A gestao financeira automatizada me economiza horas por semana.',
    rating: 5,
  },
  {
    name: 'Clinica Mente Saudavel',
    role: 'Clinica',
    text: 'O controle de comissoes e relatorios facilitou muito nossa administracao. Recomendo para qualquer clinica.',
    rating: 5,
  },
];

// ── FAQ Accordion Item ─────────────────────────────────────

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b last:border-b-0">
      <button
        className="w-full flex items-center justify-between py-4 text-left hover:text-primary transition-colors"
        onClick={() => setOpen(!open)}
      >
        <span className="font-medium text-sm pr-4">{question}</span>
        {open ? (
          <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
      </button>
      {open && (
        <div className="pb-4 pr-8">
          <p className="text-sm text-muted-foreground">{answer}</p>
        </div>
      )}
    </div>
  );
}

// ── Landing Page ───────────────────────────────────────────

export default function Landing() {
  const { user } = useAuthStore();
  const navigate = useNavigate();

  const handleCTA = (path: string) => {
    if (user) {
      navigate('/therapists');
    } else {
      navigate(`/register?redirect_to=${encodeURIComponent(path)}`);
    }
  };

  return (
    <PublicLayout>
      {/* ── Hero ──────────────────────────────────────── */}
      <section className="py-20 sm:py-28 px-4 text-center bg-gradient-to-b from-primary/5 to-background">
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 text-primary text-sm font-medium mb-4">
            <Heart className="h-4 w-4" />
            Plataforma de Terapia Online
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">
            Saude mental ao seu alcance
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Conectamos pacientes a terapeutas qualificados. Agende sessoes online,
            acompanhe sua evolucao e cuide da sua saude mental com tecnologia e seguranca.
          </p>
          <div className="flex items-center justify-center gap-3 pt-2">
            <Button size="lg" onClick={() => handleCTA('/therapists')}>
              Encontrar Terapeuta <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
            <Button size="lg" variant="outline" onClick={() => handleCTA('/register')}>
              Sou Terapeuta
            </Button>
          </div>
        </div>
      </section>

      {/* ── How it works ──────────────────────────────── */}
      <section className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-4">Como funciona</h2>
          <p className="text-center text-muted-foreground mb-12 max-w-2xl mx-auto">
            Em tres passos simples, voce comeca sua jornada terapeutica.
          </p>
          <div className="grid gap-8 grid-cols-1 md:grid-cols-3">
            {HOW_IT_WORKS.map(item => (
              <div key={item.step} className="text-center space-y-4">
                <div className="inline-flex items-center justify-center h-16 w-16 rounded-full bg-primary/10 mx-auto">
                  <item.icon className="h-7 w-7 text-primary" />
                </div>
                <div className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-primary text-primary-foreground text-sm font-bold">
                  {item.step}
                </div>
                <h3 className="text-lg font-semibold">{item.title}</h3>
                <p className="text-sm text-muted-foreground">{item.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── For patients ──────────────────────────────── */}
      <section className="py-20 px-4 bg-muted/50">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-4">Para Pacientes</h2>
          <p className="text-center text-muted-foreground mb-12">
            Tudo o que voce precisa para cuidar da sua saude mental.
          </p>
          <div className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
            {PATIENT_BENEFITS.map(b => (
              <Card key={b.title}>
                <CardContent className="p-6 text-center">
                  <div className="inline-flex items-center justify-center p-3 rounded-full bg-primary/10 mb-4">
                    <b.icon className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="font-semibold mb-2">{b.title}</h3>
                  <p className="text-sm text-muted-foreground">{b.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ── For therapists ────────────────────────────── */}
      <section className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-4">Para Terapeutas</h2>
          <p className="text-center text-muted-foreground mb-12">
            Foque no que importa — a plataforma cuida do resto.
          </p>
          <div className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
            {THERAPIST_BENEFITS.map(b => (
              <Card key={b.title}>
                <CardContent className="p-6 text-center">
                  <div className="inline-flex items-center justify-center p-3 rounded-full bg-primary/10 mb-4">
                    <b.icon className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="font-semibold mb-2">{b.title}</h3>
                  <p className="text-sm text-muted-foreground">{b.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ── For clinics ───────────────────────────────── */}
      <section className="py-20 px-4 bg-muted/50">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-4">Para Clinicas</h2>
          <p className="text-center text-muted-foreground mb-12">
            Gerencie sua clinica com eficiencia e transparencia.
          </p>
          <div className="grid gap-6 grid-cols-1 sm:grid-cols-3">
            {CLINIC_BENEFITS.map(b => (
              <Card key={b.title}>
                <CardContent className="p-6 text-center">
                  <div className="inline-flex items-center justify-center p-3 rounded-full bg-primary/10 mb-4">
                    <b.icon className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="font-semibold mb-2">{b.title}</h3>
                  <p className="text-sm text-muted-foreground">{b.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ── Testimonials ──────────────────────────────── */}
      <section className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">O que dizem nossos usuarios</h2>
          <div className="grid gap-6 grid-cols-1 md:grid-cols-3">
            {TESTIMONIALS.map(t => (
              <Card key={t.name}>
                <CardContent className="p-6 space-y-4">
                  <div className="flex items-center gap-0.5">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Star
                        key={i}
                        className={`h-4 w-4 ${i < t.rating ? 'text-yellow-500 fill-yellow-500' : 'text-muted-foreground/30'}`}
                      />
                    ))}
                  </div>
                  <p className="text-sm italic text-muted-foreground">"{t.text}"</p>
                  <div>
                    <p className="font-medium text-sm">{t.name}</p>
                    <p className="text-xs text-muted-foreground">{t.role}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ── FAQ ────────────────────────────────────────── */}
      <section className="py-20 px-4 bg-muted/50">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">Perguntas Frequentes</h2>
          <Card>
            <CardContent className="p-6">
              {FAQ_ITEMS.map(item => (
                <FAQItem key={item.question} question={item.question} answer={item.answer} />
              ))}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* ── CTA final ─────────────────────────────────── */}
      <section className="py-20 px-4 text-center">
        <div className="max-w-2xl mx-auto space-y-6">
          <h2 className="text-3xl font-bold">Comece sua jornada hoje</h2>
          <p className="text-muted-foreground">
            Cadastre-se gratuitamente e encontre o terapeuta ideal para voce.
          </p>
          <Button size="lg" onClick={() => handleCTA('/therapists')}>
            Comecar Agora <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────── */}
      <footer className="border-t bg-card py-8 px-4">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Heart className="h-5 w-5 text-primary" />
            <span className="font-semibold text-primary">NoctusAI Terapia</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <Link to="/termos" className="hover:text-foreground transition-colors">Termos de Uso</Link>
            <Link to="/privacidade" className="hover:text-foreground transition-colors">Privacidade</Link>
            <Link to="/suporte" className="hover:text-foreground transition-colors">Suporte</Link>
          </div>
          <p className="text-xs text-muted-foreground">
            {new Date().getFullYear()} NoctusAI. Todos os direitos reservados.
          </p>
        </div>
      </footer>
    </PublicLayout>
  );
}
