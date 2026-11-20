import type { SourceRef } from "../types";

/** Small colored label: which site a source comes from. */
export function SourceBadge({ source }: { source: Pick<SourceRef, "source" | "record_type"> }) {
  const wasalt = source.source === "wasalt";
  const label = source.record_type === "listing_db" ? "Wasalt data" : wasalt ? "Wasalt" : "DarGlobal";
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-1.5 py-px text-[10px] font-semibold tracking-wide uppercase ${
        wasalt ? "bg-wasalt-soft text-wasalt" : "bg-accent-soft text-accent"
      }`}
    >
      {label}
    </span>
  );
}
