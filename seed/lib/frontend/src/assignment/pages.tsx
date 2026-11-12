/**
 * Page keys + module items of the assignment organ: what a module (`defineModule`, CRM) mounts.
 *
 * `ASSIGNMENT_PAGE_KEYS` are the `status_pagina.nome_pagina` rows AND the BE `PageSpec` keys (`noctusai_seed.modules.assignment`);
 * a BE test parses this file and pins the two sides together. The module's sidebar position and paths are the host's call:
 *
 *     const items = assignmentModuleItems({ hooks, canWrite: () => useIsOrgAdmin() });   // two ModuleItems
 *     defineModule({ key: 'crm', items: [...crmItems, ...items] })
 */
import * as React from 'react';
import type { ElementType } from 'react';
import type { ModuleItem, ModulePageStatus } from '../modules/define';
import { AssignmentRulesPage } from './AssignmentRulesPage';
import type { AssignmentTranslate } from './i18n';
import type { AssignmentHooks } from './hooks';
import { TeamsManager } from './TeamsManager';

export const ASSIGNMENT_PAGE_KEYS = { rules: 'crm_distribuicao', teams: 'crm_equipes' } as const;
export const ASSIGNMENT_DEFAULT_PATHS = { rules: '/crm/distribuicao', teams: '/crm/equipes' } as const;
export const ASSIGNMENT_DEFAULT_LABELS = { rules: 'Distribuição', teams: 'Equipes' } as const;

export interface AssignmentModuleItemsOptions {
  hooks: AssignmentHooks;
  /** A boolean, or a HOOK (`() => boolean`) the page calls while rendering (the role is only known inside the tree). */
  canWrite?: boolean | (() => boolean);
  t?: AssignmentTranslate;
  locale?: string;
  paths?: Partial<Record<keyof typeof ASSIGNMENT_PAGE_KEYS, string>>;
  labels?: Partial<Record<keyof typeof ASSIGNMENT_PAGE_KEYS, string>>;
  icons?: Partial<Record<keyof typeof ASSIGNMENT_PAGE_KEYS, ElementType>>;
  /** Org roles that see the items (UX only; the API enforces). Omitted = every role. */
  roles?: readonly string[];
  status?: ModulePageStatus;
}

export function assignmentModuleItems(opts: AssignmentModuleItemsOptions): ModuleItem[] {
  const { hooks, t, locale } = opts;
  const useWrite = typeof opts.canWrite === 'function' ? opts.canWrite : () => !!opts.canWrite;
  const Rules = () => <AssignmentRulesPage hooks={hooks} t={t} locale={locale} canWrite={useWrite()} />;
  const Teams = () => <TeamsManager hooks={hooks} t={t} locale={locale} canWrite={useWrite()} />;
  const base = { roles: opts.roles, status: opts.status } as const;
  const item = (k: keyof typeof ASSIGNMENT_PAGE_KEYS, element: ModuleItem['element']): ModuleItem => ({
    ...base,
    label: opts.labels?.[k] ?? ASSIGNMENT_DEFAULT_LABELS[k],
    path: opts.paths?.[k] ?? ASSIGNMENT_DEFAULT_PATHS[k],
    pageKey: ASSIGNMENT_PAGE_KEYS[k],
    icon: opts.icons?.[k],
    element,
  });
  return [item('rules', Rules), item('teams', Teams)];
}
