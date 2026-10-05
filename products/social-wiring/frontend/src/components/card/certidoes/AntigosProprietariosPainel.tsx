/**
 * Header + controls of the Certidões tab's "Antigos proprietários" subtab
 * (antigos-proprietarios-CONTRACT.md §2–§5). The party ROWS are rendered by
 * the tab itself through the same `ParteSecao` as sellers (reuse, no fork) and
 * handed in as `children`.
 *
 * - On mount: `POST …/sincronizar` once (the idempotent backstop, §3); a
 *   refused/failed emission (`emissoes[]` with `nao_iniciada`) is shown, never
 *   swallowed.
 * - Dispensar / Reativar: admin only (UI convenience; the server's 403 is the
 *   gate and is rendered as such).
 * Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Loader2, Plus } from "lucide-react";
import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext } from "@noctusai/lib";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useAdicionarAntigo, useAntigosProprietarios, useDispensaAntigos, useSincronizarAntigos,
} from "@/hooks/useCertidoesPartes";
import type { AntigosEmissao, AntigosEstado, AntigosMotivo } from "@/types/certidoesPartes";

export const MOTIVO_MIN = 3;
export const MOTIVO_MAX = 500;

const MOTIVO_TEXTO: Record<AntigosMotivo, string> = {
  transferencia_menos_de_5_anos: "A última transferência do imóvel tem menos de 5 anos.",
  transferencia_5_anos_ou_mais: "A última transferência do imóvel tem 5 anos ou mais.",
  sem_transferencia_registrada: "A matrícula não registra transferência.",
  ultima_transferencia_desconhecida: "Não foi possível identificar a data da última transferência.",
  sem_imovel: "Este atendimento ainda não tem imóvel vinculado.",
};

const CODIGO_TEXTO: Record<string, string> = {
  DOCUMENTO_AUSENTE: "documento (CPF/CNPJ) ausente",
  CREDENCIAIS_AUSENTES: "credenciais de emissão ausentes",
};

const statusDe = (e: unknown): number | null =>
  typeof e === "object" && e !== null && typeof (e as { status?: unknown }).status === "number"
    ? (e as { status: number }).status
    : null;
const msgDe = (e: unknown) => (e instanceof Error ? e.message : "Tente novamente.");

function emissoesComProblema(emissoes: AntigosEmissao[] | undefined) {
  return (emissoes ?? []).filter((e) => e.status === "nao_iniciada");
}

export function AntigosProprietariosPainel(props: {
  clienteId: string;
  atendimentoId?: string | null;
  /** The antigo rows, rendered by the tab with the shared `ParteSecao`. */
  children: ReactNode;
}) {
  const { clienteId, atendimentoId, children } = props;
  const q = useAntigosProprietarios(clienteId, atendimentoId);
  const sincronizar = useSincronizarAntigos(clienteId, atendimentoId);
  const dispensa = useDispensaAntigos(clienteId, atendimentoId);
  const adicionar = useAdicionarAntigo(clienteId, atendimentoId);

  const { user } = useAuthStore();
  const sso = resolveSSOContext(user?.user_metadata);
  const isAdmin = sso.isProductAdmin || sso.org.role === "owner" || sso.org.role === "admin";

  // Backstop sync, once per opening of the subtab (re-keyed by the deal).
  const sincronizouPara = useRef<string | null>(null);
  const chaveSync = `${clienteId}:${atendimentoId ?? ""}`;
  useEffect(() => {
    if (sincronizouPara.current === chaveSync) return;
    sincronizouPara.current = chaveSync;
    sincronizar.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chaveSync]);

  const [dispensando, setDispensando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [adicionando, setAdicionando] = useState(false);
  const [tipoNovo, setTipoNovo] = useState<"pf" | "pj">("pf");
  const [nomeNovo, setNomeNovo] = useState("");
  const [docNovo, setDocNovo] = useState("");

  const data: AntigosEstado | undefined = q.data;
  const showSkeleton = q.isPending && !data;
  const isRefreshing = q.isFetching && !!data;

  const dispensaForbidden = statusDe(dispensa.error) === 403;
  const problemas = emissoesComProblema(sincronizar.data?.emissoes);

  const motivoOk = motivo.trim().length >= MOTIVO_MIN && motivo.trim().length <= MOTIVO_MAX;
  const fecharDispensa = () => { setDispensando(false); setMotivo(""); dispensa.reset(); };
  const fecharAdicionar = () => {
    setAdicionando(false); setNomeNovo(""); setDocNovo(""); setTipoNovo("pf"); adicionar.reset();
  };

  let cabecalho: ReactNode;
  if (showSkeleton) {
    cabecalho = <div className="h-16 animate-pulse rounded bg-muted" data-testid="antigos-skeleton" />;
  } else if (!data) {
    cabecalho = (
      <div className="space-y-2 text-sm" data-testid="antigos-error">
        <p className="text-destructive">Não foi possível carregar o estado dos antigos proprietários.</p>
        <Button size="sm" variant="outline" onClick={() => void q.refetch()}>Tentar novamente</Button>
      </div>
    );
  } else {
    const naoExigido = data.exigido === false || (data.exigido === null && data.dispensado === null && data.motivo === "sem_imovel");
    cabecalho = (
      <div className="space-y-2 rounded border p-3 text-sm" data-testid="antigos-header">
        {isRefreshing && <p className="text-xs text-muted-foreground" data-testid="antigos-refreshing">Atualizando…</p>}
        <p data-testid="antigos-estado" className="font-medium">
          {data.dispensado
            ? "Dispensado neste negócio"
            : data.exigido === true
              ? "Certidões dos antigos proprietários exigidas"
              : data.exigido === false
                ? "Certidões dos antigos proprietários não exigidas"
                : "Exigência indeterminada"}
        </p>
        {data.motivo && (
          <p className="text-xs text-muted-foreground" data-testid="antigos-motivo">
            {MOTIVO_TEXTO[data.motivo]}
            {data.ultima_transferencia?.data_registro ? ` Registro em ${data.ultima_transferencia.data_registro}.` : ""}
          </p>
        )}
        {data.transmitentes.length > 0 && (
          <div data-testid="antigos-transmitentes">
            <p className="text-xs font-medium">Transmitentes na matrícula</p>
            <ul className="list-inside list-disc text-xs text-muted-foreground">
              {data.transmitentes.map((t, i) => (
                <li key={`${t.nome}-${i}`}>
                  {t.nome} {t.documento_mascarado ? `(${t.documento_mascarado})` : ""} — {t.tipo_pessoa}
                  {t.ja_no_card ? " · já no card" : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
        {data.dispensado && (
          <p className="text-xs" data-testid="antigos-dispensado">
            Dispensado por {data.dispensado.por.nome ?? "administrador"} em {data.dispensado.em.slice(0, 10)}: {data.dispensado.motivo}
          </p>
        )}
        {data.sincronizacao_pendente > 0 && (
          <p className="text-xs text-amber-700" data-testid="antigos-pendentes">
            {data.sincronizacao_pendente} transmitente(s) da matrícula ainda não sincronizado(s) com o card.
          </p>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          <Button size="sm" variant="outline" onClick={() => setAdicionando(true)} data-testid="antigos-adicionar">
            <Plus className="mr-1 h-4 w-4" />Adicionar antigo proprietário
          </Button>
          <Button size="sm" variant="outline" disabled={sincronizar.isPending} onClick={() => sincronizar.mutate()} data-testid="antigos-sincronizar">
            {sincronizar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}Sincronizar com a matrícula
          </Button>
          {isAdmin && (data.dispensado ? (
            <Button size="sm" variant="outline" disabled={dispensa.isPending} data-testid="antigos-reativar"
              onClick={() => dispensa.mutate(null)}>
              Reativar exigência
            </Button>
          ) : (
            <Button size="sm" variant="outline" onClick={() => setDispensando(true)} data-testid="antigos-dispensar">
              Dispensar
            </Button>
          ))}
        </div>
        {dispensa.isError && !dispensando && (
          <p className="text-xs text-destructive" data-testid={dispensaForbidden ? "antigos-dispensa-403" : "antigos-dispensa-erro"}>
            {dispensaForbidden ? "Sem permissão: apenas administradores podem dispensar ou reativar." : msgDe(dispensa.error)}
          </p>
        )}
        {naoExigido && (
          <p className="text-xs text-muted-foreground" data-testid="antigos-nao-exigido">
            Nenhuma certidão de antigo proprietário é necessária neste negócio
            {data.motivo === "transferencia_5_anos_ou_mais" ? " (compra há 5 anos ou mais)" : ""}. Se precisar, adicione manualmente.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="antigos-painel">
      {cabecalho}
      {sincronizar.isError && (
        <p className="text-xs text-destructive" data-testid="antigos-sync-erro">
          Falha ao sincronizar com a matrícula: {msgDe(sincronizar.error)}
        </p>
      )}
      {problemas.length > 0 && (
        <ul className="space-y-1 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900" data-testid="antigos-emissoes-problema">
          {problemas.map((e) => (
            <li key={e.parte_id}>
              Emissão automática não iniciada para {sincronizar.data?.criados.find((c) => c.parte_id === e.parte_id)?.nome ?? "um antigo proprietário"}
              {e.codigo ? `: ${CODIGO_TEXTO[e.codigo] ?? e.codigo}` : ""}. Use o botão de emissão da linha.
            </li>
          ))}
        </ul>
      )}
      {children}

      <Dialog open={dispensando} onOpenChange={(o) => !o && fecharDispensa()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Dispensar antigos proprietários</DialogTitle>
            <DialogDescription>
              Dispensa a exigência apenas neste negócio. Informe o motivo ({MOTIVO_MIN} a {MOTIVO_MAX} caracteres).
            </DialogDescription>
          </DialogHeader>
          <Label htmlFor="antigos-motivo-input">Motivo</Label>
          <Textarea id="antigos-motivo-input" value={motivo} maxLength={MOTIVO_MAX} onChange={(e) => setMotivo(e.target.value)} data-testid="antigos-motivo-input" />
          {dispensa.isError && (
            <p className="text-xs text-destructive" data-testid={dispensaForbidden ? "antigos-dispensa-403" : "antigos-dispensa-erro"}>
              {dispensaForbidden ? "Sem permissão: apenas administradores podem dispensar ou reativar." : msgDe(dispensa.error)}
            </p>
          )}
          <DialogFooter>
            <Button disabled={!motivoOk || dispensa.isPending} data-testid="antigos-dispensar-confirmar"
              onClick={() => dispensa.mutate({ motivo: motivo.trim() }, { onSuccess: fecharDispensa })}>
              Dispensar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={adicionando} onOpenChange={(o) => !o && fecharAdicionar()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adicionar antigo proprietário</DialogTitle>
            <DialogDescription>Para quando a matrícula não nomeia o proprietário anterior.</DialogDescription>
          </DialogHeader>
          <div className="flex gap-2">
            <Button size="sm" variant={tipoNovo === "pf" ? "default" : "outline"} onClick={() => setTipoNovo("pf")}>Pessoa física</Button>
            <Button size="sm" variant={tipoNovo === "pj" ? "default" : "outline"} onClick={() => setTipoNovo("pj")} data-testid="antigos-tipo-pj">Empresa</Button>
          </div>
          <Label htmlFor="antigos-novo-nome">{tipoNovo === "pf" ? "Nome" : "Razão social (opcional)"}</Label>
          <Input id="antigos-novo-nome" value={nomeNovo} onChange={(e) => setNomeNovo(e.target.value)} data-testid="antigos-novo-nome" />
          <Label htmlFor="antigos-novo-doc">{tipoNovo === "pf" ? "CPF" : "CNPJ"}</Label>
          <Input id="antigos-novo-doc" value={docNovo} onChange={(e) => setDocNovo(e.target.value)} data-testid="antigos-novo-doc" />
          {adicionar.isError && <p className="text-xs text-destructive" data-testid="antigos-adicionar-erro">{msgDe(adicionar.error)}</p>}
          <DialogFooter>
            <Button data-testid="antigos-adicionar-confirmar"
              disabled={adicionar.isPending || !docNovo.trim() || (tipoNovo === "pf" && !nomeNovo.trim())}
              onClick={() =>
                adicionar.mutate(
                  tipoNovo === "pf"
                    ? { nome: nomeNovo.trim(), cpf: docNovo.trim() }
                    : { cnpj: docNovo.trim(), ...(nomeNovo.trim() ? { razao_social: nomeNovo.trim() } : {}) },
                  { onSuccess: fecharAdicionar },
                )
              }>
              Adicionar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
