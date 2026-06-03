/**
 * Example page — the **canonical page-scoped-CRUD reference** every
 * scaffolded product inherits.
 *
 * It consumes the shared `<ResourceManager/>` (`@noctusai/lib/components`)
 * to list AND create / edit / soft-delete the `example` domain entity —
 * all from this one page, no raw SQL. This is the frontend half of the
 * product-internal-wiring rule's *page-scoped CRUD* mandate
 * (KB § PATTERNS/product-internal-wiring.md): the page that lists an
 * entity is the page that manages it.
 *
 * The whole CRUD shell (table + "Novo" button + create/edit modal +
 * delete confirm + toasts + loading/empty/error states) lives in
 * `<ResourceManager/>`; this page is just the per-entity config —
 * `columns` (display) + `fields` (form). That is the formalization of
 * the hand-rolled pattern (cf. core's `AdminPlans` ≈ 290 lines → this).
 *
 * TODO(new-product): rename `Example` → your domain page, point
 * `apiPath` at your endpoint, and replace the `title`/`description`
 * columns + fields with your real ones. Backend mirror:
 * `app/routers/example_router.py` + `app/services/example_service.py`
 * + migration `003_examples.sql`.
 */
import { api } from "@/lib/api";
import { ResourceManager } from "@noctusai/lib/components";

interface ExampleRow {
  id: string;
  org_id: string;
  title: string;
  description: string | null;
  ativo: boolean;
  created_at: string;
}

function formatDate(value: string): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("pt-BR");
}

export default function Example() {
  return (
    <ResourceManager<ExampleRow>
      title="Exemplos"
      api={api}
      apiPath="/api/example"
      singularName="Exemplo"
      deleteLabel="Desativar"
      columns={[
        { key: "title", header: "Título" },
        {
          key: "description",
          header: "Descrição",
          render: (row) => row.description || "—",
        },
        {
          key: "created_at",
          header: "Criado em",
          render: (row) => formatDate(row.created_at),
        },
      ]}
      fields={[
        {
          name: "title",
          label: "Título",
          required: true,
          placeholder: "Ex: Meu primeiro exemplo",
        },
        {
          name: "description",
          label: "Descrição",
          type: "textarea",
          placeholder: "Descrição opcional",
        },
      ]}
    />
  );
}
