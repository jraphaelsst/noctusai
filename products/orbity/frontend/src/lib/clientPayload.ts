/**
 * Client form -> POST/PATCH /api/clients payload.
 *
 * `legal_name` (Razão Social) is required and is what contracts snapshot and the payment gateway charges; `name` is the
 * optional nome fantasia -- left empty it is OMITTED (the server falls back to the legal name). Empty optional fields are
 * omitted rather than sent: the backend rejects "" for e-mail and 0 for due_date (422).
 */
export function clientPayload(form: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of ["legal_name", "name", "email", "phone", "company", "default_billing_type"]) {
    const v = form[key];
    if (typeof v === "string" && v.trim() !== "") out[key] = v.trim();
  }
  const doc = typeof form.document === "string" ? form.document.trim() : "";
  if (doc !== "") out.document = doc;
  const due = Number(form.due_date);
  if (Number.isFinite(due) && due >= 1 && due <= 31) out.due_date = Math.trunc(due);
  const monthly = Number(form.monthly_value);
  if (Number.isFinite(monthly) && monthly > 0) out.monthly_value = monthly;
  out.billing_automation_enabled = Boolean(form.billing_automation_enabled);
  return out;
}

/** Digits only (CPF 11 / CNPJ 14) -- the shape the CNPJ lookup route takes. */
export function documentDigits(value: string): string {
  return value.replace(/\D/g, "");
}

export function isCnpj(value: string): boolean {
  return documentDigits(value).length === 14;
}
