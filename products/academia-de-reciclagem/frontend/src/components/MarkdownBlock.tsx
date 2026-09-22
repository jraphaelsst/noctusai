/**
 * Inline safe markdown block — no HTML injection, no markdown lib dep.
 * Mirrors `products/knowledge-extractor/frontend/src/pages/LessonViewer.tsx`
 * (`MarkdownBlock`), the existing platform convention for rendering
 * untrusted markdown bodies: plain text via `whitespace-pre-wrap`, never
 * `dangerouslySetInnerHTML`.
 *
 * Kept product-local (only `KbDetail.tsx` in this product uses it — no
 * second consumer yet, so it wasn't promoted alongside the sibling
 * Card/Textarea/Select/Field/FormError/EmptyState/ErrorState primitives
 * that moved to `@noctusai/lib/design-system` (DRY N=2 triage); this stays
 * at N=1 until a second product needs the same shape).
 */
export function MarkdownBlock({ value }: { value: string }) {
  return (
    <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-foreground">
      {value}
    </pre>
  );
}
