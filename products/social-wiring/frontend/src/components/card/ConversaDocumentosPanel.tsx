/**
 * ConversaDocumentosPanel — "Pedir documentos" over WhatsApp + the triage list
 * of documents that arrived by WhatsApp and still need a type (CONTRACT §2.2 /
 * §2.3). Self-contained: it fetches its own data keyed by `clienteId`.
 *
 * Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching &&
 * !!data` — never `isLoading`, never an unmount of rows that exist.
 */
import { Loader2, MessageCircle, Paperclip } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  useClassificarDocumento,
  useConversa,
  useDocumentosAClassificar,
  usePedirDocumentos,
} from "@/hooks/useConversaDocumentos";
import type { DocumentoAClassificar } from "@/types/conversa";

import { mensagemDoErro } from "./mensagemDoErro";

/** Types the operator can assign (those with a reader). The server refuses the rest. */
export const TIPOS_CLASSIFICAVEIS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "rg", label: "RG/CPF" },
  { value: "cnh", label: "CNH" },
  { value: "cin", label: "CIN" },
  { value: "certidao_casamento", label: "Certidão de casamento" },
  { value: "certidao_nascimento", label: "Certidão de nascimento" },
  { value: "comprovante_endereco", label: "Comprovante de endereço" },
];

export interface ConversaDocumentosPanelProps {
  clienteId: string;
}

function LinhaATriar({ doc, clienteId }: { doc: DocumentoAClassificar; clienteId: string }) {
  const classificar = useClassificarDocumento(clienteId);
  const [tipo, setTipo] = useState("");
  const dica = doc.classificacao_tipo_provavel
    ? `Sugestão: ${doc.classificacao_tipo_provavel}`
    : "Tipo não reconhecido";

  return (
    <li
      className="flex items-center gap-2 text-sm"
      data-testid={`a-classificar-${doc.id}`}
    >
      <Paperclip className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate" title={doc.nome_original}>
        {doc.nome_original}
        <span className="ml-2 text-xs text-muted-foreground">{dica}</span>
      </span>
      <select
        aria-label={`Tipo de ${doc.nome_original}`}
        className="h-8 rounded-md border bg-background px-2 text-xs"
        value={tipo}
        onChange={(e) => setTipo(e.target.value)}
      >
        <option value="">Tipo…</option>
        {TIPOS_CLASSIFICAVEIS.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>
      <Button
        size="sm"
        variant="secondary"
        disabled={!tipo || classificar.isPending}
        onClick={() =>
          classificar.mutate(
            { documentoId: doc.id, tipo },
            {
              onError: (err) =>
                toast.error(mensagemDoErro(err, "Não foi possível classificar o documento.")),
              onSuccess: () => toast.success("Documento classificado — leitura em andamento."),
            },
          )
        }
      >
        {classificar.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Classificar"}
      </Button>
    </li>
  );
}

export function ConversaDocumentosPanel({ clienteId }: ConversaDocumentosPanelProps) {
  const conversa = useConversa(clienteId);
  const aClassificar = useDocumentosAClassificar(clienteId);
  const pedir = usePedirDocumentos(clienteId);

  const showSkeleton = conversa.isPending && !conversa.data;
  const isRefreshing = (conversa.isFetching && !!conversa.data) || (aClassificar.isFetching && !!aClassificar.data);
  const pendentes = aClassificar.data?.items ?? [];
  const ultimas = (conversa.data?.mensagens ?? []).slice(-3);

  return (
    <section className="space-y-3 rounded-md border p-3" data-testid="conversa-documentos-panel">
      <header className="flex items-center gap-2">
        <MessageCircle className="h-4 w-4 text-muted-foreground" />
        <h4 className="flex-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Documentos por WhatsApp
        </h4>
        {isRefreshing && (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" data-testid="conversa-refreshing" />
        )}
        <Button
          size="sm"
          disabled={pedir.isPending}
          onClick={() =>
            pedir.mutate(undefined, {
              onSuccess: (r) =>
                toast.success(`Pedido enviado: ${r.itens_solicitados.join(", ")}`),
              onError: (err) =>
                toast.error(mensagemDoErro(err, "Não foi possível pedir os documentos.")),
            })
          }
        >
          {pedir.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Pedir documentos"}
        </Button>
      </header>

      {showSkeleton ? (
        <div className="h-10 animate-pulse rounded bg-muted" data-testid="conversa-skeleton" />
      ) : ultimas.length > 0 ? (
        <ul className="space-y-1" data-testid="conversa-mensagens">
          {ultimas.map((m) => (
            <li
              key={m.id}
              className={m.direcao === "out" ? "text-right text-sm" : "text-left text-sm"}
            >
              <span className="inline-block max-w-[85%] rounded-md bg-muted px-2 py-1">
                {m.anexo && <Paperclip className="mr-1 inline h-3 w-3" />}
                {m.texto}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">Nenhuma conversa ainda.</p>
      )}

      {pendentes.length > 0 && (
        <div className="space-y-2" data-testid="a-classificar-lista">
          <h5 className="text-xs font-medium">
            Aguardando classificação ({pendentes.length})
          </h5>
          <ul className="space-y-1">
            {pendentes.map((d) => (
              <LinhaATriar key={d.id} doc={d} clienteId={clienteId} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
