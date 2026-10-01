/**
 * `<CertidoesPartesTab/>` — the card's "Certidões" tab, per party: every
 * comprador and vendedor (PF and PJ, plus derived EMP columns) as a
 * collapsible section, ALL COLLAPSED by default; expanded, each holds that
 * party's levantamento de certidões. Contract §1/§6.
 *
 * Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching &&
 * !!data` (indicator only) → KB § PATTERNS/frontend/lying-loading-state.md.
 */
import { useState } from "react";

import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TooltipProvider } from "@/components/ui/tooltip";
import { CertidoesPartePanel } from "@/components/CertidoesPartePanel";
import {
  useCertidoesPartes, useCriarLinhaPartes, useInvalidatePartes, useReemitirResultado,
  useRemoverLinhaPartes, useRenomearLinhaPartes, useSolicitarEmissao, useUploadNaCelula,
} from "@/hooks/useCertidoesPartes";
import type { CertidaoParte, CertidaoParteLinha } from "@/types/certidoesPartes";

import { ParteSecao } from "./ParteSecao";

export function CertidoesPartesTab(props: {
  clienteId: string;
  atendimentoId?: string | null;
}) {
  const { clienteId, atendimentoId } = props;
  const q = useCertidoesPartes(clienteId, atendimentoId);
  const emissao = useSolicitarEmissao(clienteId, atendimentoId);
  const reemitir = useReemitirResultado(clienteId);
  const upload = useUploadNaCelula(clienteId, atendimentoId);
  const criar = useCriarLinhaPartes(clienteId);
  const renomear = useRenomearLinhaPartes(clienteId);
  const remover = useRemoverLinhaPartes(clienteId);
  const invalidar = useInvalidatePartes(clienteId);

  const [detalhes, setDetalhes] = useState<CertidaoParte | null>(null);
  const [adicionando, setAdicionando] = useState(false);
  const [novoNome, setNovoNome] = useState("");
  const [renomeando, setRenomeando] = useState<CertidaoParteLinha | null>(null);
  const [nomeRen, setNomeRen] = useState("");
  const [removendo, setRemovendo] = useState<CertidaoParteLinha | null>(null);

  const data = q.data;
  const showSkeleton = q.isPending && !data;
  const isRefreshing = q.isFetching && !!data;

  if (showSkeleton) {
    return (
      <div className="space-y-2" data-testid="certidoes-partes-skeleton">
        <div className="h-12 animate-pulse rounded bg-muted" />
        <div className="h-12 animate-pulse rounded bg-muted" />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="space-y-2 text-sm" data-testid="certidoes-partes-error">
        <p className="text-destructive">Não foi possível carregar as certidões das partes.</p>
        <Button size="sm" variant="outline" onClick={() => void q.refetch()}>Tentar novamente</Button>
      </div>
    );
  }
  if (data.partes.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="certidoes-partes-empty">
        {data.atendimento_id
          ? "Nenhum comprador ou vendedor vinculado a este atendimento ainda."
          : "Selecione um atendimento para ver as certidões das partes."}
      </p>
    );
  }

  const fecharAdicionar = () => { setAdicionando(false); setNovoNome(""); };

  return (
    <div className="space-y-3" data-testid="certidoes-partes">
      {q.isError && (
        <p className="text-xs text-destructive" data-testid="certidoes-partes-error-banner">
          Falha ao atualizar — exibindo os últimos dados carregados.
        </p>
      )}
      {isRefreshing && (
        <p className="text-xs text-muted-foreground" data-testid="certidoes-partes-refreshing">Atualizando…</p>
      )}
      <TooltipProvider delayDuration={200}>
        {data.partes.map((parte) => (
          <ParteSecao
            key={parte.chave}
            parte={parte}
            linhas={data.linhas}
            dataReferencia={data.data_referencia}
            emissaoPendente={emissao.isPending}
            onSolicitar={(i) => emissao.mutate(i)}
            onReemitir={(id) => reemitir.mutate(id)}
            onUpload={(i) => upload.mutate(i)}
            onDetalhes={setDetalhes}
            onAdicionar={() => setAdicionando(true)}
            onRenomear={(l) => { setRenomeando(l); setNomeRen(l.rotulo.replace(/^Outras: /, "")); }}
            onRemover={setRemovendo}
          />
        ))}
      </TooltipProvider>

      <Dialog open={!!detalhes} onOpenChange={(o) => { if (!o) { setDetalhes(null); void invalidar(); } }}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>Certidões — {detalhes?.nome}</DialogTitle>
            <DialogDescription>Registre, envie ou corrija as certidões desta parte.</DialogDescription>
          </DialogHeader>
          {detalhes &&
            (detalhes.kind === "empresa" ? (
              <CertidoesPartePanel empresaId={detalhes.empresa_id as string} nomeParte={detalhes.nome} documento={detalhes.documento ?? undefined} />
            ) : detalhes.parte_id ? (
              <CertidoesPartePanel atendimentoParteId={detalhes.parte_id} nomeParte={detalhes.nome} documento={detalhes.documento ?? undefined} />
            ) : (
              <CertidoesPartePanel clienteId={detalhes.cliente_id as string} nomeParte={detalhes.nome} documento={detalhes.documento ?? undefined} />
            ))}
        </DialogContent>
      </Dialog>

      <Dialog open={adicionando} onOpenChange={(o) => !o && fecharAdicionar()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adicionar certidão</DialogTitle>
            <DialogDescription>Cria uma nova linha aplicável a todas as partes deste atendimento.</DialogDescription>
          </DialogHeader>
          <Label htmlFor="certidoes-partes-novo-nome">Nome da certidão</Label>
          <Input id="certidoes-partes-novo-nome" value={novoNome} onChange={(e) => setNovoNome(e.target.value)} placeholder="Ex.: Consulta Municipal" data-testid="certidoes-partes-novo-nome-input" />
          <DialogFooter>
            <Button disabled={!novoNome.trim() || criar.isPending} data-testid="certidoes-partes-adicionar-confirmar"
              onClick={() => criar.mutate(novoNome.trim(), { onSuccess: fecharAdicionar })}>
              Adicionar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!renomeando} onOpenChange={(o) => !o && setRenomeando(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Renomear certidão</DialogTitle></DialogHeader>
          <Label htmlFor="certidoes-partes-ren-nome">Nome da certidão</Label>
          <Input id="certidoes-partes-ren-nome" value={nomeRen} onChange={(e) => setNomeRen(e.target.value)} />
          <DialogFooter>
            <Button disabled={!nomeRen.trim() || renomear.isPending}
              onClick={() => renomeando && renomear.mutate({ linhaId: renomeando.id as string, nome: nomeRen.trim() }, { onSuccess: () => setRenomeando(null) })}>
              Salvar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!removendo} onOpenChange={(o) => !o && setRemovendo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover certidão</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja remover a linha "{removendo?.rotulo}"? Os resultados já registrados NÃO serão apagados.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive hover:bg-destructive/90"
              onClick={() => removendo && remover.mutate(removendo.id as string, { onSuccess: () => setRemovendo(null) })}>
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
