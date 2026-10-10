/**
 * Treinamentos (P6, `/media-creation/treinamentos`) — player + "Aulas" list.
 * A lesson without `video_url` shows an honest "Vídeo em produção" empty state; a URL
 * is embedded only when it is https on an allow-listed host (contract §4.2, §7.6).
 * Admins (`GET /treinamentos/admin`) get a pencil per lesson. The server enforces both.
 */
import { useState } from "react";
import { AlertCircle, Loader2, Pencil, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { mensagemErro } from "@/components/cerebro/labels";
import {
  useAtualizarTreinamento,
  useTreinamentos,
  useTreinamentosAdmin,
} from "@/hooks/geracao/useTreinamentos";
import type { Treinamento } from "@/types/geracao";

/** Mirrors the backend `TREINAMENTO_VIDEO_HOSTS` (the UI never embeds anything else). */
export const TREINAMENTO_VIDEO_HOSTS = [
  "iframe.mediadelivery.net",
  "player.vimeo.com",
  "www.youtube.com",
  "www.youtube-nocookie.com",
];

/** The URL itself when it is embeddable (https + allow-listed host), else null. */
export function urlEmbedSegura(url: string | null): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "https:" && TREINAMENTO_VIDEO_HOSTS.includes(u.hostname) ? u.toString() : null;
  } catch {
    return null;
  }
}

export function Treinamentos() {
  const aulasQ = useTreinamentos();
  const adminQ = useTreinamentosAdmin();
  const aulas = aulasQ.data ?? [];
  const [ativaId, setAtivaId] = useState<string | null>(null);
  const [editando, setEditando] = useState<Treinamento | null>(null);

  const ativa = aulas.find((a) => a.id === ativaId) ?? aulas[0] ?? null;
  const embed = urlEmbedSegura(ativa?.video_url ?? null);
  const isAdmin = adminQ.data === true;

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Treinamentos</h1>
          <p className="text-sm text-muted-foreground">Primeiros passos: da Bio aos primeiros roteiros</p>
        </div>
        {aulasQ.isRefreshing && (
          <span role="status" className="flex items-center gap-1 text-sm text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Atualizando…
          </span>
        )}
      </header>

      {aulasQ.showSkeleton ? (
        <div className="grid gap-4 lg:grid-cols-[1fr_320px]" aria-busy="true" data-testid="treinamentos-skeleton">
          <Skeleton className="aspect-video w-full" />
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </div>
      ) : aulasQ.isError && !aulasQ.data ? (
        <div role="alert" className="flex flex-col items-center gap-3 py-16 text-sm">
          <AlertCircle className="h-6 w-6 text-destructive" />
          Não foi possível carregar os treinamentos.
          <Button variant="outline" size="sm" onClick={() => void aulasQ.refetch()}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Tentar novamente
          </Button>
        </div>
      ) : aulas.length === 0 || !ativa ? (
        <p className="py-16 text-center text-sm text-muted-foreground">Nenhum treinamento disponível.</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <section aria-label="Player" className="space-y-3">
            {embed ? (
              <iframe
                key={ativa.id}
                title={ativa.titulo}
                src={embed}
                loading="lazy"
                allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
                className="aspect-video w-full rounded-lg border"
              />
            ) : (
              <div
                data-testid="video-em-producao"
                className="flex aspect-video w-full items-center justify-center rounded-lg border bg-muted/30 text-sm text-muted-foreground"
              >
                Vídeo em produção — em breve.
              </div>
            )}
            <div>
              <h2 className="text-lg font-medium">{ativa.titulo}</h2>
              <p className="text-sm text-muted-foreground">{ativa.descricao}</p>
            </div>
          </section>

          <aside aria-label="Aulas" className="space-y-2">
            <h2 className="text-base font-medium">Aulas</h2>
            <ol className="space-y-2">
              {aulas.map((a, i) => (
                <li key={a.id} className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setAtivaId(a.id)}
                    aria-current={a.id === ativa.id ? "true" : undefined}
                    className={`flex flex-1 items-center gap-3 rounded-md border p-3 text-left text-sm ${
                      a.id === ativa.id ? "border-primary bg-primary/5" : "hover:bg-muted/50"
                    }`}
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs">
                      {i + 1}
                    </span>
                    {a.titulo}
                  </button>
                  {isAdmin && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Editar aula ${i + 1}`}
                      onClick={() => setEditando(a)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  )}
                </li>
              ))}
            </ol>
          </aside>
        </div>
      )}

      <EditarAulaModal aula={editando} onClose={() => setEditando(null)} />
    </div>
  );
}

function EditarAulaModal({ aula, onClose }: { aula: Treinamento | null; onClose: () => void }) {
  return (
    <Dialog open={!!aula} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>{aula && <EditarAulaForm key={aula.id} aula={aula} onClose={onClose} />}</DialogContent>
    </Dialog>
  );
}

function EditarAulaForm({ aula, onClose }: { aula: Treinamento; onClose: () => void }) {
  const [titulo, setTitulo] = useState(aula.titulo);
  const [descricao, setDescricao] = useState(aula.descricao);
  const [url, setUrl] = useState(aula.video_url ?? "");
  const [ativo, setAtivo] = useState(aula.ativo);
  const atualizarM = useAtualizarTreinamento();

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    try {
      await atualizarM.mutateAsync({
        id: aula.id,
        titulo: titulo.trim(),
        descricao: descricao.trim(),
        video_url: url.trim() === "" ? null : url.trim(),
        ativo,
      });
      toast.success("Aula atualizada.");
      onClose();
    } catch (err) {
      toast.error(mensagemErro(err, "Não foi possível atualizar a aula."));
    }
  }

  return (
    <form onSubmit={salvar} className="space-y-4">
      <DialogHeader>
        <DialogTitle>Editar aula</DialogTitle>
      </DialogHeader>
      <div className="space-y-1.5">
        <Label htmlFor="aula-titulo">Título</Label>
        <Input id="aula-titulo" value={titulo} maxLength={160} onChange={(e) => setTitulo(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="aula-descricao">Descrição</Label>
        <Textarea id="aula-descricao" rows={3} maxLength={1000} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="aula-url">URL do vídeo</Label>
        <Input
          id="aula-url"
          type="url"
          placeholder="https://iframe.mediadelivery.net/embed/..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">Hospedagens aceitas: {TREINAMENTO_VIDEO_HOSTS.join(", ")}.</p>
      </div>
      <div className="flex items-center gap-2">
        <Switch id="aula-ativo" checked={ativo} onCheckedChange={setAtivo} />
        <Label htmlFor="aula-ativo">Ativo</Label>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={atualizarM.isPending}>
          Cancelar
        </Button>
        <Button type="submit" disabled={atualizarM.isPending || titulo.trim() === ""}>
          {atualizarM.isPending ? "Salvando…" : "Salvar"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export default Treinamentos;
