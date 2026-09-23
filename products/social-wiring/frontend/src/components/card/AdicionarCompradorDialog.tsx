/**
 * `<AdicionarCompradorDialog/>` — add another party to this atendimento.
 *
 * Presentational (S3): `onCreate` is the only callback out, and this file
 * never fetches. The container decides what happens with the values.
 *
 * 🔴 WHY IT ASKS FOR NAME AND PHONE, AND NOTHING ELSE
 * ---------------------------------------------------
 * Those are exactly the two fields an atendimento cannot move stages without
 * (`pipeline.stage_gate.CAMPOS_OBRIGATORIOS`). Asking for more here would be
 * asking the operator to fill a form in the middle of a different task — the
 * rest of the new person's details belong on the checklist, which is the
 * surface built for collecting them and which will show them as pending until
 * they are.
 *
 * Name is required for a reason worth stating: this creates a PERSON record.
 * A party with no name is a row nobody can identify later, and the contract
 * this exists to support is a legal document naming both buyers.
 *
 * 🔴 ONE DIALOG, BOTH SIDES (migration 098). `lado` changes the copy and the
 * default role and nothing else, because nothing else differs: a vendedor is a
 * `clientes` row with the same checklist, the same uploads and the same
 * extraction as a comprador. A separate `AdicionarVendedorDialog` would have
 * been this file with three strings changed, and the copy that stopped being
 * edited would be the bug.
 *
 * 🔴 …AND A THIRD VARIANT FOR THE SAME REASON. `"conjuge"` (the Cônjuge tab's
 * empty-state action) is COPY ONLY too — it creates the exact same buyer-side
 * party `"comprador"` does, and the container is what sends `papel: "conjuge"`
 * on `onCreate`'s values (this file never learns a role). `lado` stays
 * whatever the request defaults to (`comprador`) — see `ClienteDetailModal
 * .handleAdicionarConjuge`.
 */
import { useEffect, useState } from "react";

import type { LadoParte } from "@/types/cardHub";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** Copy variant — the two negotiation sides plus the Cônjuge tab's own
 *  dedicated action. Not `LadoParte` itself: this prop never reaches the
 *  server (see the module docblock), so it is free to name a THIRD flavor
 *  that still creates a `lado: "comprador"` party underneath. */
export type AdicionarCompradorVariant = LadoParte | "conjuge";

export interface AdicionarCompradorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (values: { nome: string; celular?: string }) => void;
  saving?: boolean;
  /** Which flavor of "add a party" this is. Copy only — the container owns
   *  the request and sends `lado`/`papel` itself. Defaults to the buyer side
   *  so every existing call site keeps its meaning. */
  lado?: AdicionarCompradorVariant;
}

/** Copy per variant. The seller-side description names the OWNER, because
 *  that is what the first vendedor on a deal is; the cônjuge variant names
 *  the legal reason the tab exists at all. */
const COPY: Record<AdicionarCompradorVariant, { titulo: string; descricao: string; placeholder: string }> = {
  comprador: {
    titulo: "Adicionar comprador",
    descricao:
      "Outra pessoa envolvida nesta negociação — um cônjuge, por exemplo. " +
      "Ela terá o mesmo checklist e os mesmos documentos do titular.",
    placeholder: "Maria Mauricio",
  },
  vendedor: {
    titulo: "Adicionar vendedor",
    descricao:
      "Quem está vendendo o imóvel — o proprietário, seu cônjuge ou um " +
      "procurador. Terá o mesmo checklist e os mesmos documentos de qualquer " +
      "outra parte.",
    placeholder: "Carlos Eduardo Ramos",
  },
  conjuge: {
    titulo: "Adicionar cônjuge",
    descricao:
      "O cônjuge do titular — a assinatura que uma venda por pessoa casada " +
      "exige ao lado da dele/dela (CC art. 1.647). Terá o mesmo checklist e " +
      "os mesmos documentos do titular.",
    placeholder: "Maria Mauricio",
  },
};

export function AdicionarCompradorDialog({
  open,
  onOpenChange,
  onCreate,
  saving,
  lado = "comprador",
}: AdicionarCompradorDialogProps) {
  const copy = COPY[lado];
  const [nome, setNome] = useState("");
  const [celular, setCelular] = useState("");

  // Cleared on OPEN rather than on close: clearing on close wipes the fields
  // while the closing animation is still showing them.
  useEffect(() => {
    if (open) {
      setNome("");
      setCelular("");
    }
  }, [open]);

  const podeEnviar = nome.trim().length > 0 && !saving;

  function submit() {
    if (!podeEnviar) return;
    onCreate({
      nome: nome.trim(),
      celular: celular.trim() || undefined,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-md"
        data-testid={`adicionar-${lado}-dialog`}
      >
        <DialogHeader>
          <DialogTitle>{copy.titulo}</DialogTitle>
          <DialogDescription>{copy.descricao}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label
              htmlFor="comprador-nome"
              className="mb-1 block text-xs font-medium text-muted-foreground"
            >
              Nome completo
            </label>
            <Input
              id="comprador-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
              placeholder={copy.placeholder}
              autoFocus
              data-testid="comprador-nome-input"
            />
          </div>
          <div>
            <label
              htmlFor="comprador-celular"
              className="mb-1 block text-xs font-medium text-muted-foreground"
            >
              Celular <span className="font-normal">(opcional)</span>
            </label>
            <Input
              id="comprador-celular"
              value={celular}
              onChange={(e) => setCelular(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
              placeholder="+55 11 99999-8888"
              data-testid="comprador-celular-input"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="comprador-cancelar-btn"
          >
            Cancelar
          </Button>
          <Button
            disabled={!podeEnviar}
            onClick={submit}
            data-testid="comprador-salvar-btn"
          >
            {saving ? "Adicionando…" : "Adicionar"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
