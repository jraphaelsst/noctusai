/**
 * Back-office page frame: heading + intro, inside a `CommerceLocaleProvider`
 * set to the store profile's `locale` so the organ components and the host
 * copy speak the store's language. While the profile is still loading (or
 * absent — a new store) the default locale applies; nothing is hidden.
 */
import * as React from "react";
import { CommerceLocaleProvider, DEFAULT_COMMERCE_LOCALE } from "@noctusai/lib";

import { staffCommerce } from "@/lib/commerce";
import { usePageT } from "@/lib/i18n";

export function useStoreLocale(): string {
  const profile = staffCommerce.useProfile();
  return profile.data?.locale ?? DEFAULT_COMMERCE_LOCALE;
}

function Heading({ titleKey, introKey, actions }: { titleKey: string; introKey?: string; actions?: React.ReactNode }) {
  const { t } = usePageT();
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-foreground">{t(titleKey)}</h1>
        {introKey ? <p className="max-w-3xl text-sm text-muted-foreground">{t(introKey)}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function AdminFrame({
  titleKey,
  introKey,
  actions,
  children,
}: {
  titleKey: string;
  introKey?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const locale = useStoreLocale();
  return (
    <CommerceLocaleProvider locale={locale}>
      <div className="space-y-6">
        <Heading titleKey={titleKey} introKey={introKey} actions={actions} />
        {children}
      </div>
    </CommerceLocaleProvider>
  );
}
