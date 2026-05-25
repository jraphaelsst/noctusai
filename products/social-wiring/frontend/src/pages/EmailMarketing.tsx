/**
 * Email Marketing — page-scoped CRUD for the email_marketing module's
 * routine owned data.
 *
 * The `email_marketing` backend module ships a full CRUD surface
 * (contacts / lists / templates / campaigns) under `/api/email-marketing/*`
 * but had NO frontend — managing those entities required raw SQL / direct
 * API calls. The product-internal-wiring rule
 * (`KB § PATTERNS/product-internal-wiring.md`) mandates that each page that
 * lists an owned entity also creates / edits / deletes it on that same page
 * (page-scoped CRUD; read-only ≠ managed; never raw SQL for routine data).
 *
 * This page wires the three SIMPLE owned entities — Contatos, Listas,
 * Templates — via the shared `<ResourceManager/>` (`@noctusai/lib/components`),
 * one tab each. Each tab is just the per-entity config (`columns` + `fields`);
 * the whole CRUD shell (list + create/edit modal + delete + toasts +
 * loading/empty/error states) lives in `ResourceManager`.
 *
 * Deliberately OUT of scope (need bespoke UIs beyond a config-driven shell —
 * surfaced as follow-up, not silently dropped):
 *   - Campaign composer + its send/schedule/pause lifecycle
 *     (`/api/email-marketing/campaigns` + `/ai/*` + analytics).
 *   - Automations (`/api/email-marketing/automations`).
 *   - Campaign analytics (`/api/email-marketing/analytics`) — read-only
 *     derived rollups (a carve-out, no write side by design).
 *   - List membership management (add/remove contacts from a list) — a
 *     relational sub-surface inside the Listas detail, not a top-level CRUD.
 */
import { Mail, Send, Users2, FileText } from "lucide-react";

import { api } from "@/lib/api";
import { ResourceManager } from "@noctusai/lib/components";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface ContactRow {
  id: string;
  email: string;
  nome: string | null;
  telefone: string | null;
  empresa: string | null;
  status: string | null;
  created_at: string;
}

interface ListRow {
  id: string;
  nome: string;
  descricao: string | null;
  tipo: string;
  created_at: string;
}

interface TemplateRow {
  id: string;
  nome: string;
  assunto: string;
  categoria: string;
  ativo: boolean;
  created_at: string;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("pt-BR");
}

// ─── Contatos tab ────────────────────────────────────────────────────
function ContactsTab() {
  return (
    <ResourceManager<ContactRow>
      title="Contatos"
      description="Gerencie a base de contatos para campanhas de email."
      api={api}
      apiPath="/api/email-marketing/contacts"
      singularName="Contato"
      columns={[
        { key: "email", header: "Email" },
        { key: "nome", header: "Nome", render: (r) => r.nome || "—" },
        { key: "empresa", header: "Empresa", render: (r) => r.empresa || "—" },
        { key: "status", header: "Status", render: (r) => r.status || "—" },
        {
          key: "created_at",
          header: "Criado em",
          render: (r) => formatDate(r.created_at),
        },
      ]}
      fields={[
        {
          name: "email",
          label: "Email",
          type: "email",
          required: true,
          placeholder: "contato@empresa.com",
          createOnly: true,
        },
        { name: "nome", label: "Nome", placeholder: "João Silva" },
        { name: "telefone", label: "Telefone", placeholder: "+5511999999999" },
        { name: "empresa", label: "Empresa", placeholder: "Empresa Exemplo" },
      ]}
    />
  );
}

// ─── Listas tab ──────────────────────────────────────────────────────
function ListsTab() {
  return (
    <ResourceManager<ListRow>
      title="Listas"
      description="Agrupe contatos em listas para segmentar envios."
      api={api}
      apiPath="/api/email-marketing/lists"
      singularName="Lista"
      columns={[
        { key: "nome", header: "Nome" },
        {
          key: "descricao",
          header: "Descrição",
          render: (r) => r.descricao || "—",
        },
        { key: "tipo", header: "Tipo", render: (r) => r.tipo || "—" },
        {
          key: "created_at",
          header: "Criado em",
          render: (r) => formatDate(r.created_at),
        },
      ]}
      fields={[
        {
          name: "nome",
          label: "Nome",
          required: true,
          placeholder: "Clientes ativos",
        },
        {
          name: "descricao",
          label: "Descrição",
          type: "textarea",
          placeholder: "Descrição opcional da lista",
        },
        {
          name: "tipo",
          label: "Tipo",
          type: "select",
          defaultValue: "static",
          createOnly: true,
          options: [
            { value: "static", label: "Estática" },
            { value: "dynamic", label: "Dinâmica" },
          ],
        },
      ]}
    />
  );
}

// ─── Templates tab ───────────────────────────────────────────────────
function TemplatesTab() {
  return (
    <ResourceManager<TemplateRow>
      title="Templates"
      description="Modelos de email reutilizáveis para suas campanhas."
      api={api}
      apiPath="/api/email-marketing/templates"
      singularName="Template"
      columns={[
        { key: "nome", header: "Nome" },
        { key: "assunto", header: "Assunto" },
        { key: "categoria", header: "Categoria", render: (r) => r.categoria || "—" },
        {
          key: "ativo",
          header: "Ativo",
          render: (r) => (r.ativo ? "Sim" : "Não"),
        },
        {
          key: "created_at",
          header: "Criado em",
          render: (r) => formatDate(r.created_at),
        },
      ]}
      fields={[
        {
          name: "nome",
          label: "Nome",
          required: true,
          placeholder: "Boas-vindas",
        },
        {
          name: "assunto",
          label: "Assunto",
          required: true,
          placeholder: "Bem-vindo à nossa newsletter",
        },
        {
          name: "corpo_html",
          label: "Corpo (HTML)",
          type: "textarea",
          required: true,
          placeholder: "<h1>Olá {{nome}}</h1><p>...</p>",
          help: "Use {{nome}}, {{email}}, {{empresa}} como variáveis.",
        },
        {
          name: "categoria",
          label: "Categoria",
          type: "select",
          defaultValue: "marketing",
          options: [
            { value: "marketing", label: "Marketing" },
            { value: "transactional", label: "Transacional" },
            { value: "newsletter", label: "Newsletter" },
          ],
        },
      ]}
    />
  );
}

export default function EmailMarketing() {
  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <Mail className="h-6 w-6 text-primary" />
          Email Marketing
        </h1>
        <p className="text-sm text-muted-foreground">
          Gerencie contatos, listas e templates. Composição de campanhas e
          automações chegam em uma próxima iteração.
        </p>
      </header>

      <Tabs defaultValue="contacts">
        <TabsList>
          <TabsTrigger value="contacts" className="gap-2">
            <Users2 className="h-4 w-4" />
            Contatos
          </TabsTrigger>
          <TabsTrigger value="lists" className="gap-2">
            <Send className="h-4 w-4" />
            Listas
          </TabsTrigger>
          <TabsTrigger value="templates" className="gap-2">
            <FileText className="h-4 w-4" />
            Templates
          </TabsTrigger>
        </TabsList>

        <TabsContent value="contacts" className="mt-4">
          <ContactsTab />
        </TabsContent>
        <TabsContent value="lists" className="mt-4">
          <ListsTab />
        </TabsContent>
        <TabsContent value="templates" className="mt-4">
          <TemplatesTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
