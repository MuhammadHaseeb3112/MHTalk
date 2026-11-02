/** Phone helpers. Pakistani local numbers (03xx...) are normalised to +92. */

export function normalizePhone(value) {
  const raw = String(value || "").trim();
  let digits = raw.replace(/\D/g, "");
  if (!digits) return "";
  if (digits.startsWith("00")) digits = digits.slice(2);
  if (digits.startsWith("0") && digits.length === 11) digits = `92${digits.slice(1)}`;
  else if (digits.length === 10 && digits.startsWith("3")) digits = `92${digits}`;
  return `+${digits}`;
}

export function looksLikePhone(value) {
  const digits = String(value || "").replace(/\D/g, "");
  return digits.length >= 7 && /^[+\d\s()-]+$/.test(String(value || "").trim());
}

/** "+923130067082" -> "+92 313 0067082" (display only). */
export function formatPhone(value) {
  const phone = String(value || "");
  const match = phone.match(/^\+92(\d{3})(\d{7})$/);
  if (match) return `+92 ${match[1]} ${match[2]}`;
  const generic = phone.match(/^\+(\d{1,3})(\d{3})(\d{3,4})(\d{0,4})$/);
  if (generic) return `+${generic[1]} ${generic[2]} ${generic[3]}${generic[4] ? ` ${generic[4]}` : ""}`;
  return phone;
}

/** Digits-only form for partial number matching in search. */
export function phoneDigits(value) {
  return String(value || "").replace(/\D/g, "");
}
