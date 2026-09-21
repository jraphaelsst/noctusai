/**
 * Copy-to-clipboard button with explicit success / failure feedback (a
 * clipboard permission denial is reported, never swallowed).
 */
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@noctusai/lib/design-system";

export function CopyTextButton({ text, label = "Copiar" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      toast.error(`Não foi possível copiar: ${err instanceof Error ? err.message : "permissão negada"}.`);
    }
  }

  return (
    <Button size="sm" variant="outline" onClick={handleCopy} data-testid="copy-text-button">
      {copied ? <Check className="mr-1 h-3.5 w-3.5" /> : <Copy className="mr-1 h-3.5 w-3.5" />}
      {copied ? "Copiado" : label}
    </Button>
  );
}
