/**
 * RevisaoCpfGrupoCard — one CPF review-queue group: every candidate sharing
 * the normalized CPF, masked (`maskCpf`, brief 2026-09-28's own example:
 * `***.***.*89-01`), which deals each one is on and in what role, and the
 * two operator actions (`pessoa-mesma-cpf-multideal-CONTRACT.md` §1).
 *
 * UNLIKE `RevisaoGrupoCard` (the identity axis), this axis's merge REQUIRES
 * an explicit survivor (§1: no default is named), so this card offers a
 * radio pick per candidate before "Mesma pessoa — unificar" is enabled, and
 * gates the action behind `CpfMergeConfirmDialog` — the brief's own ask
 * ("say plainly what merge does") rather than firing on click like the
 * identity axis still does.
 *
 * Each candidate's negociações are NOT fetched eagerly — §2's read is a
 * per-cliente call with no batched shape for a whole group, so firing one
 * per candidate on every page load would be an N+1 the brief explicitly
 * asked to avoid ("fetch lazily on expand"). `CandidatoNegociacoesLazy`
 * below mounts (and therefore queries) only once its row's "Ver
 * negociações" toggle is open.
 */
import { useState } from "react";
import { ChevronDown, ChevronUp, GitMerge, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import { maskCpf, useNegociacoesDoCliente } from "@/hooks/useClientes";
import type { RevisaoCpfCandidato, RevisaoCpfGrupo } from "@/hooks/useClientesRevisao";
import { CpfMergeConfirmDialog } from "@/components/clientes/CpfMergeConfirmDialog";

/** pt-BR label for a deal's role — mirrors `rotuloDePapel`'s "one place"
 *  convention without importing `ClienteCardDialog` (a presentational
 *  file this review queue has no other reason to depend on). `titular` is
 *  the one value that axis never emits (§2's synthetic buyer-side row). */
const PAPEL_LABEL: Record<string, string> = {
  titular: "Titular",
  comprador: "Comprador",
  conjuge: "Cônjuge",
  fiador: "Fiador",
  procurador: "Procurador",
  proprietario: "Proprietário",
  inventariante: "Inventariante",
  antigo_proprietario: "Antigo proprietário",
  outro: "Outro",
};

function rotuloPapel(papel: string): string {
  return PAPEL_LABEL[papel] ?? papel;
}

/** One candidate's deal list, mounted (and therefore fetched) ONLY while its
 *  row is expanded — see file header. */
function CandidatoNegociacoesLazy({ clienteId }: { clienteId: string }) {
  const query = useNegociacoesDoCliente(clienteId);
  const loading = query.isPending && !query.data;
  const refreshing = query.isFetching && !!query.data;

  if (loading) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> Carregando negociações…
      </p>
    );
  }
  if (query.isError) {
    return (
      <p className="text-xs text-destructive">Não foi possível carregar as negociações.</p>
    );
  }
  const negociacoes = query.data?.negociacoes ?? [];
  if (negociacoes.length === 0) {
    return <p className="text-xs text-muted-foreground">Nenhuma negociação encontrada.</p>;
  }
  return (
    <ul className="space-y-1" data-testid="cpf-candidato-negociacoes">
      {negociacoes.map((n) => (
        <li key={n.atendimento_id} className="flex flex-wrap items-center gap-1.5 text-xs">
          {refreshing && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
          <span className="font-medium">{n.titulo || "Negociação sem título"}</span>
          <span className="text-muted-foreground">
            · {rotuloPapel(n.papel)} ({n.lado === "comprador" ? "compra" : "venda"})
            {n.etapa_label ? ` · ${n.etapa_label}` : ""}
            {n.imovel_codigo ? ` · imóvel ${n.imovel_codigo}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function CandidatoRow({
  candidato,
  selecionado,
  onSelecionar,
}: {
  candidato: RevisaoCpfCandidato;
  selecionado: boolean;
  onSelecionar: () => void;
}) {
  const [expandido, setExpandido] = useState(false);

  return (
    <li
      data-testid="cpf-candidato"
      className="rounded-md border border-border bg-muted/30 p-2.5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex min-w-0 items-center gap-2 text-sm">
          <input
            type="radio"
            className="h-4 w-4 shrink-0"
            checked={selecionado}
            onChange={onSelecionar}
            data-testid="cpf-candidato-sobrevivente-radio"
          />
          <span className="min-w-0">
            <span className="block truncate font-medium">
              {candidato.nome || "Sem nome"}
            </span>
            <span className="block font-mono text-xs text-muted-foreground">
              {maskCpf(candidato.cpf)}
            </span>
          </span>
        </label>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1 px-2 text-xs"
          onClick={() => setExpandido((v) => !v)}
          data-testid="cpf-candidato-ver-negociacoes"
        >
          Ver negociações
          {expandido ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </Button>
      </div>
      {expandido && (
        <div className="mt-2 border-t pt-2">
          <CandidatoNegociacoesLazy clienteId={candidato.id} />
        </div>
      )}
    </li>
  );
}

export interface RevisaoCpfGrupoCardProps {
  grupo: RevisaoCpfGrupo;
  onMerge: (grupoId: string, sobreviventeId: string) => void;
  onManterSeparados: (grupoId: string) => void;
  merging: boolean;
  rejecting: boolean;
}

export function RevisaoCpfGrupoCard({
  grupo,
  onMerge,
  onManterSeparados,
  merging,
  rejecting,
}: RevisaoCpfGrupoCardProps) {
  const [sobreviventeId, setSobreviventeId] = useState<string>(
    grupo.candidatos[0]?.id ?? "",
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const busy = merging || rejecting;

  const sobrevivente = grupo.candidatos.find((c) => c.id === sobreviventeId);
  const quantidadeAbsorvidos = Math.max(0, grupo.candidatos.length - 1);

  return (
    <Card data-testid="revisao-cpf-grupo-card" data-motivo="CPF">
      <CardContent className="space-y-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Badge
            variant="outline"
            data-testid="cpf-motivo-badge"
            className="border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400"
          >
            CPF · Mesmo CPF em cadastros diferentes
          </Badge>
          <span className="text-xs text-muted-foreground">
            {grupo.candidatos.length} candidatos
          </span>
        </div>

        <p className="text-xs text-muted-foreground">
          CPF compartilhado:{" "}
          <span className="font-mono text-foreground">{maskCpf(grupo.chave_canonica)}</span>
        </p>

        <ul className="space-y-2">
          {grupo.candidatos.map((c) => (
            <CandidatoRow
              key={c.id}
              candidato={c}
              selecionado={c.id === sobreviventeId}
              onSelecionar={() => setSobreviventeId(c.id)}
            />
          ))}
        </ul>

        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            size="sm"
            disabled={busy || !sobreviventeId}
            onClick={() => setConfirmOpen(true)}
            data-testid="cpf-mesclar-btn"
          >
            <GitMerge className="mr-2 h-4 w-4" />
            {merging ? "Unificando…" : "Mesma pessoa — unificar"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => onManterSeparados(grupo.chave_canonica)}
            data-testid="cpf-manter-separados-btn"
          >
            {rejecting ? "Salvando…" : "Manter separados"}
          </Button>
        </div>
      </CardContent>

      <CpfMergeConfirmDialog
        open={confirmOpen}
        pending={merging}
        sobreviventeNome={sobrevivente?.nome || "Este cadastro"}
        quantidadeAbsorvidos={quantidadeAbsorvidos}
        onOpenChange={setConfirmOpen}
        onConfirm={() => {
          onMerge(grupo.chave_canonica, sobreviventeId);
          setConfirmOpen(false);
        }}
      />
    </Card>
  );
}
