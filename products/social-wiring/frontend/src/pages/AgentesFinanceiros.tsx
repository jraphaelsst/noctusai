/**
 * Agentes Financeiros — the org's registry of financing banks (migration 100).
 *
 * The management surface behind the dropdown on the card's Financiamento tab.
 * An agency works with the same four or five banks over and over, each with a
 * manager, a branch and a phone number the operator reaches for on every deal;
 * typed per deal, "Caixa Econômica Federal" becomes three spellings inside a
 * month and "how many deals went through Caixa this quarter" stops having an
 * answer.
 *
 * 🔴 RETIRE, NEVER DELETE — AND THE PAGE SAYS SO BEFORE THE CLICK.
 * `atendimento_financiamento.agente_financeiro_id` references this table with
 * `ON DELETE RESTRICT`, so deleting an agent any deal points at is refused by
 * the database. This page offers "Desativar" as the primary action and keeps
 * Excluir for agents nothing references — rather than letting a 409 be the
 * first anyone hears of the rule. When the server refuses anyway (a deal
 * created between render and click), its own message is surfaced verbatim:
 * only it knows how many atendimentos are involved.
 *
 * 🔴 INACTIVE AGENTS ARE LISTED, not hidden. This is the surface where one is
 * reactivated, and an agent you cannot see is an agent you cannot bring back.
 * The card's dropdown asks the same endpoint with `incluir_inativos=false`,
 * which is why that flag is a parameter and not a constant.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Ban, Loader2, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react";

import {
  AgenteFinanceiro,
  AgenteFinanceiroPatch,
  useAgentesFinanceiros,
  useAtualizarAgenteFinanceiro,
  useCriarAgenteFinanceiro,
  useRemoverAgenteFinanceiro,
} from "@/hooks/useAgentesFinanceiros";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@noctusai/seed/components/ui/table";
import { TableSkeleton } from "@noctusai/lib/design-system";

const VAZIO: AgenteFinanceiroPatch = {
  nome: "",
  codigo_banco: "",
  agencia: "",
  contato_nome: "",
  contato_email: "",
  contato_telefone: "",
  observacoes: "",
};

/** The server's own message wins. Its 409 names how many atendimentos block a
 *  delete and its duplicate-name error names the agent — both are things the
 *  operator can act on, and a blanket "erro ao salvar" reads as a network
 *  failure. */
function erroDoServidor(err: unknown, fallback: string): string {
  const msg = (err as { message?: string } | null)?.message;
  return msg && msg.trim() ? msg : fallback;
}

export default function AgentesFinanceiros() {
  // `true` — the management page sees retired agents; see the header.
  const query = useAgentesFinanceiros(true);
  const criar = useCriarAgenteFinanceiro();
  const atualizar = useAtualizarAgenteFinanceiro();
  const remover = useRemoverAgenteFinanceiro();

  const [aberto, setAberto] = useState(false);
  const [editando, setEditando] = useState<AgenteFinanceiro | null>(null);
  const [draft, setDraft] = useState<AgenteFinanceiroPatch>(VAZIO);

  const agentes = query.data ?? [];
  const salvando = criar.isPending || atualizar.isPending;

  function abrirNovo() {
    setEditando(null);
    setDraft(VAZIO);
    setAberto(true);
  }

  function abrirEdicao(a: AgenteFinanceiro) {
    setEditando(a);
    setDraft({
      nome: a.nome,
      codigo_banco: a.codigo_banco ?? "",
      agencia: a.agencia ?? "",
      contato_nome: a.contato_nome ?? "",
      contato_email: a.contato_email ?? "",
      contato_telefone: a.contato_telefone ?? "",
      observacoes: a.observacoes ?? "",
    });
    setAberto(true);
  }

  function campo(k: keyof AgenteFinanceiroPatch, v: string) {
    setDraft((d) => ({ ...d, [k]: v }));
  }

  function submit() {
    const nome = (draft.nome ?? "").trim();
    if (!nome) return;
    // Empty strings become null: a blank box means "not recorded", and storing
    // "" would make every "has a branch?" check answer yes.
    const payload: AgenteFinanceiroPatch = {
      nome,
      codigo_banco: (draft.codigo_banco ?? "").trim() || null,
      agencia: (draft.agencia ?? "").trim() || null,
      contato_nome: (draft.contato_nome ?? "").trim() || null,
      contato_email: (draft.contato_email ?? "").trim() || null,
      contato_telefone: (draft.contato_telefone ?? "").trim() || null,
      observacoes: (draft.observacoes ?? "").trim() || null,
    };

    const onError = (err: unknown) =>
      toast.error(erroDoServidor(err, "Não foi possível salvar o agente."));

    if (editando) {
      atualizar.mutate(
        { id: editando.id, patch: payload },
        { onSuccess: () => setAberto(false), onError },
      );
    } else {
      criar.mutate(payload, { onSuccess: () => setAberto(false), onError });
    }
  }

  function alternarAtivo(a: AgenteFinanceiro) {
    atualizar.mutate(
      { id: a.id, patch: { ativo: !a.ativo } },
      {
        onError: (err) =>
          toast.error(
            erroDoServidor(err, "Não foi possível alterar a situação."),
          ),
      },
    );
  }

  function excluir(a: AgenteFinanceiro) {
    remover.mutate(a.id, {
      onError: (err) =>
        toast.error(
          erroDoServidor(
            err,
            "Não foi possível excluir. Desative-o em vez de excluir.",
          ),
        ),
    });
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Agentes Financeiros
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Os bancos com que a imobiliária trabalha. Aparecem na aba
            Financiamento do card, para selecionar quem está financiando cada
            atendimento.
          </p>
        </div>
        <Button onClick={abrirNovo} data-testid="agente-novo-btn">
          <Plus className="mr-1.5 h-4 w-4" />
          Novo agente
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Cadastrados
            {agentes.length > 0 && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {agentes.length}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* 🔴 Two signals, never `isLoading`: a skeleton only while there is
              genuinely nothing yet, so a refetch after a save does not unmount
              rows that already exist.
              → KB § PATTERNS/frontend/lying-loading-state.md */}
          {query.isPending && agentes.length === 0 ? (
            <TableSkeleton rows={4} />
          ) : query.isError ? (
            /* An error branch, not a fall-through to the empty state — an
               empty list lying over a failed fetch is the exact bug that
               pattern names. */
            <p className="text-sm text-destructive" data-testid="agentes-erro">
              {erroDoServidor(query.error, "Não foi possível carregar os agentes.")}
            </p>
          ) : agentes.length === 0 ? (
            <p
              className="text-sm text-muted-foreground"
              data-testid="agentes-vazio"
            >
              Nenhum agente cadastrado ainda.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Código</TableHead>
                    <TableHead>Agência</TableHead>
                    <TableHead>Contato</TableHead>
                    <TableHead>Situação</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {agentes.map((a) => (
                    <TableRow
                      key={a.id}
                      data-testid={`agente-row-${a.id}`}
                      className={a.ativo ? undefined : "opacity-60"}
                    >
                      <TableCell className="font-medium">{a.nome}</TableCell>
                      <TableCell className="tabular-nums">
                        {a.codigo_banco ?? "—"}
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {a.agencia ?? "—"}
                      </TableCell>
                      <TableCell>
                        {a.contato_nome ? (
                          <span>
                            {a.contato_nome}
                            {a.contato_telefone ? (
                              <span className="block text-xs text-muted-foreground">
                                {a.contato_telefone}
                              </span>
                            ) : null}
                          </span>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant={a.ativo ? "default" : "secondary"}>
                          {a.ativo ? "Ativo" : "Inativo"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => abrirEdicao(a)}
                            data-testid={`agente-editar-${a.id}`}
                            aria-label={`Editar ${a.nome}`}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          {/* The PRIMARY retirement action — see the header.
                              Excluir stays available for agents nothing
                              references, and the server refuses the rest. */}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => alternarAtivo(a)}
                            data-testid={`agente-ativo-${a.id}`}
                            aria-label={
                              a.ativo
                                ? `Desativar ${a.nome}`
                                : `Reativar ${a.nome}`
                            }
                          >
                            {a.ativo ? (
                              <Ban className="h-4 w-4" />
                            ) : (
                              <RotateCcw className="h-4 w-4" />
                            )}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => excluir(a)}
                            disabled={remover.isPending}
                            data-testid={`agente-excluir-${a.id}`}
                            aria-label={`Excluir ${a.nome}`}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="max-w-lg" data-testid="agente-dialog">
          <DialogHeader>
            <DialogTitle>
              {editando ? "Editar agente" : "Novo agente financeiro"}
            </DialogTitle>
            <DialogDescription>
              Apenas o nome é obrigatório. O resto é o contato que a equipe
              procura na hora de acompanhar um financiamento.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="agente-nome">Nome</Label>
              <Input
                id="agente-nome"
                value={draft.nome ?? ""}
                onChange={(e) => campo("nome", e.target.value)}
                placeholder="Caixa Econômica Federal"
                autoFocus
                data-testid="agente-nome-input"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="agente-codigo">Código do banco</Label>
                <Input
                  id="agente-codigo"
                  value={draft.codigo_banco ?? ""}
                  onChange={(e) => campo("codigo_banco", e.target.value)}
                  placeholder="104"
                  data-testid="agente-codigo-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="agente-agencia">Agência</Label>
                <Input
                  id="agente-agencia"
                  value={draft.agencia ?? ""}
                  onChange={(e) => campo("agencia", e.target.value)}
                  placeholder="0001"
                  data-testid="agente-agencia-input"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="agente-contato">Contato</Label>
              <Input
                id="agente-contato"
                value={draft.contato_nome ?? ""}
                onChange={(e) => campo("contato_nome", e.target.value)}
                placeholder="Nome do gerente"
                data-testid="agente-contato-input"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="agente-email">E-mail</Label>
                <Input
                  id="agente-email"
                  value={draft.contato_email ?? ""}
                  onChange={(e) => campo("contato_email", e.target.value)}
                  data-testid="agente-email-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="agente-telefone">Telefone</Label>
                <Input
                  id="agente-telefone"
                  value={draft.contato_telefone ?? ""}
                  onChange={(e) => campo("contato_telefone", e.target.value)}
                  data-testid="agente-telefone-input"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="agente-obs">Observações</Label>
              <Textarea
                id="agente-obs"
                rows={2}
                value={draft.observacoes ?? ""}
                onChange={(e) => campo("observacoes", e.target.value)}
                data-testid="agente-obs-input"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setAberto(false)}>
              Cancelar
            </Button>
            <Button
              onClick={submit}
              disabled={!(draft.nome ?? "").trim() || salvando}
              data-testid="agente-salvar-btn"
            >
              {salvando && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {salvando ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
