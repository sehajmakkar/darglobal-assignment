/**
 * Turn the model's `[1]`, `[2][3]`, `[1, 2]` citations into markdown links with a private
 * `cite:` scheme (`[1,2](cite:1,2)`) that the Markdown renderer swaps for citation pills.
 * Numbers that don't match a source are dropped (the backend already filters them).
 */
const CITATION_RUN = /(?:\s*\[\s*\d+(?:\s*,\s*\d+)*\s*\])+/g;

export function linkCitations(markdown: string, validNumbers: Set<number>): string {
  return markdown.replace(CITATION_RUN, (run) => {
    const numbers = [...run.matchAll(/\d+/g)]
      .map((m) => Number(m[0]))
      .filter((n, i, all) => validNumbers.has(n) && all.indexOf(n) === i);
    if (!numbers.length) return "";
    const ids = numbers.join(",");
    return ` [${ids}](cite:${ids})`;
  });
}

export function parseCiteHref(href: string | undefined): number[] | null {
  if (!href?.startsWith("cite:")) return null;
  return href
    .slice(5)
    .split(",")
    .map(Number)
    .filter((n) => Number.isInteger(n) && n > 0);
}

/** react-markdown sanitises URLs; allow our cite: scheme plus normal safe ones. */
export function urlTransform(url: string): string {
  if (url.startsWith("cite:")) return url;
  return /^(https?:|mailto:|\/|#)/i.test(url) ? url : "";
}
