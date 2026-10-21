/**
 * ClientForm -- create / edit a client.
 *
 * "Razão Social" is REQUIRED (it is what contracts snapshot and what goes to the payment gateway); "Nome fantasia" is optional
 * and falls back to the legal name. Typing a CNPJ offers "Buscar CNPJ": the Razão Social comes from the public registry
 * (BrasilAPI / ReceitaWS through /api/clients/cnpj/{cnpj}) and prefills the field -- an empty field is filled, a typed one
 * is never overwritten silently (an explicit "Usar" button).
 */
import { useState } from "react";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { toast } from "sonner";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Field, Input, Select } from "@noctusai/lib/design-system";
import { api } from "@/lib/api";
import type { ClientOption } from "@/hooks/useClients";
import { clientPayload, documentDigits, isCnpj } from "@/lib/clientPayload";

export interface ClientFormValues {
  id?: string;
  legal_name: string;
  name: string;
  document: string;
  email: string;
  phone: string;
  monthly_value: string;
  due_date: string;
  default_billing_type: string;
  billing_automation_enabled: boolean;
}

export const EMPTY_CLIENT: ClientFormValues = {
  legal_name: "", name: "", document: "", email: "", phone: "", monthly_value: "", due_date: "",
  default_billing_type: "", billing_automation_enabled: false,
};

export interface ClientRowLike {
  id: string;
  legal_name?: string | null;
  name: string;
  document?: string | null;
  email: string | null;
  phone: string | null;
  monthly_value: number | null;
  due_date: number | null;
  default_billing_type: string | null;
  billing_automation_enabled: boolean;
}

/** The form values of an existing row. A nome fantasia equal to the legal name is shown empty (it is the fallback). */
export function valuesOf(row: ClientRowLike): ClientFormValues {
  const legal = row.legal_name || row.name;
  return {
    id: row.id,
    legal_name: legal,
    name: row.name && row.name !== legal ? row.name : "",
    document: row.document ?? "",
    email: row.email ?? "",
    phone: row.phone ?? "",
    monthly_value: row.monthly_value != null ? String(row.monthly_value) : "",
    due_date: row.due_date != null ? String(row.due_date) : "",
    default_billing_type: row.default_billing_type ?? "",
    billing_automation_enabled: row.billing_automation_enabled,
  };
}

const BILLING_TYPES = [
  { value: "", label: "Selecione…" },
  { value: "boleto", label: "Boleto (gateway)" },
  { value: "pix", label: "PIX (gateway)" },
  { value: "cartao", label: "Cartão" },
  { value: "transferencia", label: "Transferência" },
];

interface CnpjFound {
  cnpj: string;
  legal_name: string | null;
  situacao_cadastral: string | null;
}

export function ClientForm({ open, initial, onClose, onSaved }: { open: boolean; initial: ClientFormValues; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<ClientFormValues>(initial);
  const [found, setFound] = useState<CnpjFound | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [looking, setLooking] = useState(false);
  const editing = !!initial.id;
  const set = <K extends keyof ClientFormValues>(key: K, value: ClientFormValues[K]) => setForm((f) => ({ ...f, [key]: value }));
  const legalMissing = form.legal_name.trim() === "";

  // The saved client goes straight into the picker options (active clients, newest
  // first): a new one on top, an edit in place, an inactivated one out.
  const save = useCacheWriteMutation<ClientOption, void>({
    mutationFn: async () => {
      const payload = clientPayload({ ...form });
      return editing
        ? api.patch<ClientOption>(`/api/clients/${initial.id}`, payload)
        : api.post<ClientOption>("/api/clients", payload);
    },
    targets: [
      {
        queryKey: ["orbity-client-options"],
        commit: (old: ClientOption[] | undefined, saved) =>
          saved.active === false
            ? listOps.remove(old, saved.id)
            : editing
              ? listOps.patch(old, saved.id, saved)
              : listOps.replace(old, saved.id, saved, "prepend"),
      },
    ],
    onSuccess: () => {
      toast.success(editing ? "Cliente atualizado" : "Cliente criado");
      onSaved();
    },
    onError: (error: Error) => {
      toast.error(editing ? "Falha ao atualizar cliente" : "Falha ao criar cliente", { description: error.message });
    },
  });

  const lookup = async () => {
    setLooking(true);
    setLookupError(null);
    setFound(null);
    try {
      const res = await api.get<CnpjFound>(`/api/clients/cnpj/${documentDigits(form.document)}`);
      if (!res.legal_name) {
        setLookupError("A Receita Federal não informou a Razão Social deste CNPJ. Preencha manualmente.");
      } else if (form.legal_name.trim() === "") {
        set("legal_name", res.legal_name);
        setFound({ ...res, legal_name: null }); // applied; nothing left to offer
      } else {
        setFound(res);
      }
    } catch (err: unknown) {
      setLookupError(err instanceof Error ? err.message : "Não foi possível consultar o CNPJ.");
    } finally {
      setLooking(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={editing ? "Editar cliente" : "Novo cliente"}>
      <DialogHeader><h3 className="text-base font-semibold">{editing ? "Editar cliente" : "Novo cliente"}</h3></DialogHeader>
      <DialogBody>
        <form
          id="client-form"
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!legalMissing) save.mutate();
          }}
        >
          <Field label="CPF / CNPJ">
            <div className="flex gap-2">
              <Input value={form.document} onChange={(e) => { set("document", e.target.value); setFound(null); setLookupError(null); }} placeholder="00.000.000/0000-00" />
              <Button type="button" variant="outline" disabled={!isCnpj(form.document) || looking} onClick={() => void lookup()}>
                {looking ? "Buscando…" : "Buscar CNPJ"}
              </Button>
            </div>
          </Field>
          {lookupError ? <p className="text-xs text-destructive" role="alert">{lookupError}</p> : null}
          {found?.legal_name ? (
            <p className="text-xs text-muted-foreground" role="status">
              Receita Federal: <strong>{found.legal_name}</strong>{" "}
              <button type="button" className="underline" onClick={() => { set("legal_name", found.legal_name ?? ""); setFound(null); }}>Usar como Razão Social</button>
            </p>
          ) : null}

          <Field label="Razão Social" required error={legalMissing ? "Informe a Razão Social (é o nome usado na cobrança)." : null}>
            <Input value={form.legal_name} onChange={(e) => set("legal_name", e.target.value)} maxLength={255} placeholder="Empresa Exemplo Comércio Ltda" />
          </Field>
          <Field label="Nome fantasia (opcional)">
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} maxLength={255} placeholder={form.legal_name || "Usa a Razão Social quando vazio"} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="E-mail (necessário para a cobrança)">
              <Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} placeholder="financeiro@empresa.com" />
            </Field>
            <Field label="Telefone">
              <Input value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="+55 11 99999-9999" />
            </Field>
            <Field label="Valor mensal (R$)">
              <Input type="number" min={0} step="0.01" value={form.monthly_value} onChange={(e) => set("monthly_value", e.target.value)} />
            </Field>
            <Field label="Dia de vencimento (1–31)">
              <Input type="number" min={1} max={31} value={form.due_date} onChange={(e) => set("due_date", e.target.value)} />
            </Field>
            <Field label="Forma de cobrança">
              <Select value={form.default_billing_type} onChange={(e) => set("default_billing_type", e.target.value)}>
                {BILLING_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
            <label className="flex items-end gap-2 pb-2 text-sm">
              <input type="checkbox" checked={form.billing_automation_enabled} onChange={(e) => set("billing_automation_enabled", e.target.checked)} />
              Gerar cobrança no gateway automaticamente
            </label>
          </div>
        </form>
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button variant="outline" onClick={onClose}>Cancelar</Button>
        <Button type="submit" form="client-form" disabled={legalMissing || save.isPending}>{save.isPending ? "Salvando…" : "Salvar"}</Button>
      </DialogFooter>
    </Dialog>
  );
}
