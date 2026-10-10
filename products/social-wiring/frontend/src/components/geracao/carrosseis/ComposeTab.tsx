/**
 * Carrosséis › Novo post tab — moved from the legacy `MediaCreation` page
 * (esteira-contract §A.5 A-2). The kit dropdown now links to the Branding page.
 *
 * Loading/error/empty for the kit list: skeleton while the kits load, an
 * error with retry, and an empty state pointing at Branding.
 */
import { useState } from "react";
import { Loader2, Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type PostFormat, useBrandKits, usePosts } from "@/hooks/useMediaCreation";

/** Route of the CoreStudio Branding page (FE-Z mounts it). */
export const BRANDING_PATH = "/media-creation/branding";

// ─── Compose tab ─────────────────────────────────────────────────────

export function ComposeTab({ onCreated }: { onCreated: (id: string) => void }) {
  const { items: kits, loading: kitsLoading, error: kitsError, refresh: refreshKits } = useBrandKits();
  const kitsSkeleton = kitsLoading && kits.length === 0;
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
        {kitsError && kits.length === 0 && !kitsLoading && (
          <div
            role="alert"
            data-testid="compose-kits-error"
            className="flex items-center justify-between gap-2 rounded border border-destructive/40 p-4 text-sm"
          >
            <span className="text-destructive">Não foi possível carregar os kits de marca.</span>
            <Button size="sm" variant="outline" onClick={() => void refreshKits()}>
              Tentar novamente
            </Button>
          </div>
        )}
        {!kitsLoading && !kitsError && kits.length === 0 && (
          <p
            data-testid="compose-kits-empty"
            className="rounded border border-dashed p-4 text-sm text-muted-foreground"
          >
            Crie um branding primeiro na página{" "}
            <Link to={BRANDING_PATH} className="font-medium text-primary underline">
              Branding
            </Link>{" "}
            — todo post precisa de um kit.
          </p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <Label>Kit de marca</Label>
              <Link
                to={BRANDING_PATH}
                data-testid="compose-manage-branding"
                className="text-xs font-medium text-primary hover:underline"
              >
                Gerenciar branding →
              </Link>
            </div>
            {kitsSkeleton ? (
              <div data-testid="compose-kits-loading" aria-busy="true">
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
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
            )}
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
                <SelectItem value="reels">Reels (roteiro 9:16)</SelectItem>
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
