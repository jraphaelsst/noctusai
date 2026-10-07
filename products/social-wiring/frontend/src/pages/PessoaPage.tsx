/**
 * PessoaPage — ONE person page behind TWO routes: `/clientes/:id` and
 * `/vendedores/:id` (decision D3: roles overlap — a comprador can also be a
 * vendedor — so a single component renders both, ordering sections by route).
 *
 *   /clientes/:id    header · contatos · atendimentos → Interesses
 *                    → "Imóveis que possui" (bottom)
 *   /vendedores/:id  header → "Imóveis à venda" → Interesses (bottom — the
 *                    intro to permuta)
 *
 * Data: `GET /api/clientes/{id}/resumo` (CONTRACT §4.5). The page is wired to
 * real data and owns the CRUD of both sections in place.
 *
 * Loading (lying-loading-state.md): `showSkeleton = isPending && !data`;
 * a background refetch only shows a small spinner.
 */
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext } from "@noctusai/lib";
import { AlertCircle, ArrowLeft, Loader2, Mail, MessageCircle, Trash2 } from "lucide-react";

import { ImovelInteressesList } from "@/components/interesses/ImovelInteressesList";
import { ProprietariosSection } from "@/components/interesses/ProprietariosSection";
import { whatsappHref } from "@/components/interesses/contato";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ExcluirClienteConfirmDialog } from "@/components/card/ExcluirClienteConfirmDialog";
import { useClienteMutations } from "@/hooks/useClientes";
import { usePessoaResumo } from "@/hooks/usePessoa";
import { toastServerError } from "@/lib/erroServidor";
import { formatDate } from "@/lib/utils";
import type { PessoaPapel, PessoaResumo } from "@/types/pessoa";

const PAPEL_LABEL: Record<PessoaPapel, string> = {
  lead: "Lead",
  comprador: "Comprador",
  vendedor: "Vendedor",
  proprietario: "Proprietário",
};

export type PessoaVisao = "comprador" | "vendedor";

export default function PessoaPage() {
  const { id } = useParams<{ id: string }>();
  const { pathname } = useLocation();
  const visao: PessoaVisao = pathname.startsWith("/vendedores") ? "vendedor" : "comprador";

  const navigate = useNavigate();
  const query = usePessoaResumo(id);
  const { remove: excluirCliente } = useClienteMutations();
  const [confirmExcluirOpen, setConfirmExcluirOpen] = useState(false);
  // UI convenience only — same gate as ClienteDetailModal; the server's
  // `require_org_admin_role` on DELETE /api/clientes/{id} is the real one.
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdmin =
    ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;

  if (showSkeleton) {
    return (
      <div className="space-y-6 p-6" data-testid="pessoa-loading">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full rounded-lg" />
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    );
  }

  if (query.isError || !query.data || !id) {
    return (
      <div className="p-6">
        <Card>
          <CardContent
            className="flex flex-col items-center gap-3 py-16 text-center"
            data-testid="pessoa-erro"
          >
            <AlertCircle className="h-10 w-10 text-destructive" />
            <p className="font-medium">Não foi possível carregar esta pessoa.</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Ela pode ter sido removida ou unificada com outro cadastro.
            </p>
            <Button asChild variant="outline">
              <Link to="/clientes">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Voltar aos clientes
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const resumo = query.data;
  const interesses = <ImovelInteressesList key="interesses" clienteId={id} atendimentoId={atendimentoUnico(resumo)} />;
  const propriedades = (
    <ProprietariosSection
      key="propriedades"
      clienteId={id}
      titulo={visao === "vendedor" ? "Imóveis à venda" : "Imóveis que possui"}
    />
  );
  // D3: comprador → interesses first, ownership at the bottom;
  //     vendedor  → ownership first, interesses at the bottom (permuta intro).
  const secoes = visao === "vendedor" ? [propriedades, interesses] : [interesses, propriedades];
  const outraVisao =
    visao === "vendedor"
      ? { to: `/clientes/${id}`, label: "Ver como cliente" }
      : { to: `/vendedores/${id}`, label: "Ver como vendedor" };

  return (
    <div className="space-y-6 p-6" data-testid={`pessoa-page-${visao}`}>
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link to="/clientes">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Clientes
        </Link>
      </Button>

      <PessoaCabecalho
        resumo={resumo}
        refreshing={isRefreshing}
        outraVisao={outraVisao}
        onExcluir={isAdmin ? () => setConfirmExcluirOpen(true) : undefined}
      />

      <ExcluirClienteConfirmDialog
        open={confirmExcluirOpen}
        pending={excluirCliente.isPending}
        nome={resumo.cliente.nome_oficial || resumo.cliente.nome || ""}
        onOpenChange={setConfirmExcluirOpen}
        onConfirm={() => {
          excluirCliente.mutate(id, {
            onSuccess: (result) => {
              setConfirmExcluirOpen(false);
              if (result.storage_falhas.length > 0) {
                toast.warning(
                  "Cliente excluído, mas alguns arquivos não puderam ser removidos do armazenamento.",
                  { description: result.storage_falhas.join(", ") },
                );
              }
              navigate("/clientes", { replace: true });
            },
            // 409 (merge-survivor) message comes through toastServerError.
            onError: (err) => toastServerError(err, "Não foi possível excluir o cliente."),
          });
        }}
      />

      {secoes.map((secao, i) => (
        <Card key={i}>
          <CardContent className="pt-6">{secao}</CardContent>
        </Card>
      ))}
    </div>
  );
}

/** The one open (non-arquivado) atendimento, when unambiguous — passed down so
 *  the roteiro POST never answers 409. Several ⇒ the dialog asks. */
function atendimentoUnico(resumo: PessoaResumo): string | undefined {
  const abertos = resumo.atendimentos.filter((a) => !a.arquivado);
  return abertos.length === 1 ? abertos[0].id : undefined;
}

function PessoaCabecalho({
  resumo,
  refreshing,
  outraVisao,
  onExcluir,
}: {
  resumo: PessoaResumo;
  refreshing: boolean;
  outraVisao: { to: string; label: string };
  onExcluir?: () => void;
}) {
  const { cliente, papeis, contatos, atendimentos, contagens } = resumo;
  const nome = cliente.nome_oficial || cliente.nome || "Sem nome";
  const wa = whatsappHref(contatos.celular);

  return (
    <Card data-testid="pessoa-cabecalho">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div className="space-y-2">
          <CardTitle className="flex items-center gap-2 text-xl">
            {nome}
            {refreshing && (
              <Loader2
                className="h-3.5 w-3.5 animate-spin text-muted-foreground"
                data-testid="pessoa-refreshing"
              />
            )}
          </CardTitle>
          <div className="flex flex-wrap gap-1.5" data-testid="pessoa-papeis">
            {papeis.map((p) => (
              <Badge key={p} variant="secondary">
                {PAPEL_LABEL[p] ?? p}
              </Badge>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            {contatos.celular ? (
              wa ? (
                <a
                  href={wa}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:underline"
                  data-testid="pessoa-whatsapp"
                >
                  <MessageCircle className="h-3.5 w-3.5" aria-hidden />
                  {contatos.celular}
                </a>
              ) : (
                <span>{contatos.celular}</span>
              )
            ) : (
              <span>Sem telefone</span>
            )}
            {contatos.email && (
              <a
                href={`mailto:${contatos.email}`}
                className="inline-flex items-center gap-1 hover:underline"
              >
                <Mail className="h-3.5 w-3.5" aria-hidden />
                {contatos.email}
              </a>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to={outraVisao.to}>{outraVisao.label}</Link>
          </Button>
          {onExcluir && (
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={onExcluir}
              data-testid="pessoa-excluir"
            >
              <Trash2 className="mr-2 h-4 w-4" aria-hidden />
              Excluir cliente
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground" data-testid="pessoa-contagens">
          {contagens.atendimentos} atendimento(s) · {contagens.interesses} interesse(s) ·{" "}
          {contagens.propriedades} imóvel(is) · {contagens.roteiros} roteiro(s)
        </p>

        <div>
          <h3 className="mb-2 text-sm font-semibold">Atendimentos</h3>
          {atendimentos.length === 0 ? (
            <p className="text-sm italic text-muted-foreground" data-testid="pessoa-atendimentos-vazio">
              Nenhum atendimento.
            </p>
          ) : (
            <ul className="divide-y rounded-lg border" data-testid="pessoa-atendimentos">
              {atendimentos.map((a) => (
                <li
                  key={`${a.id}-${a.parte_id ?? "t"}`}
                  className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm"
                  data-testid={`pessoa-atendimento-${a.id}`}
                >
                  <span className="font-medium">{a.titulo ?? "Atendimento"}</span>
                  {a.etapa && <Badge variant="outline">{a.etapa.nome}</Badge>}
                  {a.arquivado && <Badge variant="secondary">Arquivado</Badge>}
                  {a.titular ? (
                    <Badge variant="secondary">Titular</Badge>
                  ) : (
                    a.papel && <Badge variant="secondary">{a.papel}</Badge>
                  )}
                  {a.imovel_pendente && <Badge variant="destructive">Imóvel pendente</Badge>}
                  <span className="flex flex-wrap gap-1">
                    {a.imoveis.map((c) => (
                      <Link
                        key={c}
                        to={`/imoveis/${encodeURIComponent(c)}`}
                        className="text-xs text-primary hover:underline"
                      >
                        {c}
                      </Link>
                    ))}
                  </span>
                  {a.created_at && (
                    <span className="ml-auto text-xs text-muted-foreground">
                      {formatDate(a.created_at, false)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
