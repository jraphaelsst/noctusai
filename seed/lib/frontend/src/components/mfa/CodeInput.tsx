import * as React from 'react';
import { Input } from '../../design-system/ui/Input';

export interface CodeInputProps {
  id: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  autoFocus?: boolean;
}

/** 6-digit one-time code field (numeric keypad, OS autofill friendly). */
export function CodeInput({ id, value, onChange, disabled, invalid, describedBy, autoFocus }: CodeInputProps) {
  return (
    <Input
      id={id}
      inputMode="numeric"
      pattern="[0-9]*"
      autoComplete="one-time-code"
      maxLength={6}
      placeholder="000000"
      value={value}
      disabled={disabled}
      autoFocus={autoFocus}
      aria-invalid={invalid || undefined}
      aria-describedby={describedBy}
      className="text-center font-mono text-lg tracking-[0.5em]"
      onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
    />
  );
}
