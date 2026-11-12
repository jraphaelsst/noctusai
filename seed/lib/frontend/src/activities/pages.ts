/**
 * Page keys the activities organ offers a module (mirrors BE `noctusai_lib.domain.activities.ACTIVITIES_PAGES`).
 * `MyTasksPage` is the page; the card-hub TAB (`ActivitiesPanel`) needs no key. A module spreads this into its
 * `defineModule` items: `{ ...ACTIVITIES_PAGES.myTasks, element: lazy(() => import('...MyTasks')) }`.
 */
export const ACTIVITIES_PAGES = {
  myTasks: { pageKey: 'crm_atividades', path: '/crm/atividades', label: 'Atividades' },
} as const;
