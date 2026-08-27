/**
 * TokenCheckbox — the card's checkbox, drawn from the design tokens.
 *
 * 🔴 NOT `<input type="checkbox">`. The browser default paints a hard white
 * square with a platform blue tick: it ignores the theme entirely, so on the
 * dark card it read as a bright hole punched through the surface, and in dark
 * mode it stayed white while everything around it inverted.
 *
 * Every colour here is a TOKEN, never a raw Tailwind palette value — that is
 * what makes it follow the theme instead of fighting it:
 *   · `bg-card`         — the same surface it sits on, so it reads as part of
 *                         the row rather than as an object dropped onto it
 *   · `border-border`   — the card's own hairline
 *   · `bg-primary` / `text-primary-foreground` when checked — the one moment
 *                         it should draw the eye
 * Softly rounded (not a square, not a pill), per the same brief.
 *
 * Built on the product's Radix `Checkbox` primitive rather than a bespoke
 * button: it already carries the roving focus ring, the `disabled` handling
 * and `role="checkbox"` + `aria-checked`, none of which a hand-rolled div
 * would have.
 */
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

export interface TokenCheckboxProps {
  checked: boolean;
  /** Omitted for a DERIVED tick nobody can set by hand — see `hint`. */
  onCheckedChange?: (checked: boolean) => void;
  /** The accessible name. Required: an unlabelled checkbox is unreachable. */
  label: string;
  testId?: string;
  disabled?: boolean;
  /** Native `title` for a checkbox whose state is not a human decision, so
   *  "why can I not click this?" is answered in place. */
  hint?: string;
  className?: string;
}

export function TokenCheckbox({
  checked,
  onCheckedChange,
  label,
  testId,
  disabled,
  hint,
  className,
}: TokenCheckboxProps) {
  return (
    <Checkbox
      checked={checked}
      onCheckedChange={(v) => onCheckedChange?.(v === true)}
      disabled={disabled ?? !onCheckedChange}
      aria-label={label}
      title={hint}
      data-testid={testId}
      className={cn(
        "h-[1.15rem] w-[1.15rem] shrink-0 rounded-[0.375rem] border-border bg-card",
        "transition-colors hover:border-primary/60",
        "data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
        // A derived tick is still readable at full contrast — it is
        // information, not a disabled control the eye should skip.
        "disabled:cursor-default disabled:opacity-100",
        className,
      )}
    />
  );
}
