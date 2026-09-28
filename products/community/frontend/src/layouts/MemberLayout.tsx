/**
 * MemberLayout — the portal shell a `membro` sees (ninho-vazio CONTRACT.md
 * §Frontend: "a `membro` must never see staff nav or pages").
 *
 * Built with the seed's `createProductLayout` exactly like the staff layout
 * in `App.tsx` — only the nav differs. The two nav routes map to the
 * `status_pagina` rows migration 013 seeds (`portal`,
 * `portal-grupoterapia`), so `filterNavByPageStatus` keeps them visible.
 * `RoleLayout` picks this or the staff layout from `GET /api/eu`.
 */
import { createProductLayout } from "@noctusai/seed";
import infra from "@noctusai/seed/infra";
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import { Feather, HeartHandshake, UserRound } from "lucide-react";

export const MEMBER_NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "portal",
    label: "Minha área",
    icon: HeartHandshake,
    defaultOpen: true,
    items: [
      { name: "Minha conta", href: "/portal", icon: UserRound, route: "portal" },
      { name: "Grupoterapia", href: "/portal/grupoterapia", icon: HeartHandshake, route: "portal-grupoterapia" },
    ],
  },
];

export const MEMBER_NAV_FALLBACK: NavGroup[] = [
  {
    key: "portal",
    label: "Minha área",
    icon: HeartHandshake,
    defaultOpen: true,
    items: [
      { name: "Minha conta", href: "/portal", icon: UserRound },
      { name: "Grupoterapia", href: "/portal/grupoterapia", icon: HeartHandshake },
    ],
  },
];

export const MemberLayout = createProductLayout({
  brandIcon: Feather,
  brandTitle: "Ninho Vazio",
  navGroups: MEMBER_NAV_GROUPS,
  navGroupsFallback: MEMBER_NAV_FALLBACK,
  roleLabelOverride: "Membro",
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});
