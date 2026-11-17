/**
 * "Adicionar por link" (platform admin, Vídeos tab): paste ONE Instagram post URL → the server fetches it,
 * dedupes by shortcode, creates the profile when absent (not monitored) and queues the analysis.
 * Every outcome is shown: added, already in the library (`ja_existia`), and each refusal code.
 */
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAdicionarVideoPorLink } from "@/hooks/geracao/useEstruturas";
import type { VideoPorLinkResultado } from "@/types/estruturas";
import { mensagemEstruturas } from "./erros";
import { normalizarLinkInstagram } from "./link";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PorLinkDialog({ open, onOpenChange }: Props) {
  const [url, setUrl] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<VideoPorLinkResultado | null>(null);
  const adicionar = useAdicionarVideoPorLink();

  function fechar(o: boolean) {
    if (!o) {
      setUrl("");
      setErro(null);
      setResultado(null);
      adicionar.reset();
    }
    onOpenChange(o);
  }

  async function enviar() {
    const link = normalizarLinkInstagram(url);
    if (link.ok === false) {
      setErro(link.erro);
      return;
    }
    setErro(null);
    try {
      setResultado(await adicionar.mutateAsync(link.url));
    } catch (e) {
      setErro(mensagemEstruturas(e, "Não foi possível adicionar o vídeo."));
    }
  }

  return (
    <Dialog open={open} onOpenChange={fechar}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Adicionar vídeo por link</DialogTitle>
          <DialogDescription>
            Cole o link de um post público do Instagram. O vídeo entra na biblioteca da plataforma e é analisado em seguida.
          </DialogDescription>
        </DialogHeader>

        {resultado ? (
          <div role="status" className="flex flex-col gap-2 text-sm" data-testid="por-link-resultado">
            {resultado.ja_existia ? (
              <p className="font-medium">Este vídeo já estava na biblioteca. Nada foi alterado.</p>
            ) : (
              <>
                <p className="font-medium">Vídeo adicionado. A transcrição e a análise começam em seguida.</p>
                {resultado.perfil_criado && (
                  <p className="text-muted-foreground">
                    O perfil @{resultado.viral.perfil.handle} foi criado na biblioteca, sem monitoramento contínuo.
                  </p>
                )}
              </>
            )}
            <Button asChild variant="outline" className="w-fit" onClick={() => fechar(false)}>
              <Link to={`/media-creation/biblioteca?viral=${encodeURIComponent(resultado.viral.id)}`}>Abrir o vídeo</Link>
            </Button>
          </div>
        ) : (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void enviar();
            }}
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="por-link-url">Link do post do Instagram</Label>
              <Input
                id="por-link-url"
                inputMode="url"
                autoComplete="off"
                placeholder="https://www.instagram.com/reel/…"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  setErro(null);
                }}
                aria-invalid={!!erro}
                aria-describedby={erro ? "por-link-erro" : undefined}
              />
              {erro && (
                <p id="por-link-erro" role="alert" className="text-sm text-destructive">
                  {erro}
                </p>
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => fechar(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={adicionar.isPending || !url.trim()}>
                {adicionar.isPending ? "Adicionando..." : "Adicionar"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
