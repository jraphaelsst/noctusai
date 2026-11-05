/**
 * ImovelNotasCard — OUR notes on this imóvel (migration 315). Owned data,
 * full CRUD: add, edit, remove (with confirmation).
 *
 * Mirror + owned overlay (`KB § PATTERNS/frontend/mirror-owned-overlay.md`):
 * Vista has no notes field and the sync never touches this table, so the
 * whole card is editable. Every write goes through `useCacheWriteMutation`
 * (the list updates the instant the operator acts and converges on the
 * server's row); a refusal is drawn under the form it came from; a typed
 * draft says it is unsaved.
 */
import { useState } from "react";
import { Loader2, Pencil, StickyNote, Trash2 } from "lucide-react";

import { QueryErrorState, UnsavedChangesNotice, useConfirm, useUnsavedChanges } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { type ImovelNota, useImovelNotaMutations, useImovelNotas } from "@/hooks/useImovelDados";

const MAX = 4000;

function quando(n: ImovelNota): string {
  const iso = n.updated_at && n.updated_at !== n.created_at ? n.updated_at : n.created_at;
  const data = iso ? new Date(iso).toLocaleString("pt-BR") : "";
  const quem = (n.updated_by ?? n.created_by)?.nome;
  const editada = n.updated_at && n.updated_at !== n.created_at ? " (editada)" : "";
  return [quem, data].filter(Boolean).join(" · ") + editada;
}

function NotaLinha({ nota, codigo }: { nota: ImovelNota; codigo: string }) {
  const { atualizar, remover } = useImovelNotaMutations(codigo);
  const confirm = useConfirm();
  const [editando, setEditando] = useState(false);
  const [draft, setDraft] = useState(nota.texto);
  const { dirty } = useUnsavedChanges({ texto: draft }, editando ? { texto: nota.texto } : undefined);
  const pendente = nota.id.startsWith("optimistic:");

  async function apagar() {
    const ok = await confirm({
      title: "Remover esta nota?",
      description: "A nota some do imóvel para toda a equipe. Não dá para desfazer.",
      confirmLabel: "Remover",
      tone: "danger",
    });
    if (ok) remover.mutate({ id: nota.id });
  }

  if (editando) {
    return (
      <li className="space-y-2" data-testid="imovel-nota-editando">
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={MAX}
          rows={3}
          disabled={atualizar.isPending}
          aria-label="Editar nota"
          data-testid="imovel-nota-edit-texto"
        />
        {atualizar.error && (
          <p className="text-sm text-destructive" role="alert" data-testid="imovel-nota-edit-erro">
            {atualizar.error.message}
          </p>
        )}
        <UnsavedChangesNotice dirty={dirty} data-testid="imovel-nota-nao-salva" />
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            disabled={atualizar.isPending || !draft.trim()}
            data-testid="imovel-nota-edit-salvar"
            onClick={() =>
              atualizar.mutate({ id: nota.id, texto: draft }, { onSuccess: () => setEditando(false) })
            }
          >
            {atualizar.isPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
            Salvar
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={atualizar.isPending}
            onClick={() => {
              atualizar.reset();
              setDraft(nota.texto);
              setEditando(false);
            }}
          >
            Cancelar
          </Button>
        </div>
      </li>
    );
  }

  return (
    <li className="space-y-1" data-testid="imovel-nota" aria-busy={pendente}>
      <p className="whitespace-pre-wrap text-sm">{nota.texto}</p>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{quando(nota)}</span>
        {!pendente && (
          <span className="flex gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Editar nota"
              data-testid="imovel-nota-editar"
              onClick={() => {
                setDraft(nota.texto);
                setEditando(true);
              }}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Remover nota"
              data-testid="imovel-nota-remover"
              disabled={remover.isPending}
              onClick={apagar}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </span>
        )}
      </div>
      {remover.error && (
        <p className="text-sm text-destructive" role="alert" data-testid="imovel-nota-remover-erro">
          {remover.error.message}
        </p>
      )}
    </li>
  );
}

export function ImovelNotasCard({ codigo }: { codigo: string }) {
  const query = useImovelNotas(codigo);
  const { criar } = useImovelNotaMutations(codigo);
  const [texto, setTexto] = useState("");
  const { dirty } = useUnsavedChanges({ texto }, query.data ? { texto: "" } : undefined);

  const showSkeleton = query.isPending && !query.data;
  const itens = query.data ?? [];

  return (
    <Card data-testid="imovel-notas">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <StickyNote className="h-4 w-4" />
          Notas internas
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Anotações nossas sobre o imóvel. Não existem no Vista e a sincronização nunca as altera.
        </p>

        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!texto.trim()) return;
            criar.mutate({ texto }, { onSuccess: () => setTexto("") });
          }}
        >
          <Textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            maxLength={MAX}
            rows={2}
            placeholder="Ex.: chave com o porteiro; proprietário só atende à tarde"
            disabled={criar.isPending}
            aria-label="Nova nota"
            data-testid="imovel-nota-novo-texto"
          />
          {criar.error && (
            <p className="text-sm text-destructive" role="alert" data-testid="imovel-nota-novo-erro">
              {criar.error.message}
            </p>
          )}
          <UnsavedChangesNotice dirty={dirty} data-testid="imovel-nota-novo-nao-salva" />
          <Button type="submit" size="sm" disabled={criar.isPending || !texto.trim()} data-testid="imovel-nota-adicionar">
            {criar.isPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
            Adicionar nota
          </Button>
        </form>

        {showSkeleton ? (
          <div data-testid="imovel-notas-skeleton">
            <Skeleton className="h-12 w-full" />
          </div>
        ) : query.isError && !query.data ? (
          <QueryErrorState
            query={query}
            variant="inline"
            title="Não foi possível carregar as notas."
            data-testid="imovel-notas-erro"
          />
        ) : itens.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="imovel-notas-vazio">
            Nenhuma nota ainda.
          </p>
        ) : (
          <ul className="divide-y [&>li]:py-3 first:[&>li]:pt-0" data-testid="imovel-notas-lista">
            {itens.map((n) => (
              <NotaLinha key={n.id} nota={n} codigo={codigo} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
