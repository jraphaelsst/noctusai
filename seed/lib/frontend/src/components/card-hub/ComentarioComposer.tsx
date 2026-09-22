import { useState } from "react";

import { CardHubButton as Button } from "../../design-system/ui/card-hub-button";
import { Textarea } from "../../design-system/ui/textarea";

export interface ComentarioComposerProps {
  onPost: (corpo: string) => void;
  posting?: boolean;
}

/**
 * 🔴 The comment composer's post action KEPT ITS WORDS.
 *
 * The brief removed the text from every button in the card and put it on
 * hover — with two exceptions, and this is one. The composer's button appears
 * only once something has been typed, and at that moment it is the whole
 * point of the box below it. A bare glyph beside a filled textarea does not
 * say whether it posts, saves a draft or clears — and this is the one control
 * whose misfire is public: a half-written note lands on the client's activity
 * feed for the whole team to read.
 *
 * MOVED from `products/social-wiring/frontend/src/components/card/ClienteCardDialog.tsx`
 * (a private sub-section there) into the seed card hub
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md` Slice C).
 * Markup, classes and data-testids are SW's.
 *
 * Presentational only: props in, callbacks out.
 */
export function ComentarioComposer({ onPost, posting }: ComentarioComposerProps) {
  const [corpo, setCorpo] = useState("");
  return (
    <div className="space-y-2">
      <Textarea
        placeholder="Escrever um comentário…"
        value={corpo}
        onChange={(e) => setCorpo(e.target.value)}
        rows={2}
        data-testid="comentario-textarea"
      />
      {corpo.trim().length > 0 && (
        <Button
          size="sm"
          className="max-sm:min-h-10"
          disabled={posting}
          onClick={() => {
            onPost(corpo.trim());
            setCorpo("");
          }}
          data-testid="comentario-enviar-btn"
        >
          {posting ? "Enviando…" : "Comentar"}
        </Button>
      )}
    </div>
  );
}
