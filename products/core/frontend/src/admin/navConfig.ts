/**
 * Core's admin navigation DATA, in the canonical module-group order shared with
 * Social Wiring (CRM, Redes Sociais, ERP, CMS, CoreStudio, Banib, Emissões,
 * Integrações, Configurações), then core's own groups, then standalone items.
 * The rendering is the seed `Sidebar` organ; core only supplies this config.
 *
 * Code-split with the admin chunk: never import this from the main bundle.
 */
import {
  Activity, BarChart3, Brain, Building2, Coins, CreditCard, FileText, Filter, Gauge, Globe,
  KeyRound, Landmark, LayoutDashboard, MessageSquare, Package, PackageOpen, Palette, Plug,
  Search, Settings, ShieldCheck, Users, Wallet, Webhook, ClipboardList, Zap, GitBranch,
  Share2, Briefcase, Sparkles, FileCheck,
} from 'lucide-react';
import { orderNavGroups } from '@noctusai/lib/design-system';
import type { NavGroup, NavItem } from '@noctusai/lib/design-system';
import { NAV_DOCS, NAV_LEADS, NAV_SITE } from './websiteConfig';

const PLATFORM_GROUPS: NavGroup[] = [
  {
    key: 'crm',
    label: 'CRM',
    icon: Users,
    items: [
      { name: 'Funil', href: '/admin/funil', icon: Filter },
      NAV_LEADS,
      { name: 'Organizações', href: '/admin/orgs', icon: Building2 },
      { name: 'Usuários', href: '/admin/users', icon: Users },
    ],
  },
  {
    key: 'erp',
    label: 'ERP',
    icon: Briefcase,
    items: [{ name: 'Financeiro', href: '/admin/financeiro', icon: Landmark }],
    groups: [
      {
        key: 'erp-vendas',
        label: 'Vendas',
        icon: Wallet,
        items: [
          { name: 'Produtos', href: '/admin/products', icon: Package },
          { name: 'Planos', href: '/admin/plans', icon: ClipboardList },
          { name: 'Assinaturas', href: '/admin/subs', icon: CreditCard },
          { name: 'Faturamento', href: '/admin/billing', icon: Wallet },
        ],
      },
      {
        key: 'erp-consumo-ia',
        label: 'Consumo de IA',
        icon: Coins,
        items: [
          { name: 'Créditos de IA', href: '/admin/creditos', icon: Coins },
          { name: 'Uso e custos', href: '/admin/uso', icon: Gauge },
        ],
      },
    ],
  },
  {
    key: 'cms',
    label: 'CMS',
    icon: Globe,
    items: [
      NAV_SITE,
      NAV_DOCS,
    ],
  },
  {
    key: 'integracoes',
    label: 'Integrações',
    icon: Plug,
    items: [
      { name: 'Webhooks', href: '/admin/webhooks', icon: Webhook },
      { name: 'Chaves de API (plataforma)', href: '/admin/api-keys', icon: KeyRound },
      { name: 'Tokens de API', href: '/admin/tokens', icon: KeyRound },
      // `↗`: leaves the admin layout (a regular core page).
      { name: 'Chaves de LLM', href: '/api-keys', icon: Brain, badge: '↗' },
    ],
  },
  {
    key: 'configuracoes',
    label: 'Configurações',
    icon: Settings,
    items: [
      { name: 'Gerais', href: '/admin/settings', icon: Settings },
      { name: 'Segurança', href: '/security', icon: ShieldCheck, badge: '↗' },
    ],
  },
  {
    key: 'operacao',
    label: 'Operação',
    icon: Activity,
    items: [
      { name: 'Rotinas e saúde', href: '/admin/operacao', icon: Activity },
      { name: 'Fleet Control', href: '/admin/fleet', icon: Zap },
      { name: 'Analytics', href: '/admin/analytics', icon: BarChart3 },
      { name: 'Digest de auditoria', href: '/admin/audit-digest', icon: FileText },
    ],
  },
  {
    key: 'modelos',
    label: 'Modelos da plataforma',
    icon: PackageOpen,
    items: [
      { name: 'Design system', href: '/admin/templates/design_system', icon: Palette },
      { name: 'Agentes e prompts', href: '/admin/templates/agent', icon: Brain },
      { name: 'Mensagens', href: '/admin/templates/message', icon: MessageSquare },
      { name: 'Documentos', href: '/admin/templates/document', icon: FileText },
      { name: 'Repositório e workflow', href: '/admin/templates/repo_workflow', icon: GitBranch },
      { name: 'Fontes', href: '/admin/templates/fontes', icon: Search },
      { name: 'Scaffolds de projeto', href: '/admin/templates/scaffolds', icon: Package },
    ],
  },
];

/** Standalone items, rendered after the groups behind a divider. */
export const ADMIN_STANDALONE_ITEMS: NavItem[] = [
  { name: 'Painel', href: '/admin', icon: LayoutDashboard },
];

/**
 * Canonical modules core does not have yet: disabled "Em breve" stubs, visible to noc-admins only
 * (they sit in the platform bundle; `href: '#'` is unreachable for any other role, so `pruneNavGroups`
 * drops them for marketing).
 */
const stub = (key: string, label: string, icon: NavGroup['icon']): NavGroup => ({
  key,
  label,
  icon,
  disabled: true,
  badge: 'Em breve',
  items: [{ name: label, href: '#', icon, disabled: true }],
});

const STUB_GROUPS: NavGroup[] = [
  stub('redes-sociais', 'Redes Sociais', Share2),
  stub('corestudio', 'CoreStudio', Sparkles),
  stub('banib', 'Banib', Landmark),
  stub('emissoes', 'Emissões', FileCheck),
];

/** Canonical module order (seed `MODULE_GROUP_ORDER`) first; core's own groups (`operacao`, `modelos`) after. */
export const ADMIN_NAV_GROUPS: NavGroup[] = orderNavGroups([...PLATFORM_GROUPS, ...STUB_GROUPS]);
