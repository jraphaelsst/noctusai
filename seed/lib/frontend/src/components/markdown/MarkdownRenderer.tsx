/**
 * `<MarkdownRenderer/>` — canonical GFM markdown renderer organ.
 *
 * Renders a markdown STRING (tables, task lists, strikethrough, autolinks,
 * fenced code, headings with stable slug `id`s for `#anchor` links) using
 * the shared design-system typography tokens (`text-foreground`,
 * `text-muted-foreground`, `bg-muted`, `border-border`, …) so it is
 * theme-aware (light/dark) by construction — no separate `prose` plugin
 * dependency, no product-specific CSS.
 *
 * Sanitization: this renderer NEVER executes raw HTML found in the
 * markdown source. `react-markdown` is used WITHOUT `rehype-raw` — by
 * design, `remark-rehype`'s `allowDangerousHtml` defaults to `false`, so
 * any literal `<script>`/`<img onerror=…>` block in the source is encoded
 * as inert TEXT, never parsed into real DOM nodes. Link/image URLs also go
 * through `react-markdown`'s default `urlTransform`, which defangs
 * dangerous schemes (`javascript:`, etc.) — see `MarkdownRenderer.test.tsx`
 * for executable proof of both. No `rehype-sanitize` dependency is needed
 * as a result (considered + rejected — see the organ's `.organ.yaml`
 * `alternatives_considered`).
 *
 * Host seams (so a consuming page controls navigation without the organ
 * knowing about React Router / its own asset pipeline):
 *   - `resolveImage(src)` — called for every image `src` that is NOT
 *     already an absolute URL (`http(s):`/`data:`); return the resolved
 *     asset URL, or `undefined` to render the image as a broken/alt
 *     placeholder (never a silent blank).
 *   - `onNavigate(href)` — called (with `preventDefault`) for every link
 *     `href` that is relative (not `http(s):`/`mailto:`/`#hash`). External
 *     links open in a new tab (`rel="noopener noreferrer"`); in-page
 *     `#hash` links fall through to the browser's native anchor scroll
 *     (the heading already carries that `id` via `rehype-slug`).
 */
import * as React from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSlug from 'rehype-slug';

import { cn } from '../../utils';

export interface MarkdownRendererProps {
  /** Raw markdown source. */
  content: string;
  /**
   * Resolve a relative image `src` (as written in the markdown) to a
   * loadable URL. Not called for already-absolute `http(s):`/`data:` URLs.
   * Return `undefined` when the asset can't be resolved — the image then
   * renders as a labelled placeholder instead of a broken `<img>`.
   */
  resolveImage?: (src: string) => string | undefined;
  /**
   * Called for relative link `href`s (in-app doc-to-doc navigation).
   * NOT called for absolute `http(s):`/`mailto:` links (opened externally)
   * or bare `#hash` links (native in-page anchor scroll).
   */
  onNavigate?: (href: string) => void;
  className?: string;
}

function isAbsoluteUrl(href: string): boolean {
  return /^([a-z][a-z0-9+.-]*:|\/\/)/i.test(href);
}

function isExternalOrSpecial(href: string): boolean {
  return (
    isAbsoluteUrl(href) || href.startsWith('mailto:') || href.startsWith('tel:')
  );
}

function ImagePlaceholder({ alt }: { alt?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-border bg-muted/40 px-2 py-1 text-xs text-muted-foreground">
      Imagem indisponível{alt ? `: ${alt}` : ''}
    </span>
  );
}

export function MarkdownRenderer({
  content,
  resolveImage,
  onNavigate,
  className,
}: MarkdownRendererProps) {
  const components = React.useMemo<Components>(
    () => ({
      h1: ({ children, id }) => (
        <h1
          id={id}
          className="mt-8 scroll-mt-20 text-2xl font-semibold text-foreground first:mt-0"
        >
          {children}
        </h1>
      ),
      h2: ({ children, id }) => (
        <h2
          id={id}
          className="mt-8 scroll-mt-20 border-b border-border pb-2 text-xl font-semibold text-foreground first:mt-0"
        >
          {children}
        </h2>
      ),
      h3: ({ children, id }) => (
        <h3 id={id} className="mt-6 scroll-mt-20 text-lg font-semibold text-foreground">
          {children}
        </h3>
      ),
      h4: ({ children, id }) => (
        <h4 id={id} className="mt-4 scroll-mt-20 text-base font-semibold text-foreground">
          {children}
        </h4>
      ),
      h5: ({ children, id }) => (
        <h5 id={id} className="mt-4 scroll-mt-20 text-sm font-semibold text-foreground">
          {children}
        </h5>
      ),
      h6: ({ children, id }) => (
        <h6
          id={id}
          className="mt-4 scroll-mt-20 text-sm font-semibold uppercase tracking-wide text-muted-foreground"
        >
          {children}
        </h6>
      ),
      p: ({ children }) => (
        <p className="mt-4 text-sm leading-relaxed text-foreground first:mt-0">{children}</p>
      ),
      a: ({ href, children }) => {
        const target = href ?? '';
        if (!target || target.startsWith('#')) {
          // In-page anchor — native browser scroll, `rehype-slug` already
          // stamped a matching `id` on the target heading.
          return (
            <a href={target} className="font-medium text-primary underline underline-offset-2 hover:text-primary/80">
              {children}
            </a>
          );
        }
        if (isExternalOrSpecial(target)) {
          return (
            <a
              href={target}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-primary underline underline-offset-2 hover:text-primary/80"
            >
              {children}
            </a>
          );
        }
        return (
          <a
            href={target}
            onClick={(e) => {
              e.preventDefault();
              onNavigate?.(target);
            }}
            className="font-medium text-primary underline underline-offset-2 hover:text-primary/80"
          >
            {children}
          </a>
        );
      },
      img: ({ src, alt }) => {
        const raw = typeof src === 'string' ? src : '';
        if (!raw) return <ImagePlaceholder alt={alt} />;
        const resolved = isAbsoluteUrl(raw) ? raw : resolveImage?.(raw);
        if (!resolved) return <ImagePlaceholder alt={alt} />;
        return (
          <img
            src={resolved}
            alt={alt ?? ''}
            className="my-4 max-w-full rounded-lg border border-border"
            loading="lazy"
          />
        );
      },
      ul: ({ children }) => (
        <ul className="mt-3 list-disc space-y-1 pl-6 text-sm text-foreground marker:text-muted-foreground">
          {children}
        </ul>
      ),
      ol: ({ children }) => (
        <ol className="mt-3 list-decimal space-y-1 pl-6 text-sm text-foreground marker:text-muted-foreground">
          {children}
        </ol>
      ),
      li: ({ children, className: liClassName }) => (
        <li className={cn('leading-relaxed', liClassName)}>{children}</li>
      ),
      input: ({ type, checked, disabled }) =>
        type === 'checkbox' ? (
          <input
            type="checkbox"
            checked={!!checked}
            disabled={disabled ?? true}
            readOnly
            className="mr-1.5 accent-primary align-middle"
          />
        ) : null,
      blockquote: ({ children }) => (
        <blockquote className="mt-4 border-l-4 border-border pl-4 text-sm italic text-muted-foreground">
          {children}
        </blockquote>
      ),
      hr: () => <hr className="my-6 border-border" />,
      strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
      del: ({ children }) => <del className="text-muted-foreground line-through">{children}</del>,
      code: ({ className: codeClassName, children, ...rest }) => {
        const isBlock = /language-/.test(codeClassName ?? '');
        if (isBlock) {
          return (
            <code className={cn('font-mono text-sm', codeClassName)} {...rest}>
              {children}
            </code>
          );
        }
        return (
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
            {children}
          </code>
        );
      },
      pre: ({ children }) => (
        <pre className="mt-4 overflow-x-auto rounded-lg border border-border bg-muted/40 p-4 text-sm">
          {children}
        </pre>
      ),
      table: ({ children }) => (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full border-collapse text-sm">{children}</table>
        </div>
      ),
      thead: ({ children }) => <thead className="border-b border-border">{children}</thead>,
      th: ({ children }) => (
        <th className="border-b border-border px-3 py-2 text-left font-semibold text-foreground">
          {children}
        </th>
      ),
      td: ({ children }) => (
        <td className="border-b border-border/60 px-3 py-2 text-foreground">{children}</td>
      ),
    }),
    [resolveImage, onNavigate],
  );

  return (
    <div className={cn('markdown-renderer', className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSlug]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
