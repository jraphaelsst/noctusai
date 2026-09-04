/**
 * SectionCard — the common Card+header shape for every CONTRACT § 5 detail
 * section: a title on the left, the display-only `Pencil` placeholder on
 * the right (CONTRACT § 4).
 *
 * Each section component decides FOR ITSELF whether it has anything to show
 * (≥1 non-null field) and returns `null` before reaching this wrapper — this
 * component does not know about "empty", only about rendering a title +
 * edit button + content.
 */
import type { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import EditPlaceholderButton from "./EditPlaceholderButton";

export default function SectionCard({
  title,
  editLabel,
  children,
  contentClassName,
}: {
  title: string;
  /** Defaults to "Editar <title, lowercased>". */
  editLabel?: string;
  children: ReactNode;
  contentClassName?: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
        <EditPlaceholderButton label={editLabel ?? `Editar ${title.toLowerCase()}`} />
      </CardHeader>
      <CardContent className={contentClassName ?? "grid grid-cols-2 gap-4 sm:grid-cols-3"}>
        {children}
      </CardContent>
    </Card>
  );
}
