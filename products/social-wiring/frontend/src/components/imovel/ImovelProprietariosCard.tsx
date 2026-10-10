/**
 * ImovelProprietariosCard — "Proprietários": who owns this imóvel
 * (CONTRACT §4.2, `GET /api/imoveis/{codigo}/proprietarios`). A person links to
 * `/vendedores/:id` (the seller view of the person page); a company has no
 * person page and is shown by name.
 *
 * Loading (lying-loading-state.md): `showSkeleton = isPending && !data`.
 */
import { Loader2, Mail, Phone } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PessoaLink } from "@/components/pessoa/PessoaLink";
import { useImovelProprietarios } from "@/hooks/useImovelRelacionamentos";

const ORIGEM_LABEL: Record<string, string> = {
  manual: "Manual",
  matricula: "Matrícula",
  atendimento: "Atendimento",
};

export function ImovelProprietariosCard({ codigo }: { codigo: string }) {
  const query = useImovelProprietarios(codigo);
  const items = query.data?.items ?? [];
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;

  return (
    <Card data-testid="proprietarios-card">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-1.5 text-base">
          Proprietários{query.data ? ` (${query.data.total})` : ""}
          {isRefreshing && (
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" aria-hidden />
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {showSkeleton ? (
          <div className="h-12 animate-pulse rounded-lg bg-muted" data-testid="proprietarios-loading" />
        ) : query.isError && !query.data ? (
          <p className="text-sm text-destructive" data-testid="proprietarios-erro">
            Não foi possível carregar os proprietários.
          </p>
        ) : items.length === 0 ? (
          <p className="text-sm italic text-muted-foreground" data-testid="proprietarios-vazio">
            Nenhum proprietário registrado para este imóvel.
          </p>
        ) : (
          <ul className="divide-y rounded-lg border" data-testid="proprietarios-lista">
            {items.map((p) => (
              <li
                key={p.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2"
                data-testid={`proprietario-${p.id}`}
              >
                {p.cliente_id ? (
                  <PessoaLink
                    clienteId={p.cliente_id}
                    visao="vendedor"
                    className="text-sm font-semibold hover:underline"
                    testId={`proprietario-link-${p.id}`}
                  >
                    {p.nome || "Sem nome"}
                  </PessoaLink>
                ) : (
                  <span className="text-sm font-semibold">{p.nome || "Sem nome"}</span>
                )}
                {p.fonte_codigo && p.fonte_codigo !== codigo && (
                  <span
                    className="text-xs text-sky-800 dark:text-sky-300"
                    data-testid={`proprietario-fonte-${p.id}`}
                  >
                    do cadastro {p.fonte_codigo}
                  </span>
                )}
                <Badge variant="outline" className="text-[10px]">
                  {p.tipo_pessoa === "PJ" ? "Empresa" : "Pessoa"}
                </Badge>
                <Badge variant="secondary" className="text-[10px]">
                  {ORIGEM_LABEL[p.origem] ?? p.origem}
                </Badge>
                {p.celular && (
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <Phone className="h-3 w-3" aria-hidden />
                    {p.celular}
                  </span>
                )}
                {p.email && (
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <Mail className="h-3 w-3" aria-hidden />
                    {p.email}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
