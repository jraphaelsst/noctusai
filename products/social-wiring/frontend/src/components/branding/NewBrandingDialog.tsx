/** "Novo branding" — blank, or copied from the Branding Template. */
import { useState } from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
  Field,
  FormError,
  Input,
  Select,
} from "@noctusai/lib/design-system";

import { useCreateBranding } from "@/hooks/useBranding";
import { useMarcas } from "@/hooks/useMarcas";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function NewBrandingDialog({
  open,
  onClose,
  hasTemplate,
  defaultMarcaId,
  defaultFromTemplate,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  hasTemplate: boolean;
  defaultMarcaId?: string | null;
  defaultFromTemplate?: boolean;
  onCreated: (id: string) => void;
}) {
  const marcas = useMarcas();
  const create = useCreateBranding();
  const [name, setName] = useState("");
  const [marcaId, setMarcaId] = useState<string>(defaultMarcaId ?? "");
  const [fromTemplate, setFromTemplate] = useState(!!defaultFromTemplate && hasTemplate);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    try {
      const d = await create.mutateAsync({
        name: name.trim(),
        marca_id: marcaId || null,
        from_template: fromTemplate,
      });
      toast.success("Branding criado");
      setName("");
      onCreated(d.id);
    } catch (err) {
      setError(mensagemErroServidor(err, "Falha ao criar o branding"));
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Novo branding">
      <DialogHeader>
        <h3 className="text-base font-semibold">Novo branding</h3>
      </DialogHeader>
      <DialogBody className="space-y-3">
        <Field label="Nome" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} data-testid="branding-new-name" />
        </Field>
        <Field label="Marca">
          <Select
            value={marcaId}
            onChange={(e) => setMarcaId(e.target.value)}
            disabled={marcas.isPending && !marcas.data}
            data-testid="branding-new-marca"
          >
            <option value="">— sem marca —</option>
            {(marcas.data ?? []).map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={fromTemplate}
            disabled={!hasTemplate}
            onChange={(e) => setFromTemplate(e.target.checked)}
            data-testid="branding-new-from-template"
          />
          Criar a partir do Branding Template
          {!hasTemplate && <span className="text-xs text-muted-foreground">(importe o template primeiro)</span>}
        </label>
        <FormError message={error} />
      </DialogBody>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
        <Button variant="primary" disabled={!name.trim() || create.isPending} onClick={() => void submit()} data-testid="branding-new-submit">
          {create.isPending ? "Criando…" : "Criar"}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
