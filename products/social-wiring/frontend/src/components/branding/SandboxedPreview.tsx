/**
 * SandboxedPreview — renders a component's preview HTML ONLY inside a
 * sandboxed iframe.
 *
 * The markup is untrusted (imported / edited). It is NEVER put in the page DOM:
 * it goes into `srcDoc` of an iframe whose `sandbox` attribute is EMPTY — no
 * `allow-scripts`, no `allow-same-origin`, no forms, no popups, no top
 * navigation — and the document carries a CSP meta on top
 * (`buildPreviewDocument`). Tokens reach the preview as CSS custom properties.
 */
import { useMemo } from "react";

import {
  buildPreviewDocument,
  previewHeight,
  type BrandingTokens,
  type PreviewFont,
} from "@/lib/branding";

export interface SandboxedPreviewProps {
  name: string;
  html: string;
  tokens: BrandingTokens;
  themeId: string;
  fonts?: PreviewFont[];
}

export function SandboxedPreview({ name, html, tokens, themeId, fonts }: SandboxedPreviewProps) {
  const srcDoc = useMemo(
    () => buildPreviewDocument({ html, tokens, themeId, fonts }),
    [html, tokens, themeId, fonts],
  );
  return (
    <iframe
      title={`Pré-visualização de ${name}`}
      data-testid={`branding-preview-${name}`}
      sandbox=""
      srcDoc={srcDoc}
      loading="lazy"
      referrerPolicy="no-referrer"
      className="w-full rounded-md border bg-background"
      style={{ height: previewHeight(html) }}
    />
  );
}
