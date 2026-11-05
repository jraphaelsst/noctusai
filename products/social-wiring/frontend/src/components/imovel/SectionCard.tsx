/**
 * SectionCard — the common Card+header shape for every CONTRACT § 5 detail
 * section: a title on the left, the read-only "Vista" provenance marker (with
 * the last-sync time) on the right.
 *
 * Every section rendered through this card is a MIRROR of Vista (CONTRACT
 * § 4: Vista rejects every write route on this key), so it is read-only by
 * construction and says so — instead of the former pencil that toasted "not
 * available". What WE author lives in its own cards (cartório, endereço,
 * avaliação, notas, ...). → KB § PATTERNS/frontend/mirror-owned-overlay.md
 *
 * Each section component decides FOR ITSELF whether it has anything to show
 * (≥1 non-null field) and returns `null` before reaching this wrapper — this
 * component does not know about "empty", only about rendering a title +
 * edit button + content.
 */
import type { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { SourceBadge } from "@noctusai/lib/components";

import { useVistaSyncedAt } from "./VistaSyncContext";

export default function SectionCard({
  title,
  children,
  contentClassName,
}: {
  title: string;
  children: ReactNode;
  contentClassName?: string;
}) {
  const syncedAt = useVistaSyncedAt();
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
        <SourceBadge source="Vista" syncedAt={syncedAt} />
      </CardHeader>
      <CardContent className={contentClassName ?? "grid grid-cols-2 gap-4 sm:grid-cols-3"}>
        {children}
      </CardContent>
    </Card>
  );
}
