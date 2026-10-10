/**
 * "Informações do Viral" modal (contract §7.3): Instagram embed, metrics,
 * transcript (with an honest status chip when it is not `concluida`), badges
 * and the actions Gerar headline / Citar no Chat / Citar perfil no Chat.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { compactoPtBr, dataPtBr } from "@/components/pesquisa/format";
import { GATILHO_ROTULO } from "@/components/geracao/labels";
import { useViralDetalhe } from "@/hooks/geracao/useBiblioteca";
import type { TranscricaoViralStatus } from "@/types/geracao";
import { embedUrlInstagram } from "./filtros";
import { GerarHeadlineWizard } from "./GerarHeadlineWizard";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marcaId: string | null;
  viralId: string | null;
}

export const TRANSCRICAO_ROTULO: Record<TranscricaoViralStatus, string> = {
  nao_aplicavel: "Sem áudio para transcrever",
  pendente: "Transcrição pendente",
  na_fila: "Transcrição na fila",
  concluida: "Transcrição concluída",
  falhou: "A transcrição falhou",
  grande_demais: "Vídeo grande demais para transcrever",
  longa_demais: "Vídeo longo demais para transcrever",
  sem_orcamento: "Transcrição adiada (sem orçamento no momento)",
};

export function linkInternoViral(id: string): string {
  return `${window.location.origin}/media-creation/biblioteca?viral=${id}`;
}

async function copiar(texto: string, ok: string) {
  try {
    await navigator.clipboard.writeText(texto);
    toast.success(ok);
  } catch {
    toast.error("Não foi possível copiar.");
  }
}

export function ViralModal({ open, onOpenChange, marcaId, viralId }: Props) {
  const q = useViralDetalhe(open ? marcaId : null, open ? viralId : null);
  const v = q.data;
  const [wizard, setWizard] = useState(false);
  const embed = embedUrlInstagram(v?.permalink);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Informações do Viral</DialogTitle>
            <DialogDescription>{v ? `@${v.perfil.handle}` : "Carregando..."}</DialogDescription>
          </DialogHeader>

          {q.showSkeleton ? (
            <Skeleton className="h-72 w-full" />
          ) : q.isError || !v ? (
            <div className="text-sm text-destructive">
              Não foi possível carregar este viral.{" "}
              <Button variant="link" className="h-auto p-0" onClick={() => q.refetch()}>
                Tentar novamente
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap gap-2">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span tabIndex={0}>
                        <Button disabled={!v.estrutura_utilizavel} onClick={() => setWizard(true)}>
                          Gerar headline
                        </Button>
                      </span>
                    </TooltipTrigger>
                    {!v.estrutura_utilizavel && (
                      <TooltipContent>
                        A estrutura deste viral ainda não está disponível para gerar headlines.
                      </TooltipContent>
                    )}
                  </Tooltip>
                </TooltipProvider>
                <Button variant="outline" asChild>
                  <Link to={`/media-creation/chat?cite_viral=${encodeURIComponent(v.id)}`}>
                    Citar no Chat
                  </Link>
                </Button>
                <Button variant="outline" asChild>
                  <Link to={`/media-creation/chat?cite_perfil=${encodeURIComponent(v.perfil.id)}`}>
                    Citar perfil no Chat
                  </Link>
                </Button>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  {embed ? (
                    <iframe
                      title={`Post de @${v.perfil.handle}`}
                      src={embed}
                      className="aspect-[9/16] w-full rounded-md border"
                      sandbox="allow-scripts allow-same-origin allow-popups"
                      loading="lazy"
                    />
                  ) : null}
                  <p className="mt-2 text-xs text-muted-foreground">
                    Não consegue ver o vídeo?{" "}
                    <a
                      href={v.permalink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline"
                    >
                      Abrir no Instagram
                    </a>
                  </p>
                </div>

                <div className="flex flex-col gap-4 text-sm">
                  <section>
                    <h3 className="mb-1 font-semibold">Métricas</h3>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                      <dt className="text-muted-foreground">Visualizações</dt>
                      <dd>{compactoPtBr(v.views)}</dd>
                      <dt className="text-muted-foreground">Curtidas</dt>
                      <dd>{compactoPtBr(v.likes)}</dd>
                      <dt className="text-muted-foreground">Comentários</dt>
                      <dd>{compactoPtBr(v.comments)}</dd>
                      <dt className="text-muted-foreground">Data do Post</dt>
                      <dd>{dataPtBr(v.publicado_em)}</dd>
                    </dl>
                  </section>

                  <section className="flex flex-col gap-2">
                    <h3 className="font-semibold">Transcrição</h3>
                    {v.transcricao_status !== "concluida" && (
                      <Badge variant="secondary" className="w-fit">
                        {TRANSCRICAO_ROTULO[v.transcricao_status]}
                      </Badge>
                    )}
                    {v.transcricao_texto ? (
                      <Textarea readOnly value={v.transcricao_texto} className="h-40" />
                    ) : (
                      <p className="text-muted-foreground">Sem transcrição disponível.</p>
                    )}
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!v.transcricao_texto}
                        onClick={() => copiar(v.transcricao_texto ?? "", "Transcrição copiada!")}
                      >
                        Copiar Transcrição
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => copiar(linkInternoViral(v.id), "Link copiado!")}
                      >
                        Copiar link
                      </Button>
                    </div>
                  </section>

                  <section className="flex flex-col gap-1.5">
                    <BadgeGrupo rotulo="Nicho" itens={v.nichos.map((n) => n.nome)} />
                    <BadgeGrupo rotulo="Profissão" itens={v.profissoes.map((n) => n.nome)} />
                    <BadgeGrupo rotulo="Formato do Vídeo" itens={v.formatos.map((n) => n.nome)} />
                    <BadgeGrupo
                      rotulo="Gatilho"
                      itens={v.gatilho ? [GATILHO_ROTULO[v.gatilho]] : []}
                    />
                  </section>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
      {v && marcaId && (
        <GerarHeadlineWizard
          open={wizard}
          onOpenChange={setWizard}
          marcaId={marcaId}
          viralId={v.id}
          handle={v.perfil.handle}
        />
      )}
    </>
  );
}

function BadgeGrupo({ rotulo, itens }: { rotulo: string; itens: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-muted-foreground">{rotulo}:</span>
      {itens.length === 0 ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        itens.map((i) => (
          <Badge key={i} variant="outline">
            {i}
          </Badge>
        ))
      )}
    </div>
  );
}
