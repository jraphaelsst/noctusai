/**
 * Social Wiring App — media-wiring CMS.
 *
 * Infrastructure comes from @noctusai/seed/infra (one createProductInfra
 * call). Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav — zero boilerplate.
 *
 * Nav (nested groups, regrouped 2026-10-05 per core-studio/MENUS.md; items/routes unchanged):
 *   Principal · Imóveis · Leads · Clientes
 *   Edição de Fotos (Operação / Configuração) · Criação de mídia
 *   Marketing (Email / Mailchimp) · Emissões
 *   Conexões (Marcas, Monitor, YouTube, Meta, WhatsApp, n8n) · Configuração
 *
 * The former "Integrações" nav item is folded into "Conexões" — both the
 * /conexoes and /integrations routes point to the same Conexoes page.
 * The former separate "Conexão" (WhatsApp-only) is now embedded inside Conexoes.
 * The standalone /conexao route is kept for back-compat (direct WAHA management).
 *
 * WhatsApp (`/whatsapp-chat`) is back in nav as of the SocialDashboardShell
 * remodel (componentization wave, N=3) — it's now a full dashboard (Chat +
 * Configurações subtabs), not just the connection-scoped Chat tab MarcaModal
 * already surfaces. The `whatsapp_chat` status_pagina row already exists
 * (migration 014, status='producao') from when this route was last in nav —
 * no new migration needed to make it visible again.
 * pt-BR copy preserved.
 */
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from '@noctusai/seed/infra';
import { useSocialWiringLayoutEnrichment } from "@/hooks/useLayoutEnrichment";
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import {
  LayoutDashboard,
  Users,
  Home,
  Mail,
  Settings as SettingsIcon,
  Settings2,
  Smartphone,
  Activity,
  Share2,
  Wand2,
  Youtube,
  Instagram,
  UserRound,
  List,
  FileText,
  Send,
  ArrowLeftRight,
  Building2,
  Target,
  Megaphone,
  KanbanSquare,
  Workflow,
  TrendingUp,
  UserCheck,
  GitMerge,
  CalendarClock,
  BarChart3,
  Globe,
  Stamp,
  Landmark,
  ScrollText,
  ShieldCheck,
  ImagePlus,
  Images,
  BookOpen,
  Cpu,
  Plus,
  UserCog,
  Wallet,
  Search,
  Lightbulb,
  Sparkles,
  Brain,
  MessagesSquare,
  Library,
  GraduationCap,
  Heading,
  Star,
  Clapperboard,
  Bookmark,
} from "lucide-react";

import { lazyWithReload } from "@noctusai/lib";

// Pages
const Landing = lazyWithReload(() => import("@/pages/Landing"));
const Login = lazyWithReload(() => import("@/pages/Login"));
const AcceptInvite = lazyWithReload(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazyWithReload(() => import("@/pages/ForgotPassword"));
const Chat = lazyWithReload(() => import("@/pages/Chat"));
const Dashboard = lazyWithReload(() => import("@/pages/Dashboard"));
const Equipe = lazyWithReload(() => import("@/pages/Equipe"));
const Custos = lazyWithReload(() => import("@/pages/Custos"));
const Permutas = lazyWithReload(() => import("@/pages/Permutas"));
const Settings = lazyWithReload(() => import("@/pages/Settings"));
const YouTube = lazyWithReload(() => import("@/pages/YouTube"));
const N8n = lazyWithReload(() => import("@/pages/N8n"));
const RedirectToMarcas = lazyWithReload(() => import("@/pages/RedirectToMarcas"));
const RedirectToMeta = lazyWithReload(() => import("@/pages/RedirectToMeta"));
const Monitor = lazyWithReload(() => import("@/pages/Monitor"));
const MediaCreation = lazyWithReload(() => import("@/pages/MediaCreation"));
const EmailMarketing = lazyWithReload(() => import("@/pages/EmailMarketing"));
const Contatos = lazyWithReload(() => import("@/pages/Contatos"));
const EmailListas = lazyWithReload(() => import("@/pages/EmailListas"));
const EmailTemplates = lazyWithReload(() => import("@/pages/EmailTemplates"));
const EmailCampanhas = lazyWithReload(() => import("@/pages/EmailCampanhas"));
const EmailMarketingConfig = lazyWithReload(() => import("@/pages/EmailMarketingConfig"));
const EmailMembros = lazyWithReload(() => import("@/pages/EmailMembros"));
const NotFound = lazyWithReload(() => import("@/pages/NotFound"));
const WhatsAppChat = lazyWithReload(() => import("@/pages/WhatsAppChat"));
const Marcas = lazyWithReload(() => import("@/pages/Marcas"));
const Imoveis = lazyWithReload(() => import("@/pages/Imoveis"));
const ImovelDetalhes = lazyWithReload(() => import("@/pages/ImovelDetalhes"));
const MetaDashboard = lazyWithReload(() => import("@/pages/MetaDashboard"));
const Leads = lazyWithReload(() => import("@/pages/leads/Leads"));
const Campanhas = lazyWithReload(() => import("@/pages/campanhas/Campanhas"));
const FunilVendas = lazyWithReload(() => import("@/pages/funil/FunilVendas"));
const ProcessosVenda = lazyWithReload(() => import("@/pages/funil/ProcessosVenda"));
const PortalRoi = lazyWithReload(() => import("@/pages/PortalRoi"));
const ClientesBoard = lazyWithReload(() => import("@/pages/clientes/ClientesBoard"));
const RevisaoFila = lazyWithReload(() => import("@/pages/clientes/RevisaoFila"));
const PessoaPage = lazyWithReload(() => import("@/pages/PessoaPage"));
const Agendamentos = lazyWithReload(() => import("@/pages/scheduling/Agendamentos"));
const EmailPainel = lazyWithReload(() => import("@/pages/email/Painel"));
const EmailCampanhasNoc = lazyWithReload(() => import("@/pages/email/Campanhas"));
const EmailContatosNoc = lazyWithReload(() => import("@/pages/email/Contatos"));
const EmailListasNoc = lazyWithReload(() => import("@/pages/email/Listas"));
const EmailTemplatesNoc = lazyWithReload(() => import("@/pages/email/Templates"));
const EmailAutomacoes = lazyWithReload(() => import("@/pages/email/Automacoes"));
const EmailDominios = lazyWithReload(() => import("@/pages/email/Dominios"));
const EmailDescadastro = lazyWithReload(() => import("@/pages/email/Descadastro"));
const EmailConfirmarEmail = lazyWithReload(() => import("@/pages/email/ConfirmarEmail"));
const Certidoes = lazyWithReload(() => import("@/pages/Certidoes"));
const Matriculas = lazyWithReload(() => import("@/pages/Matriculas"));
const AgentesFinanceiros = lazyWithReload(
  () => import("@/pages/AgentesFinanceiros"),
);
const Testemunhas = lazyWithReload(() => import("@/pages/Testemunhas"));
const Pesquisa = lazyWithReload(() => import("@/pages/Pesquisa"));
const ExtrairPesquisa = lazyWithReload(() => import("@/pages/ExtrairPesquisa"));
const CerebroLista = lazyWithReload(() => import("@/pages/cerebro/CerebroLista"));
const CerebroEditor = lazyWithReload(() => import("@/pages/cerebro/CerebroEditor"));
const CerebroPerguntas = lazyWithReload(() => import("@/pages/cerebro/CerebroPerguntas"));
const GeracaoDashboard = lazyWithReload(() => import("@/pages/geracao/Dashboard"));
const GeracaoChat = lazyWithReload(() => import("@/pages/geracao/Chat"));
const GeracaoBiblioteca = lazyWithReload(() => import("@/pages/geracao/Biblioteca"));
const GeracaoMeuPerfil = lazyWithReload(() => import("@/pages/geracao/MeuPerfil"));
const GeracaoMinhaBiblioteca = lazyWithReload(() => import("@/pages/geracao/MinhaBiblioteca"));
const GeracaoTreinamentos = lazyWithReload(() => import("@/pages/geracao/Treinamentos"));
const GeracaoHeadlinesGerar = lazyWithReload(() => import("@/pages/geracao/HeadlinesGerar"));
const GeracaoHeadlines = lazyWithReload(() => import("@/pages/geracao/Headlines"));
const GeracaoHeadlinesFavoritas = lazyWithReload(() => import("@/pages/geracao/HeadlinesFavoritas"));
const GeracaoHeadlinesSugeridas = lazyWithReload(() => import("@/pages/geracao/HeadlinesSugeridas"));
const GeracaoRoteiros = lazyWithReload(() => import("@/pages/geracao/Roteiros"));
const MinhasExtracoes = lazyWithReload(() => import("@/pages/cerebro/MinhasExtracoes"));
const Imobiliarias = lazyWithReload(() => import("@/pages/Imobiliarias"));
// Edição de Fotos — W10a (plan §4/§7). Admin pages (Referências, Guias —
// W6; Regras — W7; Curadores — notify slice; Painel — W9; Modelos +
// Processamento — W8) are all shipped.
const EdicaoFotosLotes = lazyWithReload(() => import("@/pages/edicao-fotos/Lotes"));
const EdicaoFotosNovoLote = lazyWithReload(() => import("@/pages/edicao-fotos/NovoLote"));
const EdicaoFotosLoteRevisao = lazyWithReload(() => import("@/pages/edicao-fotos/LoteRevisao"));
const EdicaoFotosConfiguracoes = lazyWithReload(() => import("@/pages/edicao-fotos/Configuracoes"));
const EdicaoFotosReferencias = lazyWithReload(() => import("@/pages/edicao-fotos/Referencias"));
const EdicaoFotosGuiasEstilo = lazyWithReload(() => import("@/pages/edicao-fotos/GuiasEstilo"));
const EdicaoFotosRegras = lazyWithReload(() => import("@/pages/edicao-fotos/Regras"));
const EdicaoFotosCuradores = lazyWithReload(() => import("@/pages/edicao-fotos/Curadores"));
const EdicaoFotosPainel = lazyWithReload(() => import("@/pages/edicao-fotos/Painel"));
const EdicaoFotosModelos = lazyWithReload(() => import("@/pages/edicao-fotos/Modelos"));
const EdicaoFotosProcessamento = lazyWithReload(() => import("@/pages/edicao-fotos/Processamento"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Contatos", href: "/contatos", icon: UserRound, route: "contatos" },
      { name: "Agendamentos", href: "/agendamentos", icon: CalendarClock, route: "agendamentos" },
    ],
  },
  {
    key: "imoveis",
    label: "Imóveis",
    icon: Building2,
    items: [
      { name: "Imóveis", href: "/imoveis", icon: Building2, route: "imoveis" },
      { name: "Permutas", href: "/permutas", icon: ArrowLeftRight, route: "permutas" },
    ],
  },
  {
    key: "leads",
    label: "Leads",
    icon: Target,
    items: [
      { name: "Leads", href: "/leads", icon: Target, route: "leads" },
      { name: "Campanhas", href: "/campanhas", icon: Megaphone, route: "campanhas" },
      { name: "Funil de Vendas", href: "/funil", icon: KanbanSquare, route: "funil" },
      { name: "Processos de Venda", href: "/processos-venda", icon: Workflow, route: "processos_venda" },
      { name: "ROI por Portal", href: "/portal-roi", icon: TrendingUp, route: "portal_roi" },
    ],
  },
  {
    key: "clientes",
    label: "Clientes",
    icon: UserCheck,
    items: [
      { name: "Clientes", href: "/clientes", icon: UserCheck, route: "clientes" },
      { name: "Revisão de Duplicados", href: "/clientes/revisao", icon: GitMerge, route: "clientes_revisao" },
    ],
  },
  {
    key: "edicao-fotos",
    label: "Edição de Fotos",
    icon: ImagePlus,
    items: [
    ],
    groups: [
      {
        key: "edicao-fotos-operacao",
        label: "Operação",
        icon: Activity,
        items: [
          { name: "Lotes", href: "/edicao-fotos", icon: ImagePlus, route: "edicao-fotos" },
          { name: "Novo Lote", href: "/edicao-fotos/novo", icon: Plus, route: "edicao-fotos-novo-lote" },
          { name: "Painel", href: "/edicao-fotos/painel", icon: BarChart3, route: "edicao-fotos-painel" },
          { name: "Processamento", href: "/edicao-fotos/processamento", icon: Activity, route: "edicao-fotos-processamento" },
        ],
      },
      {
        key: "edicao-fotos-config",
        label: "Configuração",
        icon: Settings2,
        items: [
          { name: "Configurações", href: "/edicao-fotos/configuracoes", icon: Settings2, route: "edicao-fotos-configuracoes" },
          { name: "Referências", href: "/edicao-fotos/referencias", icon: Images, route: "edicao-fotos-referencias" },
          { name: "Guias de Estilo", href: "/edicao-fotos/guias", icon: BookOpen, route: "edicao-fotos-guias" },
          { name: "Regras", href: "/edicao-fotos/regras", icon: ScrollText, route: "edicao-fotos-regras" },
          { name: "Curadores", href: "/edicao-fotos/curadores", icon: UserCog, route: "edicao-fotos-curadores" },
          { name: "Modelos", href: "/edicao-fotos/modelos", icon: Cpu, route: "edicao-fotos-modelos" },
        ],
      },
    ],
  },
  {
    key: "media-creation",
    label: "Criação de mídia",
    icon: Wand2,
    items: [
      { name: "Criação de mídia", href: "/media-creation", icon: Wand2, route: "media_creation" },
      { name: "Dashboard", href: "/media-creation/dashboard", icon: LayoutDashboard, route: "media-creation-dashboard" },
      { name: "Criar Headlines e Roteiros", href: "/media-creation/chat", icon: MessagesSquare, route: "media-creation-chat" },
      { name: "Biblioteca", href: "/media-creation/biblioteca", icon: Library, route: "media-creation-biblioteca" },
    ],
    groups: [
      {
        key: "media-creation-pesquisa",
        label: "Pesquisa",
        icon: Search,
        items: [
          { name: "Minha Pesquisa", href: "/media-creation/pesquisa", icon: Lightbulb, route: "media-creation-pesquisa" },
          { name: "Extrair Pesquisa", href: "/media-creation/pesquisa/extrair", icon: Sparkles, route: "media-creation-pesquisa-extrair" },
        ],
      },
      {
        key: "media-creation-cerebro",
        label: "Segundo Cérebro",
        icon: Brain,
        items: [
          { name: "Cérebros", href: "/media-creation/cerebro", icon: Brain, route: "media-creation-cerebro" },
          { name: "Minhas extrações", href: "/media-creation/cerebro/extracoes", icon: Brain, route: "media-creation-cerebro" },
        ],
      },
      {
        key: "media-creation-configuracoes",
        label: "Configurações",
        icon: Settings2,
        items: [
          { name: "Meu Perfil", href: "/media-creation/perfil", icon: UserCog, route: "media-creation-perfil" },
          { name: "Minha Biblioteca", href: "/media-creation/minha-biblioteca", icon: Bookmark, route: "media-creation-minha-biblioteca" },
          { name: "Treinamentos", href: "/media-creation/treinamentos", icon: GraduationCap, route: "media-creation-treinamentos" },
          { name: "Roteiros", href: "/media-creation/roteiros", icon: Clapperboard, route: "media-creation-roteiros" },
        ],
        groups: [
          {
            key: "media-creation-headlines",
            label: "Headlines",
            icon: Heading,
            items: [
              { name: "Gerar Headlines", href: "/media-creation/headlines/gerar", icon: Sparkles, route: "media-creation-headlines-gerar" },
              { name: "Headlines Favoritas", href: "/media-creation/headlines/favoritas", icon: Star, route: "media-creation-headlines-favoritas" },
              { name: "Headlines sugeridas", href: "/media-creation/headlines/sugeridas", icon: Lightbulb, route: "media-creation-headlines-sugeridas" },
            ],
          },
        ],
      },
    ],
  },
  {
    key: "marketing",
    label: "Marketing",
    icon: Share2,
    items: [
    ],
    groups: [
      {
        key: "email-noc",
        label: "Email",
        icon: Mail,
        items: [
          { name: "Painel", href: "/email", icon: BarChart3, route: "email_painel" },
          { name: "Campanhas", href: "/email/campanhas", icon: Send, route: "email_campanhas_noc" },
          { name: "Contatos", href: "/email/contatos", icon: UserRound, route: "email_contatos_noc" },
          { name: "Listas", href: "/email/listas", icon: List, route: "email_listas_noc" },
          { name: "Templates", href: "/email/templates", icon: FileText, route: "email_templates_noc" },
          { name: "Automações", href: "/email/automacoes", icon: Workflow, route: "email_automacoes_noc" },
          { name: "Domínios", href: "/email/dominios", icon: Globe, route: "email_dominios_noc" },
        ],
      },
      {
        key: "email",
        label: "Mailchimp",
        icon: Mail,
        items: [
          { name: "Membros", href: "/email-marketing/membros", icon: Users, route: "email_membros" },
          { name: "Listas", href: "/email-marketing/listas", icon: List, route: "email_listas" },
          { name: "Templates", href: "/email-marketing/templates", icon: FileText, route: "email_templates" },
          { name: "Campanhas", href: "/email-marketing/campanhas", icon: Send, route: "email_campanhas" },
          { name: "Configuração", href: "/email-marketing/configuracao", icon: Settings2, route: "email_config" },
        ],
      },
    ],
  },
  {
    key: "emissoes",
    label: "Emissões",
    icon: Stamp,
    items: [
      { name: "Certidões", href: "/certidoes", icon: ShieldCheck, route: "certidoes" },
      { name: "Extrator de Matrículas", href: "/matriculas", icon: ScrollText, route: "matriculas" },
      { name: "Agentes Financeiros", href: "/agentes-financeiros", icon: Landmark, route: "agentes_financeiros" },
    ],
  },
  {
    key: "conexoes",
    label: "Conexões",
    icon: Smartphone,
    items: [
      { name: "Marcas", href: "/marcas", icon: Building2, route: "marcas" },
      { name: "Monitor", href: "/monitor", icon: Activity, route: "monitor" },
      { name: "YouTube", href: "/youtube", icon: Youtube, route: "youtube" },
      { name: "Meta", href: "/meta", icon: Instagram, route: "meta" },
      { name: "WhatsApp", href: "/whatsapp-chat", icon: Smartphone, route: "whatsapp_chat" },
      { name: "n8n", href: "/n8n", icon: Workflow, route: "n8n" },
    ],
  },
  {
    key: "config",
    label: "Configuração",
    icon: Settings2,
    items: [
      { name: "Configurações", href: "/configuracoes", icon: SettingsIcon, route: "configuracoes" },
      { name: "Imobiliárias", href: "/imobiliarias", icon: Building2, route: "imobiliarias" },
      { name: "Testemunhas", href: "/testemunhas", icon: UserRound, route: "testemunhas" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Custos", href: "/custos", icon: Wallet, route: "custos" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard },
      { name: "Contatos", href: "/contatos", icon: UserRound },
      { name: "Agendamentos", href: "/agendamentos", icon: CalendarClock },
    ],
  },
  {
    key: "imoveis",
    label: "Imóveis",
    icon: Building2,
    items: [
      { name: "Imóveis", href: "/imoveis", icon: Building2 },
      { name: "Permutas", href: "/permutas", icon: ArrowLeftRight },
    ],
  },
  {
    key: "leads",
    label: "Leads",
    icon: Target,
    items: [
      { name: "Leads", href: "/leads", icon: Target },
      { name: "Campanhas", href: "/campanhas", icon: Megaphone },
      { name: "Funil de Vendas", href: "/funil", icon: KanbanSquare },
      { name: "Processos de Venda", href: "/processos-venda", icon: Workflow },
      { name: "ROI por Portal", href: "/portal-roi", icon: TrendingUp },
    ],
  },
  {
    key: "clientes",
    label: "Clientes",
    icon: UserCheck,
    items: [
      { name: "Clientes", href: "/clientes", icon: UserCheck },
      { name: "Revisão de Duplicados", href: "/clientes/revisao", icon: GitMerge },
    ],
  },
  {
    key: "edicao-fotos",
    label: "Edição de Fotos",
    icon: ImagePlus,
    items: [
    ],
    groups: [
      {
        key: "edicao-fotos-operacao",
        label: "Operação",
        icon: Activity,
        items: [
          { name: "Lotes", href: "/edicao-fotos", icon: ImagePlus },
          { name: "Novo Lote", href: "/edicao-fotos/novo", icon: Plus },
          { name: "Painel", href: "/edicao-fotos/painel", icon: BarChart3 },
          { name: "Processamento", href: "/edicao-fotos/processamento", icon: Activity },
        ],
      },
      {
        key: "edicao-fotos-config",
        label: "Configuração",
        icon: Settings2,
        items: [
          { name: "Configurações", href: "/edicao-fotos/configuracoes", icon: Settings2 },
          { name: "Referências", href: "/edicao-fotos/referencias", icon: Images },
          { name: "Guias de Estilo", href: "/edicao-fotos/guias", icon: BookOpen },
          { name: "Regras", href: "/edicao-fotos/regras", icon: ScrollText },
          { name: "Curadores", href: "/edicao-fotos/curadores", icon: UserCog },
          { name: "Modelos", href: "/edicao-fotos/modelos", icon: Cpu },
        ],
      },
    ],
  },
  {
    key: "media-creation",
    label: "Criação de mídia",
    icon: Wand2,
    items: [
      { name: "Criação de mídia", href: "/media-creation", icon: Wand2 },
      { name: "Dashboard", href: "/media-creation/dashboard", icon: LayoutDashboard },
      { name: "Criar Headlines e Roteiros", href: "/media-creation/chat", icon: MessagesSquare },
      { name: "Biblioteca", href: "/media-creation/biblioteca", icon: Library },
    ],
    groups: [
      {
        key: "media-creation-pesquisa",
        label: "Pesquisa",
        icon: Search,
        items: [
          { name: "Minha Pesquisa", href: "/media-creation/pesquisa", icon: Lightbulb },
          { name: "Extrair Pesquisa", href: "/media-creation/pesquisa/extrair", icon: Sparkles },
        ],
      },
      {
        key: "media-creation-cerebro",
        label: "Segundo Cérebro",
        icon: Brain,
        items: [
          { name: "Cérebros", href: "/media-creation/cerebro", icon: Brain },
          { name: "Minhas extrações", href: "/media-creation/cerebro/extracoes", icon: Brain },
        ],
      },
      {
        key: "media-creation-configuracoes",
        label: "Configurações",
        icon: Settings2,
        items: [
          { name: "Meu Perfil", href: "/media-creation/perfil", icon: UserCog },
          { name: "Minha Biblioteca", href: "/media-creation/minha-biblioteca", icon: Bookmark },
          { name: "Treinamentos", href: "/media-creation/treinamentos", icon: GraduationCap },
          { name: "Roteiros", href: "/media-creation/roteiros", icon: Clapperboard },
        ],
        groups: [
          {
            key: "media-creation-headlines",
            label: "Headlines",
            icon: Heading,
            items: [
              { name: "Gerar Headlines", href: "/media-creation/headlines/gerar", icon: Sparkles },
              { name: "Headlines Favoritas", href: "/media-creation/headlines/favoritas", icon: Star },
              { name: "Headlines sugeridas", href: "/media-creation/headlines/sugeridas", icon: Lightbulb },
            ],
          },
        ],
      },
    ],
  },
  {
    key: "marketing",
    label: "Marketing",
    icon: Share2,
    items: [
    ],
    groups: [
      {
        key: "email-noc",
        label: "Email",
        icon: Mail,
        items: [
          { name: "Painel", href: "/email", icon: BarChart3 },
          { name: "Campanhas", href: "/email/campanhas", icon: Send },
          { name: "Contatos", href: "/email/contatos", icon: UserRound },
          { name: "Listas", href: "/email/listas", icon: List },
          { name: "Templates", href: "/email/templates", icon: FileText },
          { name: "Automações", href: "/email/automacoes", icon: Workflow },
          { name: "Domínios", href: "/email/dominios", icon: Globe },
        ],
      },
      {
        key: "email",
        label: "Mailchimp",
        icon: Mail,
        items: [
          { name: "Membros", href: "/email-marketing/membros", icon: Users },
          { name: "Listas", href: "/email-marketing/listas", icon: List },
          { name: "Templates", href: "/email-marketing/templates", icon: FileText },
          { name: "Campanhas", href: "/email-marketing/campanhas", icon: Send },
          { name: "Configuração", href: "/email-marketing/configuracao", icon: Settings2 },
        ],
      },
    ],
  },
  {
    key: "emissoes",
    label: "Emissões",
    icon: Stamp,
    items: [
      { name: "Certidões", href: "/certidoes", icon: ShieldCheck },
      { name: "Extrator de Matrículas", href: "/matriculas", icon: ScrollText },
      { name: "Agentes Financeiros", href: "/agentes-financeiros", icon: Landmark },
    ],
  },
  {
    key: "conexoes",
    label: "Conexões",
    icon: Smartphone,
    items: [
      { name: "Marcas", href: "/marcas", icon: Building2 },
      { name: "Monitor", href: "/monitor", icon: Activity },
      { name: "YouTube", href: "/youtube", icon: Youtube },
      { name: "Meta", href: "/meta", icon: Instagram },
      { name: "WhatsApp", href: "/whatsapp-chat", icon: Smartphone },
      { name: "n8n", href: "/n8n", icon: Workflow },
    ],
  },
  {
    key: "config",
    label: "Configuração",
    icon: Settings2,
    items: [
      { name: "Configurações", href: "/configuracoes", icon: SettingsIcon },
      { name: "Imobiliárias", href: "/imobiliarias", icon: Building2 },
      { name: "Testemunhas", href: "/testemunhas", icon: UserRound },
      { name: "Equipe", href: "/equipe", icon: Users },
      { name: "Custos", href: "/custos", icon: Wallet },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: Share2,
  brandTitle: "Social Wiring",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
  useLayoutEnrichment: useSocialWiringLayoutEnrichment,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/media-creation", component: MediaCreation },
    { path: "/media-creation/pesquisa", component: Pesquisa },
    { path: "/media-creation/pesquisa/extrair", component: ExtrairPesquisa },
    { path: "/media-creation/cerebro", component: CerebroLista },
    { path: "/media-creation/cerebro/extracoes", component: MinhasExtracoes },
    { path: "/media-creation/cerebro/:brainId", component: CerebroEditor },
    { path: "/media-creation/cerebro/:brainId/perguntas", component: CerebroPerguntas },
    { path: "/media-creation/dashboard", component: GeracaoDashboard },
    { path: "/media-creation/chat", component: GeracaoChat },
    { path: "/media-creation/biblioteca", component: GeracaoBiblioteca },
    { path: "/media-creation/perfil", component: GeracaoMeuPerfil },
    { path: "/media-creation/minha-biblioteca", component: GeracaoMinhaBiblioteca },
    { path: "/media-creation/treinamentos", component: GeracaoTreinamentos },
    { path: "/media-creation/headlines/gerar", component: GeracaoHeadlinesGerar },
    { path: "/media-creation/headlines", component: GeracaoHeadlines },
    { path: "/media-creation/headlines/favoritas", component: GeracaoHeadlinesFavoritas },
    { path: "/media-creation/headlines/sugeridas", component: GeracaoHeadlinesSugeridas },
    { path: "/media-creation/roteiros", component: GeracaoRoteiros },
    // Legacy /email-marketing repointed at EmailCampanhas (vestigial EmailMarketing.tsx stays but is unrouted)
    { path: "/email-marketing", component: EmailCampanhas },
    { path: "/contatos", component: Contatos },
    { path: "/leads", component: Leads },
    { path: "/campanhas", component: Campanhas },
    { path: "/funil", component: FunilVendas },
    { path: "/processos-venda", component: ProcessosVenda },
    { path: "/portal-roi", component: PortalRoi },
    { path: "/certidoes", component: Certidoes },
    { path: "/matriculas", component: Matriculas },
    { path: "/agentes-financeiros", component: AgentesFinanceiros },
    { path: "/testemunhas", component: Testemunhas },
    { path: "/imobiliarias", component: Imobiliarias },
    { path: "/edicao-fotos", component: EdicaoFotosLotes },
    { path: "/edicao-fotos/novo", component: EdicaoFotosNovoLote },
    { path: "/edicao-fotos/lotes/:loteId/revisao", component: EdicaoFotosLoteRevisao },
    { path: "/edicao-fotos/configuracoes", component: EdicaoFotosConfiguracoes },
    { path: "/edicao-fotos/referencias", component: EdicaoFotosReferencias },
    { path: "/edicao-fotos/guias", component: EdicaoFotosGuiasEstilo },
    { path: "/edicao-fotos/regras", component: EdicaoFotosRegras },
    { path: "/edicao-fotos/curadores", component: EdicaoFotosCuradores },
    { path: "/edicao-fotos/painel", component: EdicaoFotosPainel },
    { path: "/edicao-fotos/modelos", component: EdicaoFotosModelos },
    { path: "/edicao-fotos/processamento", component: EdicaoFotosProcessamento },
    { path: "/clientes", component: ClientesBoard },
    // `/clientes/revisao` MUST stay declared before `/clientes/:id`.
    { path: "/clientes/revisao", component: RevisaoFila },
    // ONE person page, two section orders (atendimento-partes-imoveis D3).
    // Detail routes reached from lists — no nav entry (same shape as
    // `/imoveis/:codigo` next to the `imoveis` entry).
    { path: "/clientes/:id", component: PessoaPage },
    { path: "/vendedores/:id", component: PessoaPage },
    { path: "/email-marketing/listas", component: EmailListas },
    { path: "/email-marketing/templates", component: EmailTemplates },
    { path: "/email-marketing/campanhas", component: EmailCampanhas },
    { path: "/email-marketing/configuracao", component: EmailMarketingConfig },
    { path: "/email-marketing/membros", component: EmailMembros },
    { path: "/youtube", component: YouTube },
    { path: "/n8n", component: N8n },
    { path: "/meta", component: MetaDashboard },
    // Retired route — remodeled into the unified Meta dashboard (Wave 3)
    { path: "/instagram-insights", component: RedirectToMeta },
    // Retired routes — connection management now lives inside MarcaModal
    { path: "/conexoes", component: RedirectToMarcas },
    { path: "/integrations", component: RedirectToMarcas },
    { path: "/conexao", component: RedirectToMarcas },
    { path: "/marcas", component: Marcas },
    { path: "/imoveis", component: Imoveis },
    { path: "/imoveis/:codigo", component: ImovelDetalhes },
    { path: "/permutas", component: Permutas },
    { path: "/agendamentos", component: Agendamentos },
    { path: "/email", component: EmailPainel },
    { path: "/email/campanhas", component: EmailCampanhasNoc },
    { path: "/email/contatos", component: EmailContatosNoc },
    { path: "/email/listas", component: EmailListasNoc },
    { path: "/email/templates", component: EmailTemplatesNoc },
    { path: "/email/automacoes", component: EmailAutomacoes },
    { path: "/email/dominios", component: EmailDominios },
    { path: "/monitor", component: Monitor },
    // WhatsApp — full dashboard (Chat + Configurações), back in nav (see header comment)
    { path: "/whatsapp-chat", component: WhatsAppChat },
    { path: "/equipe", component: Equipe },
    { path: "/configuracoes", component: Settings },
    { path: "/custos", component: Custos },
  ],
  // /chat is public — the backend chat router is unauthenticated by
  // current product direction, so the frontend route matches that
  // posture. The same panel renders as YouTube → Upload → Chat.
  publicRoutes: [
    { path: "/chat", component: Chat },
    // Public e-mail unsubscribe link target (token-authenticated, no login).
    { path: "/descadastro/:token", component: EmailDescadastro },
    // Public double opt-in confirmation link target (token-authenticated, no login).
    { path: "/confirmar-email/:token", component: EmailConfirmarEmail },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
