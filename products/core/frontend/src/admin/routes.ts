/**
 * The platform admin route table. Code-split: `AdminApp` is the ONLY importer and it is itself
 * loaded lazily, only after the server confirmed a platform admin / marketing role — so no admin
 * path, label or page component ships in the main bundle of any other user.
 */
import { lazy } from 'react';
import type { AdminRoute } from './types';
import { WEBSITE_ROUTES } from './websiteConfig';

const AdminTokens = lazy(() => import('../pages/admin/AdminTokens').then(m => ({ default: m.AdminTokens })));
const AdminCreditos = lazy(() => import('../pages/admin/AdminCreditos').then(m => ({ default: m.AdminCreditos })));
const AdminDashboard = lazy(() => import('../pages/admin/AdminDashboard').then(m => ({ default: m.AdminDashboard })));
const AdminOrganizations = lazy(() => import('../pages/admin/AdminOrganizations').then(m => ({ default: m.AdminOrganizations })));
const AdminSubscriptions = lazy(() => import('../pages/admin/AdminSubscriptions').then(m => ({ default: m.AdminSubscriptions })));
const AdminApiKeys = lazy(() => import('../pages/admin/AdminApiKeys').then(m => ({ default: m.AdminApiKeys })));
const AdminPlans = lazy(() => import('../pages/admin/AdminPlans').then(m => ({ default: m.AdminPlans })));
const AdminProducts = lazy(() => import('../pages/admin/AdminProducts').then(m => ({ default: m.AdminProducts })));
const AdminBilling = lazy(() => import('../pages/admin/AdminBilling').then(m => ({ default: m.AdminBilling })));
const AdminWebhooks = lazy(() => import('../pages/admin/AdminWebhooks').then(m => ({ default: m.AdminWebhooks })));
const AdminAnalytics = lazy(() => import('../pages/admin/AdminAnalytics').then(m => ({ default: m.AdminAnalytics })));
const AdminSettings = lazy(() => import('../pages/admin/AdminSettings').then(m => ({ default: m.AdminSettings })));
const AdminUsers = lazy(() => import('../pages/admin/AdminUsers').then(m => ({ default: m.AdminUsers })));
const AdminLogoutBehavior = lazy(() => import('../pages/admin/AdminLogoutBehavior').then(m => ({ default: m.AdminLogoutBehavior })));
const TemplatesAdmin = lazy(() => import('../pages/admin/TemplatesAdmin').then(m => ({ default: m.TemplatesAdmin })));
const AdminAuditDigest = lazy(() => import('../pages/admin/AdminAuditDigest').then(m => ({ default: m.AdminAuditDigest })));
const AdminFinanceiro = lazy(() => import('../pages/admin/AdminFinanceiro').then(m => ({ default: m.AdminFinanceiro })));
const AdminUsoCustos = lazy(() => import('../pages/admin/AdminUsoCustos').then(m => ({ default: m.AdminUsoCustos })));
const AdminOperacao = lazy(() => import('../pages/admin/AdminOperacao').then(m => ({ default: m.AdminOperacao })));
const AdminFunil = lazy(() => import('../pages/admin/AdminFunil').then(m => ({ default: m.AdminFunil })));
const FleetControl = lazy(() => import('../pages/FleetControl').then(m => ({ default: m.FleetControl })));

export const ADMIN_ROUTES: AdminRoute[] = [
    ...WEBSITE_ROUTES,
    { path: '/admin', component: AdminDashboard },
    { path: '/admin/users', component: AdminUsers },
    { path: '/admin/orgs', component: AdminOrganizations },
    { path: '/admin/subs', component: AdminSubscriptions },
    { path: '/admin/api-keys', component: AdminApiKeys },
    { path: '/admin/plans', component: AdminPlans },
    { path: '/admin/funil', component: AdminFunil },
    { path: '/admin/products', component: AdminProducts },
    { path: '/admin/billing/*', component: AdminBilling },
    { path: '/admin/webhooks', component: AdminWebhooks },
    { path: '/admin/analytics', component: AdminAnalytics },
    { path: '/admin/settings', component: AdminSettings },
    { path: '/admin/logout-behavior', component: AdminLogoutBehavior },
    { path: '/admin/templates/*', component: TemplatesAdmin },
    { path: '/admin/audit-digest', component: AdminAuditDigest },
    { path: '/admin/fleet', component: FleetControl },
    { path: '/admin/operacao/*', component: AdminOperacao },
    { path: '/admin/financeiro/*', component: AdminFinanceiro },
    { path: '/admin/creditos', component: AdminCreditos },
    { path: '/admin/uso', component: AdminUsoCustos },
    { path: '/admin/tokens', component: AdminTokens },
];
