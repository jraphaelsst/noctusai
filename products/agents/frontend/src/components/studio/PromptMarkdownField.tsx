/**
 * Monospace markdown textarea with a live character / estimated-token counter
 * (and an optional hard maximum, e.g. the 1024-char skill `descricao`).
 * Product-local: the counter uses the Agent Studio compiler's estimator
 * (`ceil(len/4)`, CONTRACT §C) so an editor's number matches the inspector's.
 */
import type { TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { estimateTokens } from "./compiledSegments";

export interface PromptMarkdownFieldProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "onChange"> {
  value: string;
  onChange: (value: string) => void;
  /** Hard maximum — the counter turns red and `maxLength` is enforced. */
  max?: number;
  /** Hide the token estimate (short plain-text fields). */
  semTokens?: boolean;
  mono?: boolean;
}

export function PromptMarkdownField({
  value,
  onChange,
  max,
  semTokens,
  mono = true,
  className,
  rows = 10,
  ...rest
}: PromptMarkdownFieldProps) {
  const chars = value.length;
  const over = max !== undefined && chars > max;
  return (
    <div className="space-y-1">
      <textarea
        {...rest}
        rows={rows}
        value={value}
        maxLength={max}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-70",
          mono && "font-mono text-xs leading-relaxed",
          className,
        )}
      />
      <p
        className={cn("text-right text-[11px] tabular-nums", over ? "text-destructive" : "text-muted-foreground")}
        data-testid="markdown-field-counter"
      >
        {chars.toLocaleString("pt-BR")}
        {max !== undefined ? ` / ${max.toLocaleString("pt-BR")}` : ""} caracteres
        {!semTokens && ` · ~${estimateTokens(value).toLocaleString("pt-BR")} tokens`}
      </p>
    </div>
  );
}
