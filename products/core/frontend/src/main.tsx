/**
 * NoctusAI Core — Frontend entry point.
 *
 * Migrated to the seed framework via `createProductApp({ authProvider })` —
 * Phase 4 of `core-seed-wiring`. Core supplies its own auth provider (custom
 * JWT + refresh-token) because core IS the identity provider that Supabase
 * delegates to for every consumer product. The framework owns routing,
 * providers, error boundary, suspense; core owns auth + layout branching.
 */
import React, { lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { createProductApp } from '@noctusai/seed';
import { coreAuthProvider } from './lib/seed-auth-adapter';
import { CoreLayout } from './components/layout/CoreLayout';
import './index.css';

// Pages — lazy-wrapped so the framework's Suspense fallback renders.
const Login = lazy(() => import('./pages/Login').then(m => ({ default: m.Login })));
const Landing = lazy(() => import('./pages/Landing'));
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Pricing = lazy(() => import('./pages/Pricing').then(m => ({ default: m.Pricing })));
const BillingSettings = lazy(() => import('./pages/BillingSettings').then(m => ({ default: m.BillingSettings })));
const CheckoutSuccess = lazy(() => import('./pages/CheckoutSuccess').then(m => ({ default: m.CheckoutSuccess })));
const CheckoutCancel = lazy(() => import('./pages/CheckoutCancel').then(m => ({ default: m.CheckoutCancel })));
const TeamManagement = lazy(() => import('./pages/TeamManagement').then(m => ({ default: m.TeamManagement })));
const AccountSettings = lazy(() => import('./pages/AccountSettings').then(m => ({ default: m.AccountSettings })));
const OrgSettings = lazy(() => import('./pages/OrgSettings').then(m => ({ default: m.OrgSettings })));
const APIKeys = lazy(() => import('./pages/APIKeys').then(m => ({ default: m.APIKeys })));
const Onboarding = lazy(() => import('./pages/Onboarding').then(m => ({ default: m.Onboarding })));
const AcceptInvite = lazy(() => import('./pages/AcceptInvite').then(m => ({ default: m.AcceptInvite })));
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard').then(m => ({ default: m.AdminDashboard })));
const AdminOrganizations = lazy(() => import('./pages/admin/AdminOrganizations').then(m => ({ default: m.AdminOrganizations })));
const AdminSubscriptions = lazy(() => import('./pages/admin/AdminSubscriptions').then(m => ({ default: m.AdminSubscriptions })));
const AdminApiKeys = lazy(() => import('./pages/admin/AdminApiKeys').then(m => ({ default: m.AdminApiKeys })));
const AdminPlans = lazy(() => import('./pages/admin/AdminPlans').then(m => ({ default: m.AdminPlans })));
const AdminProducts = lazy(() => import('./pages/admin/AdminProducts').then(m => ({ default: m.AdminProducts })));
const AdminBilling = lazy(() => import('./pages/admin/AdminBilling').then(m => ({ default: m.AdminBilling })));
const AdminWebhooks = lazy(() => import('./pages/admin/AdminWebhooks').then(m => ({ default: m.AdminWebhooks })));
const AdminAnalytics = lazy(() => import('./pages/admin/AdminAnalytics').then(m => ({ default: m.AdminAnalytics })));
const AdminSettings = lazy(() => import('./pages/admin/AdminSettings').then(m => ({ default: m.AdminSettings })));
const AdminUsers = lazy(() => import('./pages/admin/AdminUsers').then(m => ({ default: m.AdminUsers })));
const AdminLogoutBehavior = lazy(() => import('./pages/admin/AdminLogoutBehavior').then(m => ({ default: m.AdminLogoutBehavior })));
const AdminTemplates = lazy(() => import('./pages/admin/AdminTemplates').then(m => ({ default: m.AdminTemplates })));
const AdminAuditDigest = lazy(() => import('./pages/admin/AdminAuditDigest').then(m => ({ default: m.AdminAuditDigest })));
const FleetControl = lazy(() => import('./pages/FleetControl').then(m => ({ default: m.FleetControl })));

const App = createProductApp({
  authProvider: coreAuthProvider,
  Layout: CoreLayout,
  Login,
  Landing,
  unauthRedirect: '/landing',
  publicRoutes: [
    { path: '/invite/:token', component: AcceptInvite },
  ],
  routes: [
    { path: '/', component: Dashboard },
    { path: '/pricing', component: Pricing },
    { path: '/billing', component: BillingSettings },
    { path: '/checkout/success', component: CheckoutSuccess },
    { path: '/checkout/cancel', component: CheckoutCancel },
    { path: '/team', component: TeamManagement },
    { path: '/settings', component: AccountSettings },
    { path: '/org-settings', component: OrgSettings },
    { path: '/api-keys', component: APIKeys },
    { path: '/settings/api-keys', component: APIKeys },
    { path: '/onboarding', component: Onboarding },
    { path: '/admin', component: AdminDashboard },
    { path: '/admin/users', component: AdminUsers },
    { path: '/admin/orgs', component: AdminOrganizations },
    { path: '/admin/subs', component: AdminSubscriptions },
    { path: '/admin/api-keys', component: AdminApiKeys },
    { path: '/admin/plans', component: AdminPlans },
    { path: '/admin/products', component: AdminProducts },
    { path: '/admin/billing', component: AdminBilling },
    { path: '/admin/webhooks', component: AdminWebhooks },
    { path: '/admin/analytics', component: AdminAnalytics },
    { path: '/admin/settings', component: AdminSettings },
    { path: '/admin/logout-behavior', component: AdminLogoutBehavior },
    { path: '/admin/templates', component: AdminTemplates },
    { path: '/admin/audit-digest', component: AdminAuditDigest },
    { path: '/admin/fleet', component: FleetControl },
  ],
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
