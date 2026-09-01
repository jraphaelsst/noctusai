/**
 * Email Marketing · Templates — the own-engine template library.
 *
 *   GET|POST     /api/email-marketing/templates
 *   PATCH|DELETE /api/email-marketing/templates/{id}
 *   POST         /api/email-marketing/templates/{id}/preview
 *   POST         /api/email-marketing/ai/template-draft
 *   POST         /api/email-marketing/ai/deliverability
 *   POST         /api/email-marketing/ai/translate
 *
 * CRUD is the `<ResourceManager/>` organ. The three things it cannot express —
 * rendering a preview, drafting HTML from a prompt, and the deliverability /
 * translation assists — sit beside it as their own panels.
 *
 * Route: /email/templates (`email_templates_noc` status_pagina, migration 085).
 */
import { useState } from "react";
import { toast } from "sonner";
import { Eye, Languages, ShieldCheck, Sparkles } from "lucide-react";

import { ResourceManager } from "@noctusai/lib/components";
import { api } from "@/lib/api";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import {
  useEmAi,
  useEmTemplateMutations,
  useEmTemplates,
  type EmTemplate,
} from "@/hooks/useEmailMarketing";

const CATEGORIA_LABEL: Record<string, string> = {
  marketing: "Marketing",
  transactional: "Transacional",
  follow_up: "Follow-up",
  newsletter: "Newsletter",
};

// ─── Preview ─────────────────────────────────────────────────────────────────

function PreviewPanel() {
  const templates = useEmTemplates();
  const { preview } = useEmTemplateMutations();
  const [id, setId] = useState("");
  const [result, setResult] = useState<{ assunto: string; html: string } | null>(
    null,
  );

  function run() {
    if (!id) return;
    preview.mutate(
      { id, variaveis: {} },
      {
        onSuccess: (res: any) => setResult(res?.data ?? res ?? null),
        onError: () => toast.error("Não foi possível renderizar o preview."),
      },
    );
  }

  return (
    <Card data-testid="templates-preview">
      <CardHeader>
        <CardTitle className="text-base">Pré-visualizar</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Select value={id} onValueChange={setId}>
            <SelectTrigger data-testid="preview-pick">
              <SelectValue placeholder="Escolha um template" />
            </SelectTrigger>
            <SelectContent>
              {(templates.data ?? []).map((t: EmTemplate) => (
                <SelectItem key={t.id} value={t.id}>
                  {t.nome}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={run}
            disabled={!id || preview.isPending}
            data-testid="preview-run"
          >
            <Eye className="mr-2 h-4 w-4" />
            {preview.isPending ? "Renderizando…" : "Ver"}
          </Button>
        </div>

        {result ? (
          <div data-testid="preview-result" className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Assunto: <span className="font-medium">{result.assunto}</span>
            </p>
            {/* Rendered inside a sandboxed iframe: the HTML is authored by the
                org's own operators, but it is still untrusted markup that must
                never execute against this origin. */}
            <iframe
              title="Pré-visualização do template"
              sandbox=""
              srcDoc={result.html}
              className="h-80 w-full rounded border bg-white"
            />
          </div>
        ) : (
          <p
            className="py-6 text-center text-xs text-muted-foreground"
            data-testid="preview-idle"
          >
            Escolha um template para ver como ele chega na caixa de entrada.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ─── AI assists ──────────────────────────────────────────────────────────────

function AiPanel() {
  const ai = useEmAi();
  const [prompt, setPrompt] = useState("");
  const [html, setHtml] = useState("");
  const [lang, setLang] = useState("en");
  const [out, setOut] = useState<string | null>(null);

  const show = (res: any) =>
    setOut(JSON.stringify(res?.data ?? res ?? {}, null, 2));

  return (
    <Card data-testid="templates-ai">
      <CardHeader>
        <CardTitle className="text-base">Assistentes de IA</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="ai-prompt">Rascunhar um template</Label>
          <Textarea
            id="ai-prompt"
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="ex.: convite para visitar o lançamento na zona sul"
            data-testid="ai-prompt"
          />
          <Button
            size="sm"
            disabled={!prompt.trim() || ai.templateDraft.isPending}
            onClick={() =>
              ai.templateDraft.mutate(prompt.trim(), {
                onSuccess: show,
                onError: () => toast.error("Falha ao rascunhar."),
              })
            }
            data-testid="ai-draft-run"
          >
            <Sparkles className="mr-2 h-3.5 w-3.5" />
            Rascunhar
          </Button>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="ai-html">HTML para analisar / traduzir</Label>
          <Textarea
            id="ai-html"
            rows={4}
            value={html}
            onChange={(e) => setHtml(e.target.value)}
            data-testid="ai-html"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!html.trim() || ai.deliverability.isPending}
              onClick={() =>
                ai.deliverability.mutate(
                  { html: html.trim() },
                  {
                    onSuccess: show,
                    onError: () => toast.error("Falha na análise."),
                  },
                )
              }
              data-testid="ai-deliverability-run"
            >
              <ShieldCheck className="mr-2 h-3.5 w-3.5" />
              Entregabilidade
            </Button>

            <Select value={lang} onValueChange={setLang}>
              <SelectTrigger className="w-32" data-testid="ai-lang">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">Inglês</SelectItem>
                <SelectItem value="es">Espanhol</SelectItem>
                <SelectItem value="fr">Francês</SelectItem>
              </SelectContent>
            </Select>

            <Button
              size="sm"
              variant="outline"
              disabled={!html.trim() || ai.translate.isPending}
              onClick={() =>
                ai.translate.mutate(
                  { html: html.trim(), targetLang: lang },
                  {
                    onSuccess: show,
                    onError: () => toast.error("Falha ao traduzir."),
                  },
                )
              }
              data-testid="ai-translate-run"
            >
              <Languages className="mr-2 h-3.5 w-3.5" />
              Traduzir
            </Button>
          </div>
        </div>

        {out && (
          <pre
            className="max-h-64 overflow-auto rounded bg-muted p-3 text-xs"
            data-testid="ai-output"
          >
            {out}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}

export default function EmailTemplatesNoc() {
  return (
    <div className="flex flex-col gap-8 p-6" data-testid="email-templates-page">
      <ResourceManager<EmTemplate>
        title="Templates"
        description="Modelos de e-mail do motor de envio próprio."
        api={api}
        apiPath="/api/email-marketing/templates"
        singularName="Template"
        emptyMessage="Nenhum template ainda."
        columns={[
          { key: "nome", header: "Nome" },
          { key: "assunto", header: "Assunto" },
          {
            key: "categoria",
            header: "Categoria",
            render: (r) => CATEGORIA_LABEL[r.categoria] ?? r.categoria,
          },
          { key: "ativo", header: "Ativo", render: (r) => (r.ativo ? "Sim" : "Não") },
        ]}
        fields={[
          { name: "nome", label: "Nome", required: true },
          { name: "assunto", label: "Assunto", required: true },
          { name: "corpo_html", label: "Corpo (HTML)", type: "textarea", required: true },
          { name: "corpo_text", label: "Corpo (texto)", type: "textarea" },
          {
            name: "categoria",
            label: "Categoria",
            type: "select",
            defaultValue: "marketing",
            options: Object.entries(CATEGORIA_LABEL).map(([value, label]) => ({
              value,
              label,
            })),
          },
          { name: "ativo", label: "Ativo", type: "checkbox", defaultValue: true },
        ]}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <PreviewPanel />
        <AiPanel />
      </div>
    </div>
  );
}
