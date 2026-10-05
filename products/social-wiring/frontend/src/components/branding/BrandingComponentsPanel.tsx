/**
 * Components of a branding: guideline (markdown) + sandboxed preview, with
 * add / edit / delete. Previews render ONLY in a sandboxed iframe.
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { MarkdownRenderer } from "@noctusai/lib/components";
import { Button, EmptyState, Field, FormError, Input, Textarea } from "@noctusai/lib/design-system";

import {
  useDeleteComponent,
  useUpsertComponent,
  type BrandingAsset,
  type BrandingComponent,
} from "@/hooks/useBranding";
import type { BrandingTokens, PreviewFont } from "@/lib/branding";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { SandboxedPreview } from "./SandboxedPreview";

/** Font files uploaded with the branding, matched to `tokens.type.fonts[].file`. */
export function previewFonts(tokens: BrandingTokens, assets: BrandingAsset[]): PreviewFont[] {
  const byLabel = new Map(assets.filter((a) => a.kind === "font" && a.signed_url).map((a) => [a.label, a.signed_url!]));
  const out: PreviewFont[] = [];
  for (const f of tokens.type?.fonts ?? []) {
    const url = byLabel.get(f.file.split("/").pop() ?? f.file);
    if (url) out.push({ family: f.family, weight: f.weight, url });
  }
  return out;
}

function ComponentForm({
  brandingId,
  initial,
  onDone,
}: {
  brandingId: string;
  initial?: BrandingComponent;
  onDone: () => void;
}) {
  const upsert = useUpsertComponent(brandingId);
  const [name, setName] = useState(initial?.name ?? "");
  const [guideline, setGuideline] = useState(initial?.guideline_md ?? "");
  const [html, setHtml] = useState(initial?.preview_html ?? "");
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setError(null);
    try {
      await upsert.mutateAsync({ name: name.trim(), guideline_md: guideline, preview_html: html });
      toast.success("Componente salvo");
      onDone();
    } catch (err) {
      setError(mensagemErroServidor(err, "Falha ao salvar o componente"));
    }
  };

  return (
    <div className="space-y-3 rounded-md border bg-muted/30 p-3" data-testid="branding-component-form">
      <Field label="Nome" required>
        <Input value={name} onChange={(e) => setName(e.target.value)} disabled={!!initial} placeholder="Button" />
      </Field>
      <Field label="Guideline (markdown)">
        <Textarea monospace rows={6} value={guideline} onChange={(e) => setGuideline(e.target.value)} />
      </Field>
      <Field label="Pré-visualização (HTML + CSS, sem scripts)">
        <Textarea monospace rows={6} value={html} onChange={(e) => setHtml(e.target.value)} />
      </Field>
      <FormError message={error} />
      <div className="flex gap-2">
        <Button variant="primary" size="sm" disabled={!name.trim() || upsert.isPending} onClick={() => void save()}>
          {upsert.isPending ? "Salvando…" : "Salvar componente"}
        </Button>
        <Button variant="ghost" size="sm" onClick={onDone}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}

export function BrandingComponentsPanel({
  brandingId,
  tokens,
  themeId,
  components,
  assets,
}: {
  brandingId: string;
  tokens: BrandingTokens | null;
  themeId: string;
  components: BrandingComponent[];
  assets: BrandingAsset[];
}) {
  const del = useDeleteComponent(brandingId);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const fonts = useMemo(() => (tokens ? previewFonts(tokens, assets) : []), [tokens, assets]);

  return (
    <section data-testid="branding-components" className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => setEditing("new")}>
          Novo componente
        </Button>
      </div>
      {editing === "new" && <ComponentForm brandingId={brandingId} onDone={() => setEditing(null)} />}
      {components.length === 0 && editing !== "new" ? (
        <EmptyState message="Nenhum componente. Importe um design system ou adicione um." />
      ) : (
        components.map((c) => (
          <article key={c.id} className="space-y-3 rounded-md border p-3" data-testid={`branding-component-${c.name}`}>
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-sm font-semibold">{c.name}</h4>
              <div className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => setEditing(c.id)}>
                  Editar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={del.isPending}
                  onClick={() =>
                    del.mutate(c.id, {
                      onError: (err) => toast.error(mensagemErroServidor(err, "Falha ao remover o componente")),
                    })
                  }
                >
                  Remover
                </Button>
              </div>
            </div>
            {editing === c.id ? (
              <ComponentForm brandingId={brandingId} initial={c} onDone={() => setEditing(null)} />
            ) : (
              <>
                {c.guideline_md && <MarkdownRenderer content={c.guideline_md} />}
                {c.preview_html ? (
                  tokens ? (
                    <SandboxedPreview name={c.name} html={c.preview_html} tokens={tokens} themeId={themeId} fonts={fonts} />
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Este branding ainda não tem tokens — a pré-visualização precisa deles.
                    </p>
                  )
                ) : (
                  <p className="text-xs text-muted-foreground">Sem pré-visualização.</p>
                )}
              </>
            )}
          </article>
        ))
      )}
    </section>
  );
}
