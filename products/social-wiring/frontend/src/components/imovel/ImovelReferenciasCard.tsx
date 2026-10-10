/**
 * ImovelReferenciasCard — "Referências do negócio" (S6, CONTRACT §8.4).
 *
 * Shown on EVERY imóvel (Vista or manual): the processo atual number and a link
 * to the deal's Drive folder, editable inline via `PATCH /{codigo}/referencias`
 * (the one write that is valid for a Vista imóvel too — it is authored data,
 * not mirror data). The Drive URL is validated here as well as on the BE.
 */
import { useState } from "react";
import { ExternalLink, FolderOpen, Loader2, Pencil } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ImovelReferencias } from "@/hooks/useImoveis";
import {
  driveUrlValida,
  useAtualizarReferencias,
} from "@/hooks/useImovelManual";

export default function ImovelReferenciasCard({
  codigo,
  referencias,
}: {
  codigo: string;
  referencias?: ImovelReferencias | null;
}) {
  const processo = referencias?.processo_atual_numero ?? "";
  const drive = referencias?.drive_folder_url ?? "";
  const [editando, setEditando] = useState(false);
  const [dProcesso, setDProcesso] = useState(processo);
  const [dDrive, setDDrive] = useState(drive);
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useAtualizarReferencias(codigo);

  function abrirEdicao() {
    setDProcesso(processo);
    setDDrive(drive);
    setErro(null);
    setEditando(true);
  }

  async function submeter(ev: React.FormEvent) {
    ev.preventDefault();
    const driveLimpo = dDrive.trim();
    if (driveLimpo && !driveUrlValida(driveLimpo)) {
      setErro(
        "Use o link de uma pasta: https://drive.google.com/…/folders/<id>",
      );
      return;
    }
    const patch: {
      processo_atual_numero?: string | null;
      drive_folder_url?: string | null;
    } = {};
    if (dProcesso.trim() !== processo)
      patch.processo_atual_numero = dProcesso.trim() || null;
    if (driveLimpo !== drive) patch.drive_folder_url = driveLimpo || null;
    if (Object.keys(patch).length === 0) {
      setEditando(false);
      return;
    }
    try {
      await salvar.mutateAsync(patch);
      toast.success("Referências atualizadas.");
      setEditando(false);
    } catch (e) {
      setErro(
        e instanceof Error
          ? e.message
          : "Não foi possível salvar as referências.",
      );
    }
  }

  return (
    <Card id="imovel-referencias" data-testid="imovel-referencias">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Referências do negócio</CardTitle>
        {!editando && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={abrirEdicao}
            data-testid="imovel-referencias-editar"
          >
            <Pencil className="mr-1.5 h-3.5 w-3.5" />
            Editar
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {editando ? (
          <form onSubmit={submeter} className="space-y-3" noValidate>
            <div className="space-y-1">
              <Label htmlFor="ref-processo" className="text-xs">
                Processo atual (nº)
              </Label>
              <Input
                id="ref-processo"
                value={dProcesso}
                onChange={(e) => setDProcesso(e.target.value)}
                disabled={salvar.isPending}
                data-testid="imovel-referencias-processo"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ref-drive" className="text-xs">
                Pasta do Drive (link)
              </Label>
              <Input
                id="ref-drive"
                value={dDrive}
                onChange={(e) => setDDrive(e.target.value)}
                placeholder="https://drive.google.com/drive/folders/…"
                disabled={salvar.isPending}
                data-testid="imovel-referencias-drive"
              />
            </div>
            {erro && (
              <p
                className="text-xs text-destructive"
                role="alert"
                data-testid="imovel-referencias-erro"
              >
                {erro}
              </p>
            )}
            <div className="flex gap-2">
              <Button
                type="submit"
                size="sm"
                disabled={salvar.isPending}
                data-testid="imovel-referencias-salvar"
              >
                {salvar.isPending && (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                )}
                Salvar
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={salvar.isPending}
                onClick={() => setEditando(false)}
              >
                Cancelar
              </Button>
            </div>
          </form>
        ) : (
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">Processo atual</dt>
              <dd data-testid="imovel-referencias-processo-valor">
                {processo || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Pasta do Drive</dt>
              <dd>
                {drive ? (
                  <a
                    href={drive}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-primary hover:underline"
                    data-testid="imovel-referencias-drive-link"
                  >
                    <FolderOpen className="h-4 w-4" />
                    Abrir pasta no Drive
                    <ExternalLink className="h-3 w-3" />
                  </a>
                ) : (
                  "—"
                )}
              </dd>
            </div>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
