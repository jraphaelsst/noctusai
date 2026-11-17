/**
 * PaginaCabecalho — the page header of a CoreStudio page that can also render as a SECTION of a
 * tabs page (Roteiros). The tabs page already owns the h1 and description, so inside it the page
 * drops its own title and keeps only its controls (MarcaSwitcher, "Criar roteiro", ...).
 *
 * The flag travels by context, so a page does not thread a prop and the standalone mount (a test,
 * a future route) is unchanged.
 */
import { createContext, useContext, type ReactNode } from "react";

const EmbeddedContext = createContext(false);

/** Wrap a section's content: pages below render as embedded (no h1 / description / page padding). */
export function EmbeddedPagina({ children }: { children: ReactNode }) {
  return <EmbeddedContext.Provider value={true}>{children}</EmbeddedContext.Provider>;
}

export const useEmbedded = () => useContext(EmbeddedContext);

/** Outer padding of a standalone page; the tabs page already pads its sections. */
export function usePaginaPadding(): string {
  return useEmbedded() ? "" : "p-6";
}

export function PaginaCabecalho({
  titulo,
  descricao,
  children,
}: {
  titulo: ReactNode;
  descricao?: ReactNode;
  /** The page's controls (right side). */
  children?: ReactNode;
}) {
  const embedded = useEmbedded();
  if (embedded && !children) return null;
  return (
    <header className={`flex flex-wrap items-start gap-4 ${embedded ? "justify-end" : "justify-between"}`}>
      {embedded ? null : (
        <div>
          <h1 className="text-2xl font-semibold">{titulo}</h1>
          {descricao ? <p className="text-sm text-muted-foreground">{descricao}</p> : null}
        </div>
      )}
      {children ? <div className="flex flex-wrap items-center gap-3">{children}</div> : null}
    </header>
  );
}
