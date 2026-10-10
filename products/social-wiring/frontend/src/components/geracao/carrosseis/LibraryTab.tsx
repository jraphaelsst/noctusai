/**
 * Carrosséis › Biblioteca tab — moved verbatim from the legacy `MediaCreation`
 * page (esteira-contract §A.5 A-2): posts list + post detail with the
 * storyboard / image-prompts / copy / render / score pipeline.
 *
 * Loading: two signals off `data` (lying-loading-state.md) — the list shows a
 * skeleton only while there is nothing yet; the detail never unmounts on a
 * refetch (it used to, on every generation stage).
 */
import {
  CheckCircle2,
  ClipboardCheck,
  ImagePlus,
  Loader2,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  type Post,
  type PostScore,
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

// Método Audience slide-role labels (+ legacy roles). Fallback: the raw role.
const ROLE_LABEL: Record<string, string> = {
  capa: "Capa",
  identificacao: "Identificação",
  virada: "Virada",
  nome: "Nome / causa",
  prova: "Prova",
  valor: "Valor prático",
  cta: "CTA",
  cover: "Capa",
  develop: "Desenvolvimento",
  insight: "Virada",
};

const roleLabel = (role: string): string => ROLE_LABEL[role] ?? role;

// ─── Library tab ─────────────────────────────────────────────────────

export function LibraryTab({
  selectedPostId,
  onSelect,
}: {
  selectedPostId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { items, loading, error, remove, refresh } = usePosts();
  // Two signals off the data: skeleton only while nothing is loaded yet;
  // a refetch over existing items just shows the inline spinner.
  const showSkeleton = loading && items.length === 0;
  const isRefreshing = loading && items.length > 0;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            Posts
            {isRefreshing && (
              <Loader2 role="status" aria-label="Atualizando" className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 p-2">
          {showSkeleton && (
            <div className="space-y-2 p-1" data-testid="carrosseis-list-loading" aria-busy="true">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          )}
          {error && items.length === 0 && !loading && (
            <div className="space-y-2 px-3 py-4 text-sm" data-testid="carrosseis-list-error" role="alert">
              <p className="text-destructive">Não foi possível carregar os posts.</p>
              <Button size="sm" variant="outline" onClick={() => void refresh()}>
                Tentar novamente
              </Button>
            </div>
          )}
          {!loading && !error && items.length === 0 && (
            <p className="px-3 py-4 text-sm text-muted-foreground" data-testid="carrosseis-list-empty">
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

      <div className="min-w-0">
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

export function PostDetail({
  postId,
  onDeleted,
}: {
  postId: string;
  onDeleted: () => void;
}) {
  const { post: fetched, loading, refresh } = usePost(postId);
  const { run, render, score, pending } = usePostGeneration(postId, refresh);

  // The hook keeps the previous post while the next one loads; only a post
  // that belongs to THIS id counts as data.
  const post = fetched && fetched.id === postId ? fetched : null;
  const isRefreshing = loading && !!post;

  if (!post) {
    if (loading) {
      return (
        <Card data-testid="post-detail-loading" aria-busy="true">
          <CardContent className="space-y-3 p-6">
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
      );
    }
    return (
      <Card data-testid="post-detail-error" role="alert">
        <CardContent className="flex flex-col items-center gap-3 p-12 text-sm">
          <p className="text-destructive">Não foi possível carregar o post.</p>
          <Button size="sm" variant="outline" onClick={() => void refresh()}>
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <CardTitle className="text-lg">{post.title}</CardTitle>
            <p className="mt-1 break-words text-sm text-muted-foreground">{post.idea}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant={STATUS_VARIANT[post.status]}>
                {STATUS_LABEL[post.status]}
              </Badge>
              <span>· {post.format}</span>
              <span>· {post.slide_count} slides</span>
              <span>· variante: {post.variant}</span>
              {post.brand_kit && <span>· kit: {post.brand_kit.name}</span>}
              {isRefreshing && (
                <Loader2 role="status" aria-label="Atualizando" className="h-3.5 w-3.5 animate-spin" />
              )}
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
              {post.slides?.some((s) => s.prompt_nano_banana)
                ? "Regerar prompts"
                : "2. Gerar prompts"}
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
              {post.copy_caption ? "Regerar legenda" : "3. Gerar legenda"}
            </Button>
            <Button
              onClick={() => void render("nano_banana")}
              disabled={pending !== null || !post.storyboard}
              size="sm"
              variant="secondary"
            >
              {pending === "render" && (
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
              )}
              {post.slides?.some((s) => s.image_url)
                ? "Renderizar novamente"
                : "4. Renderizar imagens"}
            </Button>
            <Button
              onClick={() => void score()}
              disabled={pending !== null || !post.storyboard}
              size="sm"
              variant={post.score ? "outline" : "secondary"}
            >
              {pending === "score" ? (
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
              ) : (
                <ClipboardCheck className="mr-2 h-3 w-3" />
              )}
              {post.score ? "Reavaliar post" : "5. Avaliar post"}
            </Button>
          </div>
        </section>

        {post.score && <ScoreCard score={post.score} />}

        {post.storyboard &&
          (post.storyboard.trigger_dominant ||
            (post.storyboard.templates?.length ?? 0) > 0 ||
            post.storyboard.rationale) && (
            <section>
              <h3 className="mb-2 text-sm font-semibold">Metodologia</h3>
              <Card className="bg-muted/30">
                <CardContent className="space-y-2 p-4 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    {post.storyboard.trigger_dominant && (
                      <Badge className="text-[11px]">
                        Gatilho: {post.storyboard.trigger_dominant}
                      </Badge>
                    )}
                    {post.storyboard.triggers_embedded?.map((t) => (
                      <Badge key={t} variant="secondary" className="text-[10px]">
                        {t}
                      </Badge>
                    ))}
                  </div>
                  {post.storyboard.templates && post.storyboard.templates.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="text-xs text-muted-foreground">Templates:</span>
                      {post.storyboard.templates.map((t) => (
                        <Badge key={t} variant="outline" className="text-[10px]">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  )}
                  {post.storyboard.arc_pattern && (
                    <p className="text-xs text-muted-foreground">
                      Arco: {post.storyboard.arc_pattern}
                    </p>
                  )}
                  {post.storyboard.rationale && (
                    <p className="break-words text-xs italic text-muted-foreground">
                      {post.storyboard.rationale}
                    </p>
                  )}
                </CardContent>
              </Card>
            </section>
          )}

        {post.format === "reels" &&
          post.storyboard?.slides?.some((s) => s.spoken) && (
            <section>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">
                  Roteiro (fala) — o que você grava
                </h3>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 shrink-0 text-[10px]"
                  onClick={() => {
                    const script = (post.storyboard?.slides ?? [])
                      .filter((s) => s.spoken)
                      .map((s) => s.spoken)
                      .join("\n\n");
                    void navigator.clipboard.writeText(script);
                  }}
                >
                  Copiar roteiro
                </Button>
              </div>
              <Card className="bg-muted/30">
                <CardContent className="space-y-3 p-4 text-sm">
                  {post.storyboard.slides
                    .filter((s) => s.spoken)
                    .map((s, i) => (
                      <div key={s.n ?? i} className="min-w-0">
                        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                          {roleLabel(s.role ?? "")}
                        </div>
                        <p className="break-words">{s.spoken}</p>
                      </div>
                    ))}
                </CardContent>
              </Card>
            </section>
          )}

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
                        {roleLabel(s.role)}
                      </Badge>
                      {s.image_renderer && (
                        <Badge variant="secondary" className="text-[10px]">
                          {s.image_renderer === "svg" ? "placeholder" : s.image_renderer}
                        </Badge>
                      )}
                    </div>
                    {s.image_url && (
                      <img
                        src={s.image_url}
                        alt={s.visual_brief ?? `Slide ${s.slide_n}`}
                        className="mt-1 max-h-72 w-full rounded object-cover"
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
                      />
                    )}
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

function ScoreCard({ score }: { score: PostScore }) {
  const verdict = (score.verdict || "").toLowerCase();
  const verdictVariant: "default" | "secondary" | "destructive" =
    verdict.includes("pronto")
      ? "default"
      : verdict.includes("refazer")
        ? "destructive"
        : "secondary";
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">Avaliação (Método Audience)</h3>
      <Card className="bg-muted/30">
        <CardContent className="space-y-3 p-4 text-sm">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-2xl font-semibold">{score.score}/10</span>
            {score.verdict && (
              <Badge variant={verdictVariant} className="text-[11px]">
                {score.verdict}
              </Badge>
            )}
          </div>
          {score.rationale && (
            <p className="break-words text-xs italic text-muted-foreground">
              {score.rationale}
            </p>
          )}
          {score.strengths && score.strengths.length > 0 && (
            <div>
              <div className="text-xs font-medium text-muted-foreground">Forças</div>
              <ul className="mt-1 space-y-0.5">
                {score.strengths.map((s, i) => (
                  <li key={i} className="text-xs">✓ {s}</li>
                ))}
              </ul>
            </div>
          )}
          {score.corrections && score.corrections.length > 0 && (
            <div>
              <div className="text-xs font-medium text-muted-foreground">
                Correções prioritárias
              </div>
              <ul className="mt-1 space-y-0.5">
                {score.corrections.map((c, i) => (
                  <li key={i} className="text-xs">→ {c}</li>
                ))}
              </ul>
            </div>
          )}
          {score.criteria && score.criteria.length > 0 && (
            <div className="grid gap-1 sm:grid-cols-2">
              {score.criteria.map((c) => (
                <div key={c.name} className="flex items-start gap-1.5 text-xs">
                  {c.pass ? (
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-600" />
                  ) : (
                    <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                  )}
                  <span className="min-w-0 break-words">
                    <span className="font-medium">{c.name}</span>
                    {c.note ? ` — ${c.note}` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function PromptBlock({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded border bg-background p-2 text-xs">
      <div className="mb-1 font-mono text-[10px] uppercase text-muted-foreground">
        {label}
      </div>
      <pre className="whitespace-pre-wrap break-words font-mono text-[11px]">{text}</pre>
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

