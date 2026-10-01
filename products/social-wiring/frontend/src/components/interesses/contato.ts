/** `https://wa.me/<digits>` for a stored phone; bare BR numbers (10/11
 *  digits) get the 55 country code. `null` when nothing dialable. */
export function whatsappHref(telefone: string | null | undefined): string | null {
  const digitos = (telefone ?? "").replace(/\D/g, "");
  if (digitos.length < 10) return null;
  const completo = digitos.length <= 11 ? `55${digitos}` : digitos;
  return `https://wa.me/${completo}`;
}
