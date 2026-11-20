const ARABIC = /[؀-ۿݐ-ݿࢠ-ࣿ]/g;
const LETTER = /\p{L}/gu;

/** Mirrors the backend's detect_language: Arabic if ≥30% of letters are Arabic script. */
export function isArabic(text: string): boolean {
  const letters = text.match(LETTER)?.length ?? 0;
  if (!letters) return false;
  return (text.match(ARABIC)?.length ?? 0) / letters >= 0.3;
}

export function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
