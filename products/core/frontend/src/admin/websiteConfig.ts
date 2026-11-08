/**
 * The website-admin surface (the `marketing` role's whole world, and a subset of the platform admin's).
 * A SECOND code-split bundle on purpose: a marketing user is delivered this and never the platform
 * admin bundle, so no platform-admin route, label or page ships to them.
 */
import { lazy } from 'react';
import { BookOpen, Settings, UserPlus, Users, Globe } from 'lucide-react';
import type { NavGroup, NavItem } from '@noctusai/lib/design-system';
import type { AdminRoute } from './types';

const Docs = lazy(() => import('../pages/admin/website/Docs').then(m => ({ default: m.Docs })));
const WebsiteSettings = lazy(() => import('../pages/admin/website/Settings').then(m => ({ default: m.Settings })));
const WebsiteLeads = lazy(() => import('../pages/admin/website/Leads').then(m => ({ default: m.Leads })));
const WebsiteLeadDetail = lazy(() => import('../pages/admin/website/LeadDetail').then(m => ({ default: m.LeadDetail })));

export const WEBSITE_ROUTES: AdminRoute[] = [
  { path: '/admin/website/docs/*', component: Docs },
  { path: '/admin/website/settings/*', component: WebsiteSettings },
  { path: '/admin/website/leads', component: WebsiteLeads },
  { path: '/admin/website/leads/:id', component: WebsiteLeadDetail },
];

export const NAV_LEADS: NavItem = { name: 'Leads do site', href: '/admin/website/leads', icon: UserPlus };
export const NAV_SITE: NavItem = { name: 'Site', href: '/admin/website/settings', icon: Settings };
export const NAV_DOCS: NavItem = { name: 'Documentação', href: '/admin/website/docs', icon: BookOpen };

/** Canonical module keys (`MODULE_GROUP_ORDER`): the website entries sit in CRM and CMS. */
export const WEBSITE_CRM_GROUP: NavGroup = { key: 'crm', label: 'CRM', icon: Users, items: [NAV_LEADS] };
export const WEBSITE_CMS_GROUP: NavGroup = { key: 'cms', label: 'CMS', icon: Globe, items: [NAV_SITE, NAV_DOCS] };
export const WEBSITE_NAV_GROUPS: NavGroup[] = [WEBSITE_CRM_GROUP, WEBSITE_CMS_GROUP];
