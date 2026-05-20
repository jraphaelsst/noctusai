/**
 * Media Creation — the media-PRODUCTION arm of the social-wiring product.
 *
 * Three tabs:
 *   - Biblioteca   : list of drafts / ready / published posts
 *   - Novo post    : compose → idea → 3-stage LLM generation pipeline
 *   - Kits de marca: persona + design system + references per brand
 *
 * The three generation stages — storyboard, image prompts, copy — each
 * call the backend's POST /api/media-creation/posts/{id}/generate/* and
 * persist artifacts on the post. Image RENDERING is gated until the
 * image-gen seed adapter ships; until then the operator copies prompts
 * into GalilAI / Nano Banana / Midjourney.
 */
import { useMemo, useState } from "react";
import {
  ImagePlus,
  Library,
  Loader2,
  Palette,
  Plus,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  type BrandKit,
  type BrandReference,
  type Post,
  type PostFormat,
  type ReferenceKind,
  useBrandKits,
  useBrandReferences,
  usePost,
  usePostGeneration,
  usePosts,
} from "@/hooks/useMediaCreation";

const STATUS_LABEL: Record<Post["status"], string> = {
  draft: "Rascunho",
  ready: "Pronto",
  published: "Publicado",
};

const STATUS_VARIANT: Record<Post["status"], "default" | "secondary" | "outline"> = {
  draft: "outline",
  ready: "secondary",
  published: "default",
};

const REFERENCE_KIND_LABEL: Record<ReferenceKind, string> = {
  model: "Post modelo",
  prompt: "Prompt exemplo",
  palette: "Paleta",
  typography: "Tipografia",
};

export default function MediaCreation() {
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"library" | "compose" | "brand">("library");

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <Wand2 className="h-6 w-6 text-primary" />
            Criação de mídia
          </h1>
          <p className="text-sm text-muted-foreground">
            A camada de produção do ecossistema de automação. Brief → roteiro
            → prompts → legenda. Os prompts saem prontos para o GalilAI / Nano
            Banana / Midjourney.
          </p>
        </div>
      </header>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
        <TabsList>
          <TabsTrigger value="library" className="gap-2">
            <Library className="h-4 w-4" />
            Biblioteca
          </TabsTrigger>
          <TabsTrigger value="compose" className="gap-2">
            <Plus className="h-4 w-4" />
            Novo post
          </TabsTrigger>
          <TabsTrigger value="brand" className="gap-2">
            <Palette className="h-4 w-4" />
            Kits de marca
          </TabsTrigger>
        </TabsList>

        <TabsContent value="library" className="mt-4">
          <LibraryTab
            selectedPostId={selectedPostId}
            onSelect={setSelectedPostId}
          />
        </TabsContent>

        <TabsContent value="compose" className="mt-4">
          <ComposeTab
            onCreated={(id) => {
              setSelectedPostId(id);
              setActiveTab("library");
            }}
          />
        </TabsContent>

        <TabsContent value="brand" className="mt-4">
          <BrandTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ─── Library tab ─────────────────────────────────────────────────────

function LibraryTab({
  selectedPostId,
  onSelect,
}: {
  selectedPostId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { items, loading, remove, refresh } = usePosts();

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Posts</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 p-2">
          {loading && (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          )}
          {!loading && items.length === 0 && (
            <p className="px-3 py-4 text-sm text-muted-foreground">
              Nenhum post ainda. Crie um na aba "Novo post".
            </p>
          )}
          {items.map((p) => (
            <button
              key={p.id}
              onClick={() => onSelect(p.id)}
              className={`w-full rounded px-3 py-2 text-left text-sm transition-colors ${
                selectedPostId === p.id ? "bg-primary/10" : "hover:bg-muted/50"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{p.title}</span>
                <Badge variant={STATUS_VARIANT[p.status]} className="shrink-0 text-[10px]">
                  {STATUS_LABEL[p.status]}
                </Badge>
              </div>
              <div className="mt-1 truncate text-xs text-muted-foreground">
                {p.idea}
              </div>
            </button>
          ))}
        </CardContent>
      </Card>

      <div>
        {selectedPostId ? (
          <PostDetail
            postId={selectedPostId}
            onDeleted={async () => {
              if (await remove(selectedPostId)) {
                onSelect(null);
                await refresh();
              }
            }}
          />
        ) : (
          <Card>
            <CardContent className="flex items-center justify-center p-12 text-muted-foreground">
              Selecione um post à esquerda para ver detalhes e gerar artefatos.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function PostDetail({
  postId,
  onDeleted,
}: {
  postId: string;
  onDeleted: () => void;
}) {
  const { post, loading, refresh } = usePost(postId);
  const { run, render, pending } = usePostGeneration(postId, refresh);

  if (loading || !post) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center p-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="text-lg">{post.title}</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">{post.idea}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant={STATUS_VARIANT[post.status]}>
                {STATUS_LABEL[post.status]}
              </Badge>
              <span>· {post.format}</span>
              <span>· {post.slide_count} slides</span>
              <span>· variante: {post.variant}</span>
              {post.brand_kit && <span>· kit: {post.brand_kit.name}</span>}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onDeleted}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <section>
          <h3 className="mb-2 text-sm font-semibold">Pipeline de geração</h3>
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => void run("storyboard")}
              disabled={pending !== null}
              size="sm"
              variant={post.storyboard ? "outline" : "default"}
            >
              {pending === "storyboard" ? (
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
              ) : (
                <Sparkles className="mr-2 h-3 w-3" />
              )}
              {post.storyboard ? "Regerar roteiro" : "1. Gerar roteiro"}
            </Button>
            <Button
              onClick={() => void run("prompts")}
              disabled={pending !== null || !post.storyboard}
              size="sm"
              variant={post.slides?.some((s) => s.prompt_nano_banana) ? "outline" : "default"}
            >
              {pending === "prompts" ? (
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
              ) : (
                <ImagePlus className="mr-2 h-3 w-3" />
              )}
              2. Gerar prompts
            </Button>
            <Button
              onClick={() => void run("copy")}
              disabled={pending !== null || !post.storyboard}
              size="sm"
              variant={post.copy_caption ? "outline" : "default"}
            >
              {pending === "copy" ? (
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
              ) : (
                <Sparkles className="mr-2 h-3 w-3" />
              )}
              3. Gerar legenda
            </Button>
            <Button
              onClick={() => void render()}
              disabled={pending !== null}
              size="sm"
              variant="secondary"
            >
              {pending === "render" && (
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
              )}
              Renderizar (em breve)
            </Button>
          </div>
        </section>

        {post.slides && post.slides.length > 0 && (
          <section>
            <h3 className="mb-2 text-sm font-semibold">Slides</h3>
            <div className="space-y-3">
              {post.slides.map((s) => (
                <Card key={s.id} className="bg-muted/30">
                  <CardContent className="space-y-2 p-4 text-sm">
                    <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
                      <span>Slide {s.slide_n}</span>
                      <Badge variant="outline" className="text-[10px]">
                        {s.role}
                      </Badge>
                    </div>
                    {s.headline && (
                      <div className="text-base font-medium">{s.headline}</div>
                    )}
                    {s.body && <p className="text-sm">{s.body}</p>}
                    {s.visual_brief && (
                      <p className="text-xs italic text-muted-foreground">
                        Visual: {s.visual_brief}
                      </p>
                    )}
                    {(s.prompt_nano_banana || s.prompt_galilai || s.prompt_midjourney) && (
                      <details className="mt-2">
                        <summary className="cursor-pointer text-xs font-medium text-primary">
                          Ver prompts de imagem
                        </summary>
                        <div className="mt-2 space-y-2">
                          {s.prompt_nano_banana && (
                            <PromptBlock label="Nano Banana" text={s.prompt_nano_banana} />
                          )}
                          {s.prompt_galilai && (
                            <PromptBlock label="GalilAI" text={s.prompt_galilai} />
                          )}
                          {s.prompt_midjourney && (
                            <PromptBlock label="Midjourney" text={s.prompt_midjourney} />
                          )}
                        </div>
                      </details>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        )}

        {post.copy_caption && (
          <section>
            <h3 className="mb-2 text-sm font-semibold">Legenda</h3>
            <Card className="bg-muted/30">
              <CardContent className="space-y-3 p-4 text-sm">
                <p className="whitespace-pre-wrap">{post.copy_caption}</p>
                {post.copy_hashtags && post.copy_hashtags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {post.copy_hashtags.map((h) => (
                      <Badge key={h} variant="outline" className="text-xs">
                        {h}
                      </Badge>
                    ))}
                  </div>
                )}
                {post.copy_alt_text && (
                  <p className="text-xs italic text-muted-foreground">
                    Alt: {post.copy_alt_text}
                  </p>
                )}
                {post.copy_first_comment && (
                  <p className="text-xs text-muted-foreground">
                    Primeiro comentário: {post.copy_first_comment}
                  </p>
                )}
              </CardContent>
            </Card>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

function PromptBlock({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded border bg-background p-2 text-xs">
      <div className="mb-1 font-mono text-[10px] uppercase text-muted-foreground">
        {label}
      </div>
      <pre className="whitespace-pre-wrap font-mono text-[11px]">{text}</pre>
      <Button
        size="sm"
        variant="ghost"
        className="mt-1 h-6 text-[10px]"
        onClick={() => {
          void navigator.clipboard.writeText(text);
        }}
      >
        Copiar
      </Button>
    </div>
  );
}

// ─── Compose tab ─────────────────────────────────────────────────────

function ComposeTab({ onCreated }: { onCreated: (id: string) => void }) {
  const { items: kits, loading: kitsLoading } = useBrandKits();
  const { create } = usePosts();

  const [form, setForm] = useState({
    brand_kit_id: "",
    title: "",
    idea: "",
    format: "carousel" as PostFormat,
    variant: "premium",
    slide_count: 5,
    cta: "",
    audience: "",
    key_message: "",
  });
  const [pending, setPending] = useState(false);

  const handleSubmit = async () => {
    if (!form.brand_kit_id || !form.title.trim() || !form.idea.trim()) return;
    setPending(true);
    const created = await create({
      brand_kit_id: form.brand_kit_id,
      title: form.title.trim(),
      idea: form.idea.trim(),
      format: form.format,
      variant: form.variant,
      slide_count: form.slide_count,
      cta: form.cta.trim() || undefined,
      audience: form.audience.trim() || undefined,
      key_message: form.key_message.trim() || undefined,
    });
    setPending(false);
    if (created) {
      setForm((f) => ({ ...f, title: "", idea: "", cta: "", audience: "", key_message: "" }));
      onCreated(created.id);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Compor novo post</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {!kitsLoading && kits.length === 0 && (
          <p className="rounded border border-dashed p-4 text-sm text-muted-foreground">
            Crie um kit de marca primeiro na aba "Kits de marca" — todo post
            precisa de um kit.
          </p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <Label>Kit de marca</Label>
            <Select
              value={form.brand_kit_id}
              onValueChange={(v) => setForm((f) => ({ ...f, brand_kit_id: v }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Selecione um kit" />
              </SelectTrigger>
              <SelectContent>
                {kits.map((k) => (
                  <SelectItem key={k.id} value={k.id}>
                    {k.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label>Formato</Label>
            <Select
              value={form.format}
              onValueChange={(v) => setForm((f) => ({ ...f, format: v as PostFormat }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="carousel">Carrossel</SelectItem>
                <SelectItem value="single">Imagem única</SelectItem>
                <SelectItem value="video" disabled>
                  Vídeo (em breve)
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1 sm:col-span-2">
            <Label>Título de trabalho</Label>
            <Input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="3 condomínios em Cotia que você deveria conhecer"
            />
          </div>

          <div className="space-y-1 sm:col-span-2">
            <Label>Ideia / brief</Label>
            <Textarea
              value={form.idea}
              onChange={(e) => setForm((f) => ({ ...f, idea: e.target.value }))}
              rows={3}
              placeholder="Conte aqui a ideia bruta. O LLM transforma em roteiro estruturado."
            />
          </div>

          <div className="space-y-1">
            <Label>Variante</Label>
            <Select
              value={form.variant}
              onValueChange={(v) => setForm((f) => ({ ...f, variant: v }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="premium">Premium</SelectItem>
                <SelectItem value="educational">Educativa</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label>Nº de slides</Label>
            <Input
              type="number"
              min={1}
              max={20}
              value={form.slide_count}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  slide_count: Math.max(1, Math.min(20, Number(e.target.value) || 1)),
                }))
              }
            />
          </div>

          <div className="space-y-1">
            <Label>Público-alvo (opcional)</Label>
            <Input
              value={form.audience}
              onChange={(e) => setForm((f) => ({ ...f, audience: e.target.value }))}
              placeholder="Compradores 35-55, alta renda, Cotia"
            />
          </div>

          <div className="space-y-1">
            <Label>Mensagem-chave (opcional)</Label>
            <Input
              value={form.key_message}
              onChange={(e) => setForm((f) => ({ ...f, key_message: e.target.value }))}
              placeholder="Uma sentença que resuma o que o leitor deve levar."
            />
          </div>

          <div className="space-y-1 sm:col-span-2">
            <Label>CTA (opcional)</Label>
            <Input
              value={form.cta}
              onChange={(e) => setForm((f) => ({ ...f, cta: e.target.value }))}
              placeholder='"Mande DM ‘Cotia’ para receber o tour completo"'
            />
          </div>
        </div>

        <Button
          onClick={handleSubmit}
          disabled={pending || !form.brand_kit_id || !form.title.trim() || !form.idea.trim()}
        >
          {pending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Plus className="mr-2 h-4 w-4" />
          )}
          Criar rascunho
        </Button>
      </CardContent>
    </Card>
  );
}

// ─── Brand tab ───────────────────────────────────────────────────────

function BrandTab() {
  const { items, loading, create, update, remove } = useBrandKits();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const selected = useMemo(
    () => items.find((k) => k.id === selectedId) ?? null,
    [items, selectedId],
  );

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Kits</CardTitle>
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="mr-1 h-3 w-3" />
            Novo kit
          </Button>
        </CardHeader>
        <CardContent className="space-y-1 p-2">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          )}
          {items.map((k) => (
            <button
              key={k.id}
              onClick={() => {
                setSelectedId(k.id);
                setCreating(false);
              }}
              className={`w-full rounded px-3 py-2 text-left text-sm transition-colors ${
                selectedId === k.id ? "bg-primary/10" : "hover:bg-muted/50"
              }`}
            >
              <div className="font-medium">{k.name}</div>
              <div className="truncate text-xs text-muted-foreground">
                {k.default_lang}
              </div>
            </button>
          ))}
        </CardContent>
      </Card>

      <div>
        {creating ? (
          <NewKitForm
            onCancel={() => setCreating(false)}
            onCreated={async (input) => {
              const k = await create(input);
              if (k) {
                setCreating(false);
                setSelectedId(k.id);
              }
            }}
          />
        ) : selected ? (
          <KitEditor
            kit={selected}
            onSave={(patch) => update(selected.id, patch)}
            onDelete={async () => {
              if (await remove(selected.id)) setSelectedId(null);
            }}
          />
        ) : (
          <Card>
            <CardContent className="flex items-center justify-center p-12 text-muted-foreground">
              Selecione um kit ou crie um novo.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function NewKitForm({
  onCancel,
  onCreated,
}: {
  onCancel: () => void;
  onCreated: (input: { name: string; persona?: string; design_system?: string; default_lang?: string }) => void;
}) {
  const [name, setName] = useState("");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Novo kit de marca</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <Label>Nome</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Granja Premium"
          />
        </div>
        <div className="flex gap-2">
          <Button
            disabled={!name.trim()}
            onClick={() => onCreated({ name: name.trim() })}
          >
            Criar
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function KitEditor({
  kit,
  onSave,
  onDelete,
}: {
  kit: BrandKit;
  onSave: (patch: { persona?: string; design_system?: string; default_lang?: string; name?: string }) => Promise<boolean>;
  onDelete: () => void;
}) {
  const [persona, setPersona] = useState(kit.persona);
  const [design, setDesign] = useState(kit.design_system);
  const [name, setName] = useState(kit.name);
  const dirty = persona !== kit.persona || design !== kit.design_system || name !== kit.name;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <CardTitle className="text-base">{kit.name}</CardTitle>
          <Button variant="ghost" size="sm" onClick={onDelete}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <Label>Nome</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label>Persona</Label>
          <Textarea
            rows={6}
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            placeholder="Voz: editorial, calma, premium. Vocabulário: ..."
            className="font-mono text-xs"
          />
          <p className="text-xs text-muted-foreground">
            Texto livre — pode ser o conteúdo do seu PERSONA.md.
          </p>
        </div>
        <div className="space-y-1">
          <Label>Design system</Label>
          <Textarea
            rows={6}
            value={design}
            onChange={(e) => setDesign(e.target.value)}
            placeholder="Paleta: bg #2A2620 · gold #C5A55E · texto #F5F1EA ..."
            className="font-mono text-xs"
          />
          <p className="text-xs text-muted-foreground">
            Texto livre — pode ser o conteúdo do seu DESIGN-SYSTEM.md.
          </p>
        </div>
        <Button
          disabled={!dirty}
          onClick={() =>
            void onSave({ name, persona, design_system: design })
          }
        >
          Salvar alterações
        </Button>

        <ReferencesPanel kitId={kit.id} />
      </CardContent>
    </Card>
  );
}

function ReferencesPanel({ kitId }: { kitId: string }) {
  const { items, add, remove } = useBrandReferences(kitId);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<{
    kind: ReferenceKind;
    label: string;
    asset_url: string;
    notes: string;
  }>({
    kind: "model",
    label: "",
    asset_url: "",
    notes: "",
  });

  return (
    <div className="border-t pt-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-semibold">Referências ({items.length})</h4>
        <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}>
          {open ? "Cancelar" : "Adicionar"}
        </Button>
      </div>

      {open && (
        <div className="mb-3 grid gap-2 rounded border bg-muted/30 p-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label className="text-xs">Tipo</Label>
            <Select
              value={draft.kind}
              onValueChange={(v) => setDraft((d) => ({ ...d, kind: v as ReferenceKind }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(REFERENCE_KIND_LABEL) as ReferenceKind[]).map((k) => (
                  <SelectItem key={k} value={k}>
                    {REFERENCE_KIND_LABEL[k]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Rótulo</Label>
            <Input
              value={draft.label}
              onChange={(e) => setDraft((d) => ({ ...d, label: e.target.value }))}
              placeholder="post1 — cover slide"
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label className="text-xs">URL do ativo</Label>
            <Input
              value={draft.asset_url}
              onChange={(e) => setDraft((d) => ({ ...d, asset_url: e.target.value }))}
              placeholder="https://..."
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label className="text-xs">Notas (opcional)</Label>
            <Input
              value={draft.notes}
              onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
            />
          </div>
          <Button
            size="sm"
            disabled={!draft.label.trim()}
            onClick={async () => {
              const ok = await add({
                kind: draft.kind,
                label: draft.label.trim(),
                asset_url: draft.asset_url.trim() || undefined,
                notes: draft.notes.trim() || undefined,
              });
              if (ok) {
                setOpen(false);
                setDraft({ kind: "model", label: "", asset_url: "", notes: "" });
              }
            }}
          >
            Adicionar
          </Button>
        </div>
      )}

      <div className="space-y-2">
        {items.map((r: BrandReference) => (
          <div
            key={r.id}
            className="flex items-start justify-between gap-2 rounded border bg-background p-2 text-xs"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {REFERENCE_KIND_LABEL[r.kind]}
                </Badge>
                <span className="font-medium">{r.label}</span>
              </div>
              {r.asset_url && (
                <a
                  href={r.asset_url}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate text-primary"
                >
                  {r.asset_url}
                </a>
              )}
              {r.notes && (
                <p className="text-muted-foreground">{r.notes}</p>
              )}
            </div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void remove(r.id)}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Nenhuma referência ainda. Adicione modelos / paletas / tipografia /
            prompts exemplo — o LLM vai citá-los nos artefatos gerados.
          </p>
        )}
      </div>
    </div>
  );
}
