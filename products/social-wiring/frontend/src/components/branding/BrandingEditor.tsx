/**
 * BrandingEditor — edit a branding: name, marca, persona, design-system prose,
 * brand book (markdown), extra sections and the tokens (JSON, validated by the
 * server — its message is shown verbatim).
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button, Field, FormError, Input, Select, Textarea } from "@noctusai/lib/design-system";

import {
  useUpdateBranding,
  type BrandingDetail,
  type BrandingSection,
  type UpdateBrandingInput,
} from "@/hooks/useBranding";
import { useMarcas } from "@/hooks/useMarcas";
import type { BrandingTokens } from "@/lib/branding";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function BrandingEditor({ branding, onSaved }: { branding: BrandingDetail; onSaved?: () => void }) {
  const update = useUpdateBranding(branding.id);
  const marcas = useMarcas();
  const [name, setName] = useState(branding.name);
  const [marcaId, setMarcaId] = useState<string>(branding.marca_id ?? "");
  const [persona, setPersona] = useState(branding.persona ?? "");
  const [designSystem, setDesignSystem] = useState(branding.design_system ?? "");
  const [book, setBook] = useState(branding.brand_book ?? "");
  const [sections, setSections] = useState<BrandingSection[]>(branding.sections ?? []);
  const initialTokens = useMemo(
    () => (branding.tokens ? JSON.stringify(branding.tokens, null, 2) : ""),
    [branding.tokens],
  );
  const [tokensText, setTokensText] = useState(initialTokens);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setError(null);
    const patch: UpdateBrandingInput = {};
    if (name.trim() !== branding.name) patch.name = name.trim();
    if (!branding.is_template && marcaId !== (branding.marca_id ?? "")) patch.marca_id = marcaId || null;
    if (persona !== (branding.persona ?? "")) patch.persona = persona;
    if (designSystem !== (branding.design_system ?? "")) patch.design_system = designSystem;
    if (book !== (branding.brand_book ?? "")) patch.brand_book = book;
    if (JSON.stringify(sections) !== JSON.stringify(branding.sections ?? [])) patch.sections = sections;
    if (tokensText !== initialTokens) {
      try {
        patch.tokens = JSON.parse(tokensText) as BrandingTokens;
      } catch (err) {
        setError(`Tokens: JSON inválido (${(err as Error).message})`);
        return;
      }
    }
    if (Object.keys(patch).length === 0) {
      toast.info("Nada a salvar");
      return;
    }
    try {
      await update.mutateAsync(patch);
      toast.success("Branding atualizado");
      onSaved?.();
    } catch (err) {
      setError(mensagemErroServidor(err, "Falha ao salvar o branding"));
    }
  };

  const setSection = (i: number, next: Partial<BrandingSection>) =>
    setSections((list) => list.map((s, idx) => (idx === i ? { ...s, ...next } : s)));

  return (
    <section data-testid="branding-editor" className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Nome" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} data-testid="branding-edit-name" />
        </Field>
        {!branding.is_template && (
          <Field label="Marca">
            <Select
              value={marcaId}
              onChange={(e) => setMarcaId(e.target.value)}
              disabled={marcas.isPending && !marcas.data}
              data-testid="branding-edit-marca"
            >
              <option value="">— sem marca —</option>
              {(marcas.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </Select>
          </Field>
        )}
      </div>
      <Field label="Persona (voz da marca — lida pela geração de posts)">
        <Textarea monospace rows={5} value={persona} onChange={(e) => setPersona(e.target.value)} />
      </Field>
      <Field label="Design system (texto livre — lido pela geração de posts)">
        <Textarea monospace rows={5} value={designSystem} onChange={(e) => setDesignSystem(e.target.value)} />
      </Field>
      <Field label="Brand book (markdown)">
        <Textarea monospace rows={12} value={book} onChange={(e) => setBook(e.target.value)} data-testid="branding-edit-book" />
      </Field>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold">Seções extras ({sections.length})</h4>
          <Button size="sm" variant="outline" onClick={() => setSections((l) => [...l, { title: "Nova seção", markdown: "" }])}>
            Adicionar seção
          </Button>
        </div>
        {sections.map((s, i) => (
          <div key={i} className="space-y-2 rounded-md border p-2">
            <div className="flex gap-2">
              <Input value={s.title} onChange={(e) => setSection(i, { title: e.target.value })} aria-label="Título da seção" />
              <Button size="sm" variant="ghost" onClick={() => setSections((l) => l.filter((_, idx) => idx !== i))}>
                Remover
              </Button>
            </div>
            <Textarea monospace rows={6} value={s.markdown} onChange={(e) => setSection(i, { markdown: e.target.value })} />
          </div>
        ))}
      </div>

      <Field label="Tokens (JSON — validado pelo servidor)">
        <Textarea
          monospace
          rows={16}
          value={tokensText}
          onChange={(e) => setTokensText(e.target.value)}
          placeholder="Sem tokens — importe um design system ou cole o tokens.json"
          data-testid="branding-edit-tokens"
        />
      </Field>

      <FormError message={error} />
      <Button variant="primary" disabled={update.isPending || !name.trim()} onClick={() => void save()} data-testid="branding-edit-save">
        {update.isPending ? "Salvando…" : "Salvar alterações"}
      </Button>
    </section>
  );
}
