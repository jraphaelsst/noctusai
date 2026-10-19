/**
 * Social Wiring sidebar nav — the single source for both nav shapes.
 *
 * `NAV_GROUPS` carries a status_pagina `route` key per item (gated nav);
 * `NAV_FALLBACK` (ungated — shown while page status loads / on failure) is
 * DERIVED from it via the canonical `stripNavRoutes`, so the two can never
 * drift (they used to be two hand-maintained copies in App.tsx).
 *
 * Groups (regrouped 2026-10-05 per core-studio/MENUS.md; Lais added 2026-10-13):
 *   Principal · Lais · Imóveis · Leads · Clientes
 *   Edição de Fotos (Operação / Configuração) · CoreStudio
 *   Marketing (Email / Mailchimp) · Emissões
 *   Conexões (Marcas, Monitor, YouTube, Meta, n8n) · Configuração
 *
 * WhatsApp is NOT in Conexões any more — it lives in the Lais group
 * (`nav/lais.ts`, owner decision 2026-10-13). pt-BR copy preserved.
 */
import { stripNavRoutes } from "@noctusai/lib";
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
  Building,
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
  Palette,
  GalleryHorizontal,
  Layers,
  Eye,
} from "lucide-react";

import { LAIS_NAV_GROUP } from "@/nav/lais";

export const NAV_GROUPS: NavGroupWithRoute[] = [
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
  // Lais (chatbot module) — directly after Principal; see nav/lais.ts.
  LAIS_NAV_GROUP,
  {
    key: "imoveis",
    label: "Imóveis",
    icon: Building2,
    items: [
      { name: "Imóveis", href: "/imoveis", icon: Building2, route: "imoveis" },
      { name: "Permutas", href: "/permutas", icon: ArrowLeftRight, route: "permutas" },
      { name: "Condomínios", href: "/condominios", icon: Building, route: "condominios" },
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
      { name: "Blocos do Atendimento", href: "/atendimento-blocos", icon: Layers, route: "atendimento_blocos" },
      { name: "Supervisão", href: "/supervisao", icon: Eye, route: "supervisao" },
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
    label: "CoreStudio",
    icon: Wand2,
    items: [
      { name: "Dashboard", href: "/media-creation/dashboard", icon: LayoutDashboard, route: "media-creation-dashboard" },
      { name: "Criar Headlines e Roteiros", href: "/media-creation/chat", icon: MessagesSquare, route: "media-creation-chat" },
      { name: "Esteira", href: "/media-creation/esteira", icon: KanbanSquare, route: "media-creation-esteira" },
      { name: "Carrosséis", href: "/media-creation/carrosseis", icon: GalleryHorizontal, route: "media-creation-carrosseis" },
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
          { name: "Branding", href: "/media-creation/branding", icon: Palette, route: "media-creation-branding" },
          { name: "Minha Biblioteca", href: "/media-creation/minha-biblioteca", icon: Bookmark, route: "media-creation-minha-biblioteca" },
          { name: "Treinamentos", href: "/media-creation/treinamentos", icon: GraduationCap, route: "media-creation-treinamentos" },
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
              { name: "Roteiros", href: "/media-creation/roteiros", icon: Clapperboard, route: "media-creation-roteiros" },
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
      // SIMEC (marketing intelligence, Instagram) — status_pagina `simec`, migration 284.
      { name: "SIMEC", href: "/simec", icon: BarChart3, route: "simec" },
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
      { name: "Favorecidos", href: "/favorecidos", icon: Landmark, route: "favorecidos" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Custos", href: "/custos", icon: Wallet, route: "custos" },
      { name: "Financeiro", href: "/financeiro", icon: Landmark, route: "financeiro" },
    ],
  },
];

export const NAV_FALLBACK: NavGroup[] = stripNavRoutes(NAV_GROUPS) as NavGroup[];
