/**
 * ResourceManager form -> POST/PATCH /api/clients payload.
 *
 * The organ seeds empty text as "" and empty numbers as 0. The backend
 * rejects both (EmailStr, due_date ge=1 le=31 -> 422), so empty optional
 * fields are OMITTED rather than sent.
 */
export function clientPayload(form: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of ["name", "company", "email", "phone", "default_billing_type"]) {
    const v = form[key];
    if (typeof v === "string" && v.trim() !== "") out[key] = v.trim();
  }
  const due = Number(form.due_date);
  if (Number.isFinite(due) && due >= 1 && due <= 31) out.due_date = Math.trunc(due);
  const monthly = Number(form.monthly_value);
  if (Number.isFinite(monthly) && monthly > 0) out.monthly_value = monthly;
  out.billing_automation_enabled = Boolean(form.billing_automation_enabled);
  return out;
}
