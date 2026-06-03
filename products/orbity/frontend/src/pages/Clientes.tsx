/**
 * Clientes — client list + full page-scoped CRUD (create / edit / archive).
 *
 * Uses ResourceManager from @noctusai/lib/components (the canonical
 * page-scoped-CRUD organ) wired to /api/clients.
 *
 * The backend uses POST /api/clients/{id}/archive (soft-delete), not DELETE.
 * We set canDelete=false and supply a rowActions prop that posts to the
 * archive endpoint so ResourceManager stays the owner of all CRUD UI.
 *
 * All 4 states (loading / empty / error / success) are owned by ResourceManager.
 *
 * Nav key: "clientes" — needs a status_pagina row (see return note).
 */
import { api } from "@/lib/api";
import { ResourceManager } from "@noctusai/lib/components";
import { Archive } from "lucide-react";
import { toast } from "sonner";

interface ClientRow {
  id: string;
  org_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  company: string | null;
  monthly_value: number | null;
  due_date: number | null;
  active: boolean;
  default_billing_type: string | null;
  billing_automation_enabled: boolean;
  created_at: string;
  updated_at: string;
}

function formatCurrency(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

function formatDate(value: string): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("pt-BR");
}

async function archiveClient(id: string, reload: () => void) {
  if (!window.confirm("Arquivar este cliente?")) return;
  try {
    await api.post(`/api/clients/${id}/archive`, {});
    toast.success("Cliente arquivado");
    reload();
  } catch (err: unknown) {
    toast.error("Falha ao arquivar cliente", {
      description: err instanceof Error ? err.message : undefined,
    });
  }
}

export default function Clientes() {
  return (
    <ResourceManager<ClientRow>
      title="Clientes"
      description="Gerencie os clientes da agência"
      api={api}
      apiPath="/api/clients"
      singularName="Cliente"
      canDelete={false}
      emptyMessage="Nenhum cliente cadastrado ainda."
      rowActions={(row, reload) => (
        <button
          type="button"
          onClick={() => archiveClient(row.id, reload)}
          title="Arquivar"
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:text-amber-600 hover:bg-amber-50 transition-colors"
        >
          <Archive className="h-3.5 w-3.5" />
          Arquivar
        </button>
      )}
      columns={[
        { key: "name", header: "Nome" },
        {
          key: "company",
          header: "Empresa",
          render: (row) => row.company ?? "—",
        },
        {
          key: "email",
          header: "E-mail",
          render: (row) => row.email ?? "—",
        },
        {
          key: "phone",
          header: "Telefone",
          render: (row) => row.phone ?? "—",
        },
        {
          key: "monthly_value",
          header: "Valor Mensal",
          render: (row) => formatCurrency(row.monthly_value),
        },
        {
          key: "active",
          header: "Status",
          render: (row) =>
            row.active ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                Ativo
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
                Arquivado
              </span>
            ),
        },
        {
          key: "created_at",
          header: "Criado em",
          render: (row) => formatDate(row.created_at),
        },
      ]}
      fields={[
        {
          name: "name",
          label: "Nome",
          required: true,
          placeholder: "Nome do cliente",
        },
        {
          name: "company",
          label: "Empresa",
          placeholder: "Razão social ou nome fantasia",
        },
        {
          name: "email",
          label: "E-mail",
          type: "email",
          placeholder: "contato@empresa.com",
        },
        {
          name: "phone",
          label: "Telefone",
          placeholder: "+55 11 99999-9999",
        },
        {
          name: "monthly_value",
          label: "Valor Mensal (R$)",
          type: "number",
          placeholder: "0.00",
        },
        {
          name: "due_date",
          label: "Dia de Vencimento",
          type: "number",
          help: "Dia do mês (1–31)",
        },
        {
          name: "default_billing_type",
          label: "Tipo de Cobrança",
          type: "select",
          options: [
            { value: "", label: "Selecione..." },
            { value: "boleto", label: "Boleto" },
            { value: "pix", label: "Pix" },
            { value: "cartao", label: "Cartão" },
            { value: "transferencia", label: "Transferência" },
          ],
        },
        {
          name: "billing_automation_enabled",
          label: "Automação de Cobrança",
          type: "checkbox",
        },
      ]}
    />
  );
}
