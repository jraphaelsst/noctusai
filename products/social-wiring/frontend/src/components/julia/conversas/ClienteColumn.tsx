/**
 * Right column "Cliente" of the open conversation: Perfil · Visitas solicitadas
 * · Etiquetas [+] · Notas internas [+ Nova anotação] · Interações.
 * Reads the history route (A7) for perfil/visitas/interações; notes + tags have
 * their own mutations. Server enforces access; a 403 shows the no-access state.
 */
import { useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { useConfirm } from "@noctusai/lib/components";

import { CreditoStatusChip } from "@/components/julia/credito/StatusChip";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  codigoHttp, mensagemErroConversas, useHistorico, useNotaMutations, useNotas, usePatchContato,
  type Conversa, type Etiqueta,
} from "@/hooks/useJuliaConversas";
import { EtiquetaPicker } from "./EtiquetaPicker";
import { InteracoesLista, fmtData } from "./InteracoesLista";

function Secao({ titulo, acao, children }: { titulo: string; acao?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="space-y-2 border-b px-3 py-3 last:border-b-0" aria-label={titulo}>
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{titulo}</h3>
        {acao}
      </div>
      {children}
    </section>
  );
}

function Notas({ contatoId }: { contatoId: string }) {
  const confirm = useConfirm();
  const { data: notas, isPending, isError } = useNotas(contatoId);
  const m = useNotaMutations(contatoId);
  const [novo, setNovo] = useState<string | null>(null);
  const [editando, setEditando] = useState<{ id: string; texto: string } | null>(null);
  const falha = (msg: string) => (e: unknown) => toast.error(mensagemErroConversas(e, msg));

  function salvarNova() {
    if (!novo?.trim()) return;
    m.criar.mutate({ texto: novo.trim() }, { onSuccess: () => setNovo(null), onError: falha("Não foi possível salvar a nota.") });
  }
  function salvarEdicao() {
    if (!editando?.texto.trim()) return;
    m.editar.mutate({ id: editando.id, texto: editando.texto.trim() },
      { onSuccess: () => setEditando(null), onError: falha("Não foi possível editar a nota.") });
  }
  async function remover(id: string) {
    if (!(await confirm({ title: "Excluir esta anotação?", confirmLabel: "Excluir", tone: "danger" }))) return;
    m.remover.mutate(id, { onError: falha("Não foi possível excluir a nota.") });
  }

  return (
    <Secao titulo="Notas internas" acao={
      <Button variant="ghost" size="sm" className="h-6 gap-1 px-1 text-xs" onClick={() => setNovo("")} data-testid="nota-nova">
        <Plus className="h-3 w-3" /> Nova anotação
      </Button>}>
      {novo !== null && (
        <div className="space-y-1">
          <Textarea value={novo} maxLength={4000} onChange={(e) => setNovo(e.target.value)} aria-label="Nova anotação" />
          <div className="flex justify-end gap-1">
            <Button variant="outline" size="sm" onClick={() => setNovo(null)}>Cancelar</Button>
            <Button size="sm" disabled={!novo.trim() || m.criar.isPending} onClick={salvarNova} data-testid="nota-salvar">Salvar</Button>
          </div>
        </div>
      )}
      {isPending && !notas ? (
        <div className="h-10 animate-pulse rounded bg-muted" data-testid="notas-skeleton" />
      ) : isError && !notas ? (
        <p className="text-xs text-destructive">Erro ao carregar as notas.</p>
      ) : (notas ?? []).length === 0 && novo === null ? (
        <p className="text-xs text-muted-foreground">Nenhuma anotação.</p>
      ) : (
        <ul className="space-y-2">
          {(notas ?? []).map((n) => (
            <li key={n.id} className="rounded-md bg-muted/50 p-2 text-xs" data-testid="nota-item">
              {editando?.id === n.id ? (
                <div className="space-y-1">
                  <Textarea value={editando.texto} maxLength={4000} onChange={(e) => setEditando({ id: n.id, texto: e.target.value })} aria-label="Editar anotação" />
                  <div className="flex justify-end gap-1">
                    <Button variant="outline" size="sm" onClick={() => setEditando(null)}>Cancelar</Button>
                    <Button size="sm" onClick={salvarEdicao}>Salvar</Button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="whitespace-pre-wrap">{n.texto}</p>
                  <div className="mt-1 flex items-center justify-between text-muted-foreground">
                    <span>{n.autor_nome ?? "—"} · {fmtData(n.created_at)}</span>
                    <span className="flex">
                      <Button variant="ghost" size="icon" className="h-5 w-5" aria-label="Editar anotação" onClick={() => setEditando({ id: n.id, texto: n.texto })}><Pencil className="h-3 w-3" /></Button>
                      <Button variant="ghost" size="icon" className="h-5 w-5" aria-label="Excluir anotação" onClick={() => void remover(n.id)}><Trash2 className="h-3 w-3" /></Button>
                    </span>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

interface Props {
  contatoId: string;
  nome: string;
  /** Tags on the conversation row (the list is the freshest source). */
  etiquetas: Etiqueta[];
  credito?: Conversa["credito"];
}

export function ClienteColumn({ contatoId, nome, etiquetas, credito = null }: Props) {
  const { data: hist, isPending, isError, error } = useHistorico(contatoId);
  const patch = usePatchContato();
  const setTags = (ids: string[]) =>
    patch.mutate({ id: contatoId, etiquetas: ids }, {
      onError: (e) => toast.error(mensagemErroConversas(e, "Não foi possível atualizar as etiquetas.")),
    });

  const semAcesso = codigoHttp(error) === 403;
  const contato = hist?.contato;

  return (
    <aside className="flex w-80 flex-shrink-0 flex-col overflow-y-auto border-l" data-testid="cliente-column" aria-label="Cliente">
      <h2 className="border-b px-3 py-2 text-sm font-semibold">Cliente</h2>

      <Secao titulo="Perfil">
        {isPending && !hist ? (
          <div className="h-16 animate-pulse rounded bg-muted" data-testid="perfil-skeleton" />
        ) : semAcesso ? (
          <p className="text-xs text-muted-foreground">Você não tem acesso aos dados deste cliente.</p>
        ) : isError && !hist ? (
          <p className="text-xs text-destructive">Erro ao carregar o perfil.</p>
        ) : (
          <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-xs">
            <dt className="text-muted-foreground">Nome</dt><dd>{contato?.nome ?? nome}</dd>
            {credito && (<><dt className="text-muted-foreground">Crédito</dt><dd><CreditoStatusChip status={credito.status} /></dd></>)}
            <dt className="text-muted-foreground">Telefone</dt><dd>{contato?.telefone ?? "—"}</dd>
            <dt className="text-muted-foreground">E-mail</dt><dd>{contato?.email ?? "—"}</dd>
            <dt className="text-muted-foreground">Operação</dt><dd>{contato?.operacao ?? "—"}</dd>
            <dt className="text-muted-foreground">Responsável</dt><dd>{contato?.responsavel_nome ?? "Sem responsável"}</dd>
          </dl>
        )}
      </Secao>

      <Secao titulo="Visitas solicitadas">
        {isError && !hist ? (
          <p className="text-xs text-muted-foreground">Indisponível — o histórico não carregou.</p>
        ) : (contato?.visitas ?? []).length === 0 ? (
          <p className="text-xs text-muted-foreground">Nenhuma visita solicitada.</p>
        ) : (
          <ul className="space-y-1 text-xs">
            {(contato?.visitas ?? []).map((v) => (
              <li key={v.id}>{fmtData(v.inicio)} · {v.codigo_imovel ?? "imóvel"} · {v.status}</li>
            ))}
          </ul>
        )}
      </Secao>

      <Secao titulo="Etiquetas" acao={
        <EtiquetaPicker excluir={etiquetas.map((e) => e.id)}
          onSelect={(e) => { if (typeof e !== "string") setTags([...etiquetas.map((t) => t.id), e.id]); }}
          trigger={<Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Adicionar etiqueta" data-testid="etiqueta-add"><Plus className="h-3 w-3" /></Button>} />}>
        {etiquetas.length === 0 ? (
          <p className="text-xs text-muted-foreground">Sem etiquetas.</p>
        ) : (
          <div className="flex flex-wrap gap-1">
            {etiquetas.map((e) => (
              <span key={e.id} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary" data-testid="etiqueta-chip">
                {e.nome}
                <button type="button" aria-label={`Remover etiqueta ${e.nome}`} onClick={() => setTags(etiquetas.filter((t) => t.id !== e.id).map((t) => t.id))}>
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </Secao>

      <Notas contatoId={contatoId} />

      <Secao titulo="Interações">
        {isPending && !hist ? (
          <div className="h-16 animate-pulse rounded bg-muted" />
        ) : (
          <InteracoesLista interacoes={hist?.interacoes ?? []} />
        )}
      </Secao>
    </aside>
  );
}
