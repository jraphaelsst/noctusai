/**
 * `<ImovelConflitosCard/>` — the decide surface for `imovel_campo_conflitos`
 * (migration 154, D1) on `/imoveis/:codigo`.
 *
 * WHY IT EXISTS. The backend had both halves — `GET /api/imoveis/{codigo}/
 * conflitos` and `PUT .../conflitos/{id}/decidir` — and no screen called the
 * second one: a matrícula reading that disagreed with a value a human typed
 * opened a conflict nobody could decide (route-exists ≠ wired).
 *
 * NOT A COPY of the cliente card: it mounts `ConflitosPendentesCard` and only
 * supplies the imóvel seams — field labels, JSONB group values, and the
 * source document the proposed value was read from. Settings › Pendências
 * reuses the same three helpers exported below.
 *
 * STATES. First load and "no pending conflict" render nothing — this card
 * only exists while there is something to decide, same as the cliente
 * `ConflitosPendentesPanel` (a skeleton here would flash on every imóvel
 * page, almost all of which have no conflict). A failed read is NOT silent:
 * it renders an error card with a retry. A refetch after a decision keeps
 * the list on screen (two signals off `data`).
 */
import { ExternalLink, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext } from "@noctusai/lib";

import { ConflitosPendentesCard } from "@/components/card/ConflitosPendentesCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  useDecidirImovelConflito,
  useImovelConflitos,
  useImovelDocumentoMutations,
  useImovelDocumentos,
  type ImovelConflito,
  type ImovelDocumento,
} from "@/hooks/useImovelDados";
import { rotuloTipo } from "@/lib/documentoTipos";

/** `imovel_campo_conflitos.campo` -> the label `ImovelCartorioCard` uses for
 *  the same field, so one fact reads the same way in both places. Keys
 *  mirror `campos_extraidos_service.CAMPOS`. */
const CAMPO_ROTULOS_IMOVEL: Record<string, string> = {
  numero_matricula: "Número da matrícula",
  numero_registro_imoveis: "Número do registro de imóveis",
  prefeitura_cadastro_imobiliario: "Inscrição municipal (cadastro na prefeitura)",
  situacao_onus: "Situação de ônus",
  titulo_aquisitivo_texto: "Título aquisitivo",
  onus_credor: "Credor do ônus",
  titulo_aquisitivo: "Ato do título aquisitivo (matrícula)",
  onus_fonte: "Atos de ônus (matrícula)",
};

export function rotuloCampoImovel(campo: string): string {
  return CAMPO_ROTULOS_IMOVEL[campo] ?? campo;
}

/** A scalar field is its string; the two pointer GROUPS are named by the
 *  act(s) they point at — the identity the backend compares them by
 *  (`_identidade`), never the raw offsets. Anything else falls back to JSON:
 *  never blank, never `[object Object]`. */
export function formatarValorImovel(campo: string, valor: unknown): string {
  if (valor == null || valor === "") return "—";
  if (typeof valor === "string" || typeof valor === "number") return String(valor);
  if (typeof valor === "object") {
    const v = valor as Record<string, unknown>;
    if (campo === "titulo_aquisitivo" && v.titulo_aquisitivo_ato_id != null) {
      return `Ato ${String(v.titulo_aquisitivo_ato_id)}`;
    }
    if (campo === "onus_fonte" && Array.isArray(v.onus_fonte_atos)) {
      const atos = (v.onus_fonte_atos as Array<Record<string, unknown>>)
        .map((a) => (a && a.ato_id != null ? String(a.ato_id) : null))
        .filter((a): a is string => a !== null);
      return atos.length ? `Atos ${atos.join(", ")}` : "—";
    }
  }
  return JSON.stringify(valor);
}

/** Where the proposed value came from, in words — used when the source
 *  document itself is not resolvable to an openable file. */
export function rotuloFonteImovel(c: Pick<ImovelConflito, "fonte_tabela" | "origem_proposto">): string {
  if (c.fonte_tabela === "matricula_extracoes") return "Leitura da matrícula (extrator)";
  if (c.fonte_tabela === "imovel_documentos") return "Documento do imóvel";
  return c.origem_proposto === "manual" ? "Edição manual" : `Origem: ${c.origem_proposto}`;
}

/** The imóvel document the proposed value was read from, if this imóvel
 *  still has it — `documento_id_proposto` first, then an `imovel_documentos`
 *  `fonte_id`. */
export function documentoFonte(
  c: ImovelConflito,
  documentos: ImovelDocumento[],
): ImovelDocumento | undefined {
  const ids = [
    c.documento_id_proposto,
    c.fonte_tabela === "imovel_documentos" ? c.fonte_id : null,
  ].filter((id): id is string => !!id);
  return documentos.find((d) => ids.includes(d.id));
}

function erro(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

export function ImovelConflitosCard({ codigo }: { codigo: string }) {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  // UI convenience only — the server reads the TRUSTED `noctus_users` row
  // and 403s a spoofed claim regardless (`decidir_conflito_route`).
  const isAdmin =
    ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";

  const conflitos = useImovelConflitos(codigo);
  // Shares `ImovelDocumentosCard`'s own cache entry — no second request.
  const documentos = useImovelDocumentos(codigo);
  const { getUrl } = useImovelDocumentoMutations(codigo);
  const decidir = useDecidirImovelConflito();

  if (conflitos.isError && !conflitos.data) {
    return (
      <Card data-testid="imovel-conflitos-erro">
        <CardContent className="flex flex-col items-center gap-3 p-6 text-center">
          <p className="text-sm text-muted-foreground">
            Não foi possível carregar as pendências de confirmação deste imóvel.
          </p>
          <Button variant="outline" size="sm" onClick={() => conflitos.refetch()}>
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }
  if (!conflitos.data?.length) return null;

  const abrir = async (documentoId: string) => {
    try {
      const res = await getUrl.mutateAsync(documentoId);
      if (res?.url) window.open(res.url, "_blank", "noopener,noreferrer");
    } catch (e) {
      toast.error(erro(e, "Não foi possível abrir o documento."));
    }
  };

  return (
    <div id="imovel-conflitos">
      <ConflitosPendentesCard<ImovelConflito>
        conflitos={conflitos.data}
        isAdmin={isAdmin}
        titulo="Pendências de confirmação dos dados do imóvel"
        rotuloCampo={rotuloCampoImovel}
        formatarValor={formatarValorImovel}
        itemTestId={(id) => `imovel-conflito-${id}`}
        testId="imovel-conflitos"
        decidingId={decidir.isPending ? decidir.variables?.conflitoId ?? null : null}
        renderDetalhe={(c) => {
          const doc = documentoFonte(c, documentos.data ?? []);
          return (
            <div
              className="mt-1 flex items-center gap-2 text-xs text-muted-foreground"
              data-testid={`imovel-conflito-${c.id}-fonte`}
            >
              <FileText className="h-3.5 w-3.5" />
              {doc ? (
                <button
                  type="button"
                  className="inline-flex items-center gap-1 underline underline-offset-2 hover:text-foreground"
                  onClick={() => void abrir(doc.id)}
                  data-testid={`imovel-conflito-${c.id}-documento`}
                >
                  {rotuloTipo("imovel", doc.tipo_documento)} — {doc.nome_original}
                  <ExternalLink className="h-3 w-3" />
                </button>
              ) : (
                <span>{rotuloFonteImovel(c)}</span>
              )}
            </div>
          );
        }}
        onDecidir={(conflitoId, aceitar) =>
          decidir.mutate(
            { codigo, conflitoId, aceitar },
            {
              onError: (e) => toast.error(erro(e, "Não foi possível decidir a pendência.")),
            },
          )
        }
      />
    </div>
  );
}

/**
 * The org-wide imóvel list for Settings › Pendências (owner/admin tab):
 * every pending conflict across every imóvel, each row naming its imóvel and
 * linking to the page where its source document can be opened. Decides in
 * place with the same mutation the per-imóvel card uses. Presentational over
 * the `conflitos` its caller already fetched (the tab needs the count to
 * decide its own empty state).
 */
export function ImovelConflitosPendentesOrgCard({
  conflitos,
}: {
  conflitos: ImovelConflito[];
}) {
  const decidir = useDecidirImovelConflito();
  return (
    <ConflitosPendentesCard<ImovelConflito>
      conflitos={conflitos}
      // The tab itself is owner/admin only; the PUT re-checks (403).
      isAdmin
      titulo="Pendências de confirmação de imóveis"
      rotuloCampo={rotuloCampoImovel}
      formatarValor={formatarValorImovel}
      itemTestId={(id) => `imovel-conflito-${id}`}
      testId="pendencias-imoveis"
      decidingId={decidir.isPending ? decidir.variables?.conflitoId ?? null : null}
      renderDetalhe={(c) => (
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Link
            to={`/imoveis/${encodeURIComponent(c.codigo)}#imovel-conflitos`}
            className="font-medium underline underline-offset-2 hover:text-foreground"
            data-testid={`imovel-conflito-${c.id}-link`}
          >
            Imóvel {c.codigo}
          </Link>
          <span>· {rotuloFonteImovel(c)}</span>
        </div>
      )}
      onDecidir={(conflitoId, aceitar) => {
        const conflito = conflitos.find((c) => c.id === conflitoId);
        if (!conflito) {
          // Cannot happen (the button comes from this list) — but never a
          // silent no-op if it ever does.
          toast.error("Pendência não encontrada na lista — recarregue a página.");
          return;
        }
        decidir.mutate(
          { codigo: conflito.codigo, conflitoId, aceitar },
          { onError: (e) => toast.error(erro(e, "Não foi possível decidir a pendência.")) },
        );
      }}
    />
  );
}
