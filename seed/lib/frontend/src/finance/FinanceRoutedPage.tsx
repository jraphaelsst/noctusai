/**
 * `<FinanceRoutedPage/>` — the URL-synced host of the finance organ. Mount it under a splat route
 * (`<Route path="/financeiro/*" …/>`) and pass the `basePath`; it owns the URL ⇄ section sync so no product
 * re-implements it: a section is deep-linkable, the browser back button works, and a segment the organ does not
 * know (typo, stale bookmark, `receber/x`) redirects (replace) to the canonical URL of the section it maps to.
 *
 * The caller supplies EITHER `hooks` (an already-built `createFinanceHooks(api)`) OR `api` (built once here).
 * `isAdmin` / `isAccountant` are UX gates only — the server enforces every write and export again.
 * `title` / `className` give the host an optional heading + wrapper; page chrome beyond that stays with the host.
 */
import * as React from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { FinanceShell, financeSectionFromPath, financeSectionPath } from './FinanceShell';
import type { FinanceSectionKey } from './FinanceShell';
import { createFinanceHooks } from './hooks';
import type { FinanceApi, FinanceHooks } from './hooks';

export type FinanceRoutedPageProps = {
  /** URL prefix the splat route is mounted at, e.g. `/financeiro` or `/admin/financeiro` (no trailing slash). */
  basePath: string;
  isAdmin?: boolean;
  isAccountant?: boolean;
  /** Optional page heading rendered above the shell. */
  title?: string;
  /** Optional wrapper class (e.g. `space-y-4 p-4`); when neither `title` nor `className` is set there is no wrapper. */
  className?: string;
  now?: Date;
} & ({ hooks: FinanceHooks; api?: never } | { api: FinanceApi; hooks?: never });

const trimBase = (basePath: string) => basePath.replace(/\/+$/, '');

export function FinanceRoutedPage({ basePath, isAdmin = false, isAccountant = false, title, className, now, hooks, api }: FinanceRoutedPageProps) {
  const base = trimBase(basePath);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const built = React.useMemo(() => hooks ?? createFinanceHooks(api as FinanceApi), [hooks, api]);

  const pathFor = React.useCallback(
    (key: FinanceSectionKey) => {
      const seg = financeSectionPath(key);
      return seg ? `${base}/${seg}` : base;
    },
    [base],
  );

  const segment = (pathname.startsWith(base) ? pathname.slice(base.length) : '').replace(/^\/+|\/+$/g, '');
  const section = financeSectionFromPath(segment);
  if (segment !== financeSectionPath(section)) return <Navigate to={pathFor(section)} replace />;

  const shell = (
    <FinanceShell hooks={built} isAdmin={isAdmin} isAccountant={isAccountant} section={section} onSectionChange={(key) => navigate(pathFor(key))} now={now} />
  );
  if (!title && !className) return shell;
  return (
    <div className={className}>
      {title ? <h1 className="text-2xl font-semibold">{title}</h1> : null}
      {shell}
    </div>
  );
}
