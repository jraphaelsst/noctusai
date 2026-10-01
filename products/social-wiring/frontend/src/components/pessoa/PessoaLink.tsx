/**
 * PessoaLink — the one way a card, list row or party panel links to the
 * person page (`/clientes/:id`, or `/vendedores/:id` for the seller view —
 * both render `PessoaPage`, the same `clientes.id`).
 *
 * `stopPropagation` because every caller sits on a click surface of its own
 * (a board card that opens the detail dialog, a table row that opens the lead
 * modal): following the link must not ALSO trigger that.
 */
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export type PessoaVisao = "cliente" | "vendedor";

export function pessoaHref(clienteId: string, visao: PessoaVisao = "cliente"): string {
  return `${visao === "vendedor" ? "/vendedores" : "/clientes"}/${encodeURIComponent(clienteId)}`;
}

export function PessoaLink({
  clienteId,
  visao = "cliente",
  className,
  testId,
  title,
  children,
}: {
  clienteId: string;
  visao?: PessoaVisao;
  className?: string;
  testId?: string;
  title?: string;
  children: ReactNode;
}) {
  return (
    <Link
      to={pessoaHref(clienteId, visao)}
      className={className ?? "hover:underline"}
      title={title}
      data-testid={testId}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </Link>
  );
}
