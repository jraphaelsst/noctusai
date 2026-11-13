/**
 * Social Wiring sidebar nav — built on the seed module manifests (W3-S1,
 * crm-cms-erp-vertical-seeds plan; page-to-group table = "SW Sidebar Mockup"
 * 2026-11-08, approved).
 *
 * Canonical group order is the seed's `MODULE_GROUP_ORDER`
 * (CRM · Redes Sociais · ERP · CoreStudio · Banib · Emissões ·
 * Integrações · Configurações), applied by `composeModules`. Dashboard is a
 * standalone item after the groups. Existing URLs never move; a page lives in
 * exactly one group. Every `route` key is the page's existing status_pagina key,
 * so dev-only pages stay dev/owner-only (`filterNavByPageStatus`).
 *
 * `NAV_GROUPS` carries a status_pagina `route` key per item (gated nav);
 * `NAV_FALLBACK` (ungated) is DERIVED from it via `stripNavRoutes`.
 *
 * NOC-REMEDIATE[sw-nav-extend-seed-modules]: SW defines its module groups locally
 * with `defineModule` (declared deviation) because the seed ships no base
 * crm/erp/cms modules yet. Destination: plan slice W2-6 (seed `crmModule`, later
 * erp/cms) -- then SW switches to `extendModule(base, ...)`. Keys match
 * MODULE_GROUP_ORDER. — 2026-11-11
 *
 * NOC-REMEDIATE[sw-modules-enablement-endpoint]: SW has no `GET /api/modules`, so
 * `useEnabledModules` cannot feed per-org enablement (it would read null -> no
 * module renders). All modules are ON by default (owner, 2026-11-08), so every
 * module is enabled statically below. Destination: W1-1 follow-up (mount the
 * seed modules router in SW, then pass `useEnabledModules().enabledKeys`). — 2026-11-11
 *
 * Banib (stub, "Em breve") is omitted: a disabled entry needs a status_pagina
 * row (unlisted pages are hidden) = a backend migration, out of this slice.
 * "Edição de Imagem" (ex-"Edição de Fotos", ex-module `cms`, moved 2026-11-13)
 * is a CoreStudio sub-group (Operação / Configuração) placed before Pesquisa; the
 * `cms` module is gone (composeModules/MODULE_GROUP_ORDER tolerate an absent key).
 * Hrefs and status_pagina `route` keys are unchanged.
 * CoreStudio keeps its literal tree (two items share one page key, which
 * `defineModule` forbids); it is a local group keyed `corestudio`.
 */
import { composeModules, defineModule, stripNavRoutes } from "@noctusai/lib";
import type { ModuleItem } from "@noctusai/lib";
import type { NavGroupWithRoute, NavItemWithRoute } from "@noctusai/lib";
import type { NavGroup, NavItem } from "@noctusai/lib/design-system";
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
import { Youtube, Instagram } from "@noctusai/lib/brand-icons";
import { JULIA_ICON, JULIA_LABEL, JULIA_NAV_KEY, JULIA_PAGES } from "@/nav/julia";

type Icon = ModuleItem["icon"];

/** A sub-group header inside a module. Never rendered as a page: its path/pageKey only keep `defineModule`'s uniqueness checks satisfied. */
const grp = (slug: string, label: string, icon: Icon, children: ModuleItem[]): ModuleItem => ({
  label,
  icon,
  path: `/__grupo/${slug}`,
  pageKey: `__grupo:${slug}`,
  children,
});

/** A page: nav-only (routes stay declared in App.tsx, URLs never move). */
const pg = (label: string, path: string, pageKey: string, icon: Icon): ModuleItem => ({ label, path, pageKey, icon });

const juliaItems: ModuleItem[] = Object.values(JULIA_PAGES).map((p) => pg(p.name, p.href, p.route, p.icon));

const crm = defineModule({
  key: "crm",
  icon: Users,
  items: [
    grp("pessoas", "Pessoas", UserRound, [
      pg("Contatos", "/contatos", "contatos", UserRound),
      pg("Clientes", "/clientes", "clientes", UserCheck),
      pg("Revisão de Duplicados", "/clientes/revisao", "clientes_revisao", GitMerge),
    ]),
    grp("vendas", "Vendas", Target, [
      pg("Leads", "/leads", "leads", Target),
      pg("Funil de Vendas", "/funil", "funil", KanbanSquare),
      pg("Processos de Venda", "/processos-venda", "processos_venda", Workflow),
      pg("Agendamentos", "/agendamentos", "agendamentos", CalendarClock),
    ]),
    grp("campanhas", "Campanhas", Megaphone, [
      pg("Campanhas", "/campanhas", "campanhas", Megaphone),
      pg("ROI por Portal", "/portal-roi", "portal_roi", TrendingUp),
    ]),
    grp(JULIA_NAV_KEY, JULIA_LABEL, JULIA_ICON, juliaItems),
    grp("atendimento", "Atendimento", Activity, [
      pg("Monitor", "/monitor", "monitor", Activity),
      pg("Blocos do Atendimento", "/atendimento-blocos", "atendimento_blocos", Layers),
      pg("Supervisão", "/supervisao", "supervisao", Eye),
    ]),
    grp("email", "E-mail", Mail, [
      pg("Painel", "/email", "email_painel", BarChart3),
      pg("Campanhas", "/email/campanhas", "email_campanhas_noc", Send),
      pg("Contatos", "/email/contatos", "email_contatos_noc", UserRound),
      pg("Listas", "/email/listas", "email_listas_noc", List),
      pg("Templates", "/email/templates", "email_templates_noc", FileText),
      pg("Automações", "/email/automacoes", "email_automacoes_noc", Workflow),
      pg("Domínios", "/email/dominios", "email_dominios_noc", Globe),
      grp("mailchimp", "Mailchimp", Mail, [
        pg("Membros", "/email-marketing/membros", "email_membros", Users),
        pg("Listas", "/email-marketing/listas", "email_listas", List),
        pg("Templates", "/email-marketing/templates", "email_templates", FileText),
        pg("Campanhas", "/email-marketing/campanhas", "email_campanhas", Send),
        pg("Configuração", "/email-marketing/configuracao", "email_config", Settings2),
      ]),
    ]),
  ],
});

const redesSociais = defineModule({
  key: "redes-sociais",
  icon: Share2,
  items: [
    pg("Meta", "/meta", "meta", Instagram),
    pg("YouTube", "/youtube", "youtube", Youtube),
    // SIMEC (marketing intelligence, Instagram) — status_pagina `simec`, migration 284.
    pg("SIMEC", "/simec", "simec", BarChart3),
  ],
});

const erp = defineModule({
  key: "erp",
  icon: Building2,
  items: [
    grp("imoveis", "Imóveis", Building2, [
      pg("Imóveis", "/imoveis", "imoveis", Building2),
      pg("Condomínios", "/condominios", "condominios", Building),
      pg("Permutas", "/permutas", "permutas", ArrowLeftRight),
    ]),
    grp("financeiro", "Financeiro", Landmark, [pg("Financeiro", "/financeiro", "financeiro", Landmark)]),
  ],
});

const emissoes = defineModule({
  key: "emissoes",
  icon: Stamp,
  items: [
    pg("Certidões", "/certidoes", "certidoes", ShieldCheck),
    pg("Extrator de Matrículas", "/matriculas", "matriculas", ScrollText),
    pg("Agentes Financeiros", "/agentes-financeiros", "agentes_financeiros", Landmark),
  ],
});

const integracoes = defineModule({
  key: "integracoes",
  icon: Smartphone,
  items: [
    pg("Marcas", "/marcas", "marcas", Building2),
    pg("n8n", "/n8n", "n8n", Workflow),
  ],
});

const configuracoes = defineModule({
  key: "configuracoes",
  icon: Settings2,
  items: [
    pg("Configurações", "/configuracoes", "configuracoes", SettingsIcon),
    pg("Equipe", "/equipe", "equipe", Users),
    pg("Imobiliárias", "/imobiliarias", "imobiliarias", Building2),
    pg("Testemunhas", "/testemunhas", "testemunhas", UserRound),
    pg("Favorecidos", "/favorecidos", "favorecidos", Landmark),
    pg("Custos", "/custos", "custos", Wallet),
  ],
});

/** CoreStudio: unchanged tree (see docblock), local group keyed `corestudio`. */
const CORESTUDIO_GROUP: NavGroupWithRoute =
{
    key: "corestudio",
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
        key: "edicao-fotos",
        label: "Edição de Imagem",
        icon: ImagePlus,
        items: [],
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
  };

export const SW_MODULES = [crm, redesSociais, erp, emissoes, integracoes, configuracoes] as const;

const composed = composeModules({
  modules: SW_MODULES,
  localGroups: [CORESTUDIO_GROUP],
  // NOC-REMEDIATE[sw-modules-enablement-endpoint]: static all-on (see docblock).
  enabledKeys: new Set(SW_MODULES.map((m) => m.enablementKey)),
});

export const NAV_GROUPS: NavGroupWithRoute[] = composed.navGroups;

/** Dashboard stays a standalone item after the groups (label unchanged; the "Painel" rename is open decision D3). */
export const STANDALONE_ITEMS: NavItemWithRoute[] = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
];

export const NAV_FALLBACK: NavGroup[] = stripNavRoutes(NAV_GROUPS) as NavGroup[];
export const STANDALONE_FALLBACK: NavItem[] = STANDALONE_ITEMS.map(({ route: _r, ...rest }) => rest as NavItem);
