/**
 * `<SectionTabsPage/>` -- a settings-style page whose sections are tabs AND sub-routes.
 *
 * Mount it under a splat route (`<Route path="/configuracoes/*" .../>`) with the same `basePath`; it owns the
 * URL <-> tab sync so no product hand-rolls it: a section is deep-linkable (`/configuracoes/conexoes`), the browser
 * back button works, and the bare `basePath` or a segment it does not know (typo, stale bookmark) redirects
 * (replace) to the canonical URL of the first section. The page grows by adding an entry to `sections` -- nothing
 * else changes.
 *
 * Only the ACTIVE section is rendered (a section that loads data does not fetch while another tab is open).
 * `visible: false` hides a section the viewer may not use (UX gate only -- the server enforces the real one); if
 * every section is hidden nothing is rendered, never an empty shell.
 */
import * as React from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { Tabs, TabsList, TabsTrigger } from '../../design-system/ui/tabs';
import { cn } from '../../utils';

export interface SectionTab {
  /** URL segment (`/<basePath>/<key>`), lowercase, no slashes. */
  key: string;
  label: string;
  icon?: React.ReactNode;
  /** `false` hides the tab and its route. Default true. */
  visible?: boolean;
  render: () => React.ReactNode;
}

export interface SectionTabsPageProps {
  /** URL prefix the splat route is mounted at, e.g. `/configuracoes` (no trailing slash). */
  basePath: string;
  title: string;
  description?: string;
  sections: SectionTab[];
  className?: string;
}

const trimBase = (basePath: string) => basePath.replace(/\/+$/, '');

export function SectionTabsPage({ basePath, title, description, sections, className }: SectionTabsPageProps) {
  const base = trimBase(basePath);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const shown = sections.filter((s) => s.visible !== false);
  if (shown.length === 0) return null;

  const rest = (pathname.startsWith(base) ? pathname.slice(base.length) : '').replace(/^\/+|\/+$/g, '');
  const active = shown.find((s) => s.key === rest);
  if (!active) return <Navigate to={`${base}/${shown[0].key}`} replace />;

  return (
    <div className={cn('space-y-4', className)} data-testid="section-tabs-page">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{title}</h1>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </div>
      <Tabs value={active.key} onValueChange={(key) => navigate(`${base}/${key}`)}>
        <TabsList aria-label={title}>
          {shown.map((s) => (
            <TabsTrigger key={s.key} value={s.key} data-testid={`section-tab-${s.key}`}>
              {s.icon ? <span className="mr-1.5 inline-flex">{s.icon}</span> : null}
              {s.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <div role="tabpanel" aria-label={active.label} data-testid={`section-panel-${active.key}`}>
        {active.render()}
      </div>
    </div>
  );
}
