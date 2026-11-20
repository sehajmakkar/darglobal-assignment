import type { SourceRef } from "../types";

export interface SourceSplit {
  /** Shown as "Sources (n)": what the answer actually used. */
  primary: SourceRef[];
  /** Folded under "Also searched": retrieved but not cited. */
  others: SourceRef[];
}

/**
 * While streaming nothing is cited yet, so everything retrieved is shown. Once the answer
 * is final, only cited sources are "Sources"; the rest — all of them when the answer cites
 * nothing (e.g. a polite decline) — are folded away rather than presented as evidence.
 */
export function splitSources(sources: SourceRef[], final: boolean): SourceSplit {
  if (!final) return { primary: sources, others: [] };
  return {
    primary: sources.filter((s) => s.cited),
    others: sources.filter((s) => !s.cited),
  };
}
