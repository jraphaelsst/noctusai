/**
 * MotivoRejeicaoDialog — asks the broker WHY a swap match is being rejected.
 *
 * The answer is tuning data for the matching scorer, so the reason is a fixed
 * vocabulary owned by the backend (`useMotivosRejeicao`) — never listed here.
 * A refusal from the server stays visible inside the dialog (it does not
 * close), and the motivos query has its own loading and error states.
 */
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import {
  useMotivosRejeicao,
  type MotivoLado,
  type MoverEtapaInput,
} from "@/hooks/usePermutas";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const LADOS: { valor: MotivoLado | ""; rotulo: string }[] = [
  { valor: "origem", rotulo: "Origem" },
  { valor: "destino", rotulo: "Destino" },
  { valor: "ambos", rotulo: "Ambos" },
  { valor: "", rotulo: "Não sei" },
];

type Dados = Pick<MoverEtapaInput, "motivo_rejeicao" | "motivo_rejeicao_detalhe" | "motivo_lado">;

export function MotivoRejeicaoDialog({
  aberto,
  onFechar,
  onConfirmar,
  enviando,
  erro,
}: {
  aberto: boolean;
  onFechar: () => void;
  onConfirmar: (dados: Dados) => void;
  enviando: boolean;
  /** The server's message when the last attempt was refused. */
  erro: string | null;
}) {
  const motivos = useMotivosRejeicao();
  const [codigo, setCodigo] = useState("");
  const [lado, setLado] = useState<MotivoLado | "">("");
  const [detalhe, setDetalhe] = useState("");

  useEffect(() => {
    if (aberto) {
      setCodigo("");
      setLado("");
      setDetalhe("");
    }
  }, [aberto]);

  const escolhido = (motivos.data ?? []).find((m) => m.codigo === codigo);
  const valido = !!escolhido && (!escolhido.exige_detalhe || detalhe.trim() !== "");

  function confirmar() {
    if (!escolhido || !valido) return;
    onConfirmar({
      motivo_rejeicao: escolhido.codigo,
      ...(detalhe.trim() ? { motivo_rejeicao_detalhe: detalhe.trim() } : {}),
      ...(lado ? { motivo_lado: lado } : {}),
    });
  }

  return (
    <Dialog open={aberto} onOpenChange={(o) => !o && !enviando && onFechar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Por que rejeitar este match?</DialogTitle>
          <DialogDescription>
            O motivo ajuda a calibrar o motor de sugestões de permuta.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {motivos.isPending && !motivos.data ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="motivos-carregando">
              <Loader2 className="h-4 w-4 animate-spin" />
              Carregando motivos…
            </p>
          ) : motivos.isError && !motivos.data ? (
            <p className="text-sm text-destructive" role="alert">
              Não foi possível carregar os motivos.{" "}
              {(motivos.error as { message?: string } | null)?.message ?? "Tente novamente."}
            </p>
          ) : (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Motivo</legend>
              {(motivos.data ?? []).map((m) => (
                <label key={m.codigo} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="motivo-rejeicao"
                    value={m.codigo}
                    checked={codigo === m.codigo}
                    onChange={() => setCodigo(m.codigo)}
                  />
                  {m.rotulo}
                </label>
              ))}
            </fieldset>
          )}

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Quem recusou?</legend>
            <div className="flex flex-wrap gap-4">
              {LADOS.map((l) => (
                <label key={l.rotulo} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="motivo-lado"
                    checked={lado === l.valor}
                    onChange={() => setLado(l.valor)}
                  />
                  {l.rotulo}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="space-y-1">
            <Label htmlFor="motivo-detalhe">
              Detalhes{escolhido?.exige_detalhe ? " (obrigatório)" : " (opcional)"}
            </Label>
            <Textarea
              id="motivo-detalhe"
              value={detalhe}
              onChange={(e) => setDetalhe(e.target.value)}
              rows={3}
            />
          </div>

          {erro && (
            <p className="text-sm text-destructive" role="alert">
              {erro}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onFechar} disabled={enviando}>
            Cancelar
          </Button>
          <Button onClick={confirmar} disabled={!valido || enviando}>
            {enviando && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Confirmar rejeição
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
