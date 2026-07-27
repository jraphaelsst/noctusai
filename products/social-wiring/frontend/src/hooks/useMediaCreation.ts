/**
 * Hooks for the media_creation module — brand kits + posts + generation.
 *
 * The backend wraps responses in {ok, data} via success_response(). We
 * unwrap at the boundary so component code stays envelope-free.
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@noctusai/seed/infra";
import { toast } from "sonner";

// ─── Types (mirror backend Pydantic models) ──────────────────────────

export interface BrandKit {
  id: string;
  org_id: string;
  name: string;
  persona: string;
  design_system: string;
  default_lang: string;
  created_at: string;
  updated_at: string;
}

export interface BrandKitInput {
  name: string;
  persona?: string;
  design_system?: string;
  default_lang?: string;
}

export type ReferenceKind = "model" | "prompt" | "palette" | "typography";

export interface BrandReference {
  id: string;
  org_id: string;
  brand_kit_id: string;
  kind: ReferenceKind;
  label: string;
  asset_url?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface ReferenceInput {
  kind: ReferenceKind;
  label: string;
  asset_url?: string;
  notes?: string;
}

export type PostFormat = "carousel" | "single" | "reels" | "video";
export type PostStatus = "draft" | "ready" | "published";
// Método Audience role skeleton + legacy roles (back-compat).
export type SlideRole =
  | "capa"
  | "identificacao"
  | "virada"
  | "nome"
  | "prova"
  | "valor"
  | "cta"
  | "cover"
  | "develop"
  | "insight";

/** Storyboard JSON blob persisted on the post (Método Audience metadata). */
export interface Storyboard {
  title?: string;
  audience?: string;
  key_message?: string;
  cta?: string;
  format?: string;
  trigger_dominant?: string;
  triggers_embedded?: string[];
  templates?: string[];
  arc_pattern?: string;
  rationale?: string;
  slides?: unknown[];
}

export interface PostSlide {
  id: string;
  post_id: string;
  slide_n: number;
  role: SlideRole;
  headline?: string | null;
  body?: string | null;
  visual_brief?: string | null;
  prompt_nano_banana?: string | null;
  prompt_galilai?: string | null;
  prompt_midjourney?: string | null;
  image_url?: string | null;
  image_renderer?: string | null;
}

export interface Post {
  id: string;
  org_id: string;
  brand_kit_id: string;
  title: string;
  idea: string;
  format: PostFormat;
  variant: string;
  slide_count: number;
  cta?: string | null;
  audience?: string | null;
  key_message?: string | null;
  status: PostStatus;
  storyboard?: Storyboard | null;
  copy_caption?: string | null;
  copy_hashtags?: string[] | null;
  copy_alt_text?: string | null;
  copy_first_comment?: string | null;
  created_at: string;
  updated_at: string;
  // Aggregated on GET /posts/:id
  slides?: PostSlide[];
  brand_kit?: Pick<BrandKit, "id" | "name" | "persona" | "design_system" | "default_lang"> | null;
}

export interface PostInput {
  brand_kit_id: string;
  title: string;
  idea: string;
  format?: PostFormat;
  variant?: string;
  slide_count?: number;
  cta?: string;
  audience?: string;
  key_message?: string;
}

interface Envelope<T> {
  ok: boolean;
  data: T;
}

export interface RenderSlideResult {
  slide_n: number;
  image_url: string | null;
  renderer: string;
  model: string | null;
  latency_ms?: number;
  skipped_reason?: string;
}

export interface RenderResult {
  configured: boolean;
  backend?: string;
  renderer: string;
  slides: RenderSlideResult[];
  /** "svg_fallback" when Gemini is not configured (visible placeholder). */
  mode?: string;
  placeholder?: boolean;
  requested_renderer?: string;
}

// ─── Brand kits ──────────────────────────────────────────────────────

export function useBrandKits() {
  const [items, setItems] = useState<BrandKit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get<Envelope<BrandKit[]>>("/api/media-creation/brand-kits");
      setItems(r.data ?? []);
    } catch (err: any) {
      setError(err?.message ?? "Falha ao carregar kits de marca");
    } finally {
      setLoading(false);
    }
  }, []);

  const create = useCallback(async (input: BrandKitInput): Promise<BrandKit | null> => {
    try {
      const r = await api.post<Envelope<BrandKit>>("/api/media-creation/brand-kits", input);
      toast.success("Kit de marca criado");
      await refresh();
      return r.data;
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao criar kit");
      return null;
    }
  }, [refresh]);

  const update = useCallback(async (id: string, patch: Partial<BrandKitInput>): Promise<boolean> => {
    try {
      await api.patch<Envelope<BrandKit>>(`/api/media-creation/brand-kits/${id}`, patch);
      toast.success("Kit atualizado");
      await refresh();
      return true;
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao atualizar kit");
      return false;
    }
  }, [refresh]);

  const remove = useCallback(async (id: string): Promise<boolean> => {
    try {
      await api.delete(`/api/media-creation/brand-kits/${id}`);
      toast.success("Kit removido");
      await refresh();
      return true;
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao remover kit");
      return false;
    }
  }, [refresh]);

  useEffect(() => { void refresh(); }, [refresh]);

  return { items, loading, error, refresh, create, update, remove };
}

// ─── References (nested under a kit) ─────────────────────────────────

export function useBrandReferences(brandKitId: string | null) {
  const [items, setItems] = useState<BrandReference[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!brandKitId) { setItems([]); return; }
    setLoading(true);
    try {
      const r = await api.get<Envelope<BrandReference[]>>(
        `/api/media-creation/brand-kits/${brandKitId}/references`,
      );
      setItems(r.data ?? []);
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao carregar referências");
    } finally {
      setLoading(false);
    }
  }, [brandKitId]);

  const add = useCallback(async (input: ReferenceInput): Promise<boolean> => {
    if (!brandKitId) return false;
    try {
      await api.post(`/api/media-creation/brand-kits/${brandKitId}/references`, input);
      await refresh();
      return true;
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao adicionar referência");
      return false;
    }
  }, [brandKitId, refresh]);

  const remove = useCallback(async (referenceId: string): Promise<boolean> => {
    try {
      await api.delete(`/api/media-creation/references/${referenceId}`);
      await refresh();
      return true;
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao remover referência");
      return false;
    }
  }, [refresh]);

  useEffect(() => { void refresh(); }, [refresh]);

  return { items, loading, refresh, add, remove };
}

// ─── Posts (library + lifecycle) ─────────────────────────────────────

interface UsePostsOpts {
  status?: PostStatus;
  brandKitId?: string;
}

export function usePosts(opts: UsePostsOpts = {}) {
  const { status, brandKitId } = opts;
  const [items, setItems] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (brandKitId) params.set("brand_kit_id", brandKitId);
      const path = `/api/media-creation/posts${params.toString() ? `?${params}` : ""}`;
      const r = await api.get<Envelope<Post[]>>(path);
      setItems(r.data ?? []);
    } catch (err: any) {
      setError(err?.message ?? "Falha ao carregar posts");
    } finally {
      setLoading(false);
    }
  }, [status, brandKitId]);

  const create = useCallback(async (input: PostInput): Promise<Post | null> => {
    try {
      const r = await api.post<Envelope<Post>>("/api/media-creation/posts", input);
      toast.success("Rascunho criado");
      await refresh();
      return r.data;
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao criar post");
      return null;
    }
  }, [refresh]);

  const remove = useCallback(async (id: string): Promise<boolean> => {
    try {
      await api.delete(`/api/media-creation/posts/${id}`);
      toast.success("Post excluído");
      await refresh();
      return true;
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao excluir");
      return false;
    }
  }, [refresh]);

  useEffect(() => { void refresh(); }, [refresh]);

  return { items, loading, error, refresh, create, remove };
}

// ─── Single post + generation pipeline ───────────────────────────────

export function usePost(postId: string | null) {
  const [post, setPost] = useState<Post | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!postId) { setPost(null); return; }
    setLoading(true);
    try {
      const r = await api.get<Envelope<Post>>(`/api/media-creation/posts/${postId}`);
      setPost(r.data ?? null);
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao carregar post");
    } finally {
      setLoading(false);
    }
  }, [postId]);

  useEffect(() => { void refresh(); }, [refresh]);

  return { post, loading, refresh };
}

export function usePostGeneration(postId: string | null, onUpdate?: () => void) {
  const [pending, setPending] = useState<null | "storyboard" | "prompts" | "copy" | "render">(null);

  const run = useCallback(
    async (stage: "storyboard" | "prompts" | "copy"): Promise<boolean> => {
      if (!postId) return false;
      setPending(stage);
      try {
        await api.post(`/api/media-creation/posts/${postId}/generate/${stage}`);
        toast.success(`${stageLabel(stage)} gerado(a)`);
        onUpdate?.();
        return true;
      } catch (err: any) {
        toast.error(err?.message ?? `Falha ao gerar ${stage}`);
        return false;
      } finally {
        setPending(null);
      }
    },
    [postId, onUpdate],
  );

  const render = useCallback(
    async (renderer: "nano_banana" | "galilai" | "midjourney" = "nano_banana"): Promise<RenderResult | null> => {
      if (!postId) return null;
      setPending("render");
      try {
        const r = await api.post<Envelope<RenderResult>>(
          `/api/media-creation/posts/${postId}/render`,
          { renderer },
        );
        const data = r.data;
        if (!data.configured) {
          toast.info(
            "Placeholders de marca (SVG) gerados. " +
            "Configure a chave Gemini da organização para gerar imagens por IA.",
          );
        } else {
          const ok = data.slides.filter((s) => s.image_url).length;
          toast.success(`${ok}/${data.slides.length} imagens renderizadas`);
        }
        onUpdate?.();
        return data;
      } catch (err: any) {
        toast.error(err?.message ?? "Falha na renderização");
        return null;
      } finally {
        setPending(null);
      }
    },
    [postId, onUpdate],
  );

  return { run, render, pending };
}

function stageLabel(s: "storyboard" | "prompts" | "copy"): string {
  switch (s) {
    case "storyboard": return "Roteiro";
    case "prompts":    return "Prompts de imagem";
    case "copy":       return "Legenda";
  }
}
