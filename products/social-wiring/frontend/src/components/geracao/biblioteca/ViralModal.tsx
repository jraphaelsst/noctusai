/**
 * "Informações do Viral" modal (contract §7.3; layout mirrors the reference app,
 * owner decision 2026-11-04): profile pill + Gerar headline, video (native player
 * from the scraped `video_url`, Instagram embed fallback), Métricas card,
 * Transcrição card, then Nicho / Profissão / Formato. The structure (gancho,
 * blueprint, #codigo) is deliberately NOT shown here — it surfaces in the chat.
 */
import { useState } from "react";
import type React from "react";
import { CalendarDays, Clipboard, ExternalLink, Eye, FileText, Heart, Link2, MessageCircle } from "lucide-react";
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
import { compactoPtBr, dataHoraPtBr } from "@/components/pesquisa/format";
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
        <DialogContent className="max-h-[90vh] max-w-5xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Informações do Viral</DialogTitle>
            <DialogDescription className="sr-only">
              {v ? `Post de @${v.perfil.handle}` : "Carregando..."}
            </DialogDescription>
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
            <div className="flex flex-col gap-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="inline-flex items-center gap-2 rounded-full border bg-muted/40 py-1 pl-1 pr-3 text-sm">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-[11px] font-semibold uppercase text-primary-foreground">
                    {v.perfil.handle.slice(0, 2)}
                  </span>
                  <span className="font-medium">@{v.perfil.handle}</span>
                  <span className="text-xs text-muted-foreground">instagram</span>
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/media-creation/chat?cite_viral=${encodeURIComponent(v.id)}`}>
                      Citar no Chat
                    </Link>
                  </Button>
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/media-creation/chat?cite_perfil=${encodeURIComponent(v.perfil.id)}`}>
                      Citar perfil no Chat
                    </Link>
                  </Button>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span tabIndex={0}>
                          <Button
                            className="rounded-full"
                            disabled={!v.estrutura_utilizavel}
                            onClick={() => setWizard(true)}
                          >
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
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border p-4">
                  {v.video_url ? (
                    <video
                      src={v.video_url}
                      poster={v.thumbnail_url ?? undefined}
                      controls
                      playsInline
                      preload="metadata"
                      className="aspect-[9/16] max-h-[60vh] w-full rounded-md bg-black object-contain"
                    />
                  ) : embed ? (
                    <iframe
                      title={`Post de @${v.perfil.handle}`}
                      src={embed}
                      className="aspect-[9/16] max-h-[60vh] w-full rounded-md"
                      sandbox="allow-scripts allow-same-origin allow-popups"
                      loading="lazy"
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">Vídeo indisponível.</p>
                  )}
                </div>

                <div className="flex flex-col gap-4 text-sm">
                  <section className="rounded-xl border">
                    <h3 className="border-b px-4 py-3 font-semibold">Métricas</h3>
                    <dl className="grid grid-cols-2 gap-4 p-4">
                      <Metrica icone={<Eye className="h-4 w-4 text-sky-500" />} rotulo="Visualizações" valor={compactoPtBr(v.views)} />
                      <Metrica icone={<Heart className="h-4 w-4 text-rose-500" />} rotulo="Curtidas" valor={compactoPtBr(v.likes)} />
                      <Metrica icone={<MessageCircle className="h-4 w-4 text-emerald-500" />} rotulo="Comentários" valor={compactoPtBr(v.comments)} />
                      <Metrica icone={<CalendarDays className="h-4 w-4 text-fuchsia-500" />} rotulo="Data do Post" valor={dataHoraPtBr(v.publicado_em)} />
                    </dl>
                  </section>

                  <section className="flex flex-col rounded-xl border">
                    <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
                      <h3 className="flex items-center gap-2 font-semibold">
                        <FileText className="h-4 w-4" /> Transcrição
                      </h3>
                      <div className="flex items-center gap-2">
                        <Button size="sm" variant="outline" className="rounded-full" asChild>
                          <a href={v.permalink} target="_blank" rel="noopener noreferrer">
                            <ExternalLink className="mr-1 h-3.5 w-3.5" /> Ver post
                          </a>
                        </Button>
                        <Button
                          size="icon"
                          variant="outline"
                          className="h-8 w-8 rounded-full"
                          aria-label="Copiar link do viral"
                          onClick={() => copiar(linkInternoViral(v.id), "Link copiado!")}
                        >
                          <Link2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                    <div className="flex flex-col gap-3 p-4">
                      {v.transcricao_status !== "concluida" && (
                        <Badge variant="secondary" className="w-fit">
                          {TRANSCRICAO_ROTULO[v.transcricao_status]}
                        </Badge>
                      )}
                      {v.transcricao_texto ? (
                        <Textarea readOnly value={v.transcricao_texto} className="h-44" />
                      ) : (
                        <p className="text-muted-foreground">Sem transcrição disponível.</p>
                      )}
                      <Button
                        variant="outline"
                        className="w-full rounded-full"
                        disabled={!v.transcricao_texto}
                        onClick={() => copiar(v.transcricao_texto ?? "", "Transcrição copiada!")}
                      >
                        <Clipboard className="mr-2 h-4 w-4" /> Copiar Transcrição
                      </Button>
                    </div>
                  </section>
                </div>
              </div>

              <div className="grid gap-4 text-center text-sm sm:grid-cols-2">
                <BadgeGrupo rotulo="Nicho" itens={v.nichos.map((n) => n.nome)} />
                <BadgeGrupo rotulo="Profissão" itens={v.profissoes.map((n) => n.nome)} />
                <div className="sm:col-span-2">
                  <BadgeGrupo rotulo="Formato do Vídeo" itens={v.formatos.map((n) => n.nome)} />
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

function Metrica({ icone, rotulo, valor }: { icone: React.ReactNode; rotulo: string; valor: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5">{icone}</span>
      <div>
        <dt className="text-muted-foreground">{rotulo}</dt>
        <dd className="font-medium">{valor}</dd>
      </div>
    </div>
  );
}

function BadgeGrupo({ rotulo, itens }: { rotulo: string; itens: string[] }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <span className="text-muted-foreground">{rotulo}:</span>
      <div className="flex flex-wrap justify-center gap-1.5">
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
    </div>
  );
}
