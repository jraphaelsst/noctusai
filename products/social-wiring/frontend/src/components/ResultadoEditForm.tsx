/**
 * The one "type the certidão by hand" form (número · resultado · emitida em ·
 * validade). Shared by the "Detalhes" dialog (`CertidoesPartePanel`) and the
 * party levantamento table (`card/certidoes/ParteSecao` via the tab), so a
 * pending cell with no resultado row yet is edited with the SAME form.
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  RESULTADO_VALOR_LABELS,
  type ResultadoPatchInput,
  type ResultadoValor,
} from "@/types/certidoesEstruturadas";

/** The slice of a resultado/cell the form pre-fills from. */
export interface ResultadoEditInicial {
  tipo?: string | null;
  numero?: string | null;
  emitida_em?: string | null;
  validade_ate?: string | null;
  resultado?: string | null;
}

export function ResultadoEditForm({
  resultado,
  saving,
  onCancel,
  onConfirm,
}: {
  resultado: ResultadoEditInicial;
  saving: boolean;
  onCancel: () => void;
  onConfirm: (patch: ResultadoPatchInput) => void;
}) {
  const [numero, setNumero] = useState(resultado.numero ?? "");
  // Never default an empty emissão date to today: a blank date is the honest
  // state and defaulting it silently stamped fresh dates onto old certidões
  // (atendimento-partes-imoveis spec §3.1). The operator types the real one.
  const [emitidaEm, setEmitidaEm] = useState(resultado.emitida_em ?? "");
  const [validadeAte, setValidadeAte] = useState(resultado.validade_ate ?? "");
  const [valor, setValor] = useState<ResultadoValor | "">(
    (resultado.resultado as ResultadoValor) || "",
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Only the fields that actually changed ride the request — an untouched
    // form submits `{}`, which is still a valid confirmation per the
    // endpoint's own contract (see `useConfirmarResultado`'s docstring).
    const patch: ResultadoPatchInput = {};
    if (numero !== (resultado.numero ?? "")) patch.numero = numero || undefined;
    if (emitidaEm !== (resultado.emitida_em ?? "")) patch.emitida_em = emitidaEm || undefined;
    if (validadeAte !== (resultado.validade_ate ?? "")) {
      patch.validade_ate = validadeAte || undefined;
    }
    if (valor !== ((resultado.resultado as ResultadoValor) || "")) {
      patch.resultado = (valor || undefined) as ResultadoValor | undefined;
    }
    onConfirm(patch);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4" data-testid="certidoes-parte-edit-form">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="certidoes-parte-numero">Número</Label>
          <Input
            id="certidoes-parte-numero"
            value={numero}
            onChange={(e) => setNumero(e.target.value)}
          />
        </div>
        <div>
          <Label>Resultado</Label>
          <Select value={valor} onValueChange={(v) => setValor(v as ResultadoValor)}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(RESULTADO_VALOR_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="certidoes-parte-emitida-em">Emitida em</Label>
          <Input
            id="certidoes-parte-emitida-em"
            type="date"
            value={emitidaEm}
            onChange={(e) => setEmitidaEm(e.target.value)}
          />
          {/* Serasa/CENPROT carry no printed emission date of their own —
              the office's rule is to use the date the consulta was made. */}
          {(resultado.tipo === "serasa" || resultado.tipo === "cenprot") && (
            <p className="mt-1 text-xs text-muted-foreground">
              Para Serasa/CENPROT, use a data da consulta.
            </p>
          )}
        </div>
        <div>
          <Label htmlFor="certidoes-parte-validade-ate">Validade até</Label>
          <Input
            id="certidoes-parte-validade-ate"
            type="date"
            value={validadeAte}
            onChange={(e) => setValidadeAte(e.target.value)}
          />
        </div>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={saving}>
          {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Confirmar
        </Button>
      </DialogFooter>
    </form>
  );
}
