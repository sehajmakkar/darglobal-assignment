import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { splitSources } from "../lib/sources";
import { hostname } from "../lib/text";
import type { SourceRef } from "../types";
import { SourceBadge } from "./SourceBadge";

interface Props {
  sources: SourceRef[];
  label: string;
  alsoLabel: string;
  wasaltDataLabel: string;
  final: boolean;
}

/** Source cards under an answer: cited ones as "Sources"; the rest folded (see splitSources). */
export function Sources({ sources, label, alsoLabel, wasaltDataLabel, final }: Props) {
  const [showOthers, setShowOthers] = useState(false);
  if (!sources.length) return null;
  const { primary, others } = splitSources(sources, final);

  return (
    <section className="mt-3" aria-label={label}>
      {primary.length > 0 && (
        <>
          <h4 className="mb-1.5 text-xs font-medium tracking-wide text-muted uppercase">
            {label} <span className="tabular-nums">({primary.length})</span>
          </h4>
          <ul className="-mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1 sm:grid sm:grid-cols-2 sm:overflow-visible lg:grid-cols-3">
            {primary.map((s) => (
              <SourceCard key={s.n} source={s} wasaltDataLabel={wasaltDataLabel} />
            ))}
          </ul>
        </>
      )}
      {others.length > 0 && (
        <div className={primary.length ? "mt-1.5" : ""}>
          <button
            type="button"
            onClick={() => setShowOthers((v) => !v)}
            aria-expanded={showOthers}
            className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink"
          >
            {alsoLabel} ({others.length})
            <ChevronDown className={`size-3.5 transition ${showOthers ? "rotate-180" : ""}`} />
          </button>
          {showOthers && (
            <ul className="mt-1.5 -mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1 opacity-80 sm:grid sm:grid-cols-2 sm:overflow-visible lg:grid-cols-3">
              {others.map((s) => (
                <SourceCard key={s.n} source={s} wasaltDataLabel={wasaltDataLabel} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function SourceCard({ source, wasaltDataLabel }: { source: SourceRef; wasaltDataLabel: string }) {
  const isDb = source.record_type === "listing_db";
  return (
    <li className="w-60 shrink-0 snap-start sm:w-auto">
      <a
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        title={source.title}
        className="flex h-full flex-col gap-1 rounded-xl border border-line bg-surface p-2.5 transition hover:border-accent focus-visible:outline-2 focus-visible:outline-accent"
      >
        <span className="flex items-center gap-1.5 text-[11px] text-muted">
          <span className="grid size-4 place-items-center rounded-full bg-sunken text-[10px] font-semibold tabular-nums text-ink">
            {source.n}
          </span>
          <SourceBadge source={source} />
          {isDb ? (
            <span className="truncate">{wasaltDataLabel}</span>
          ) : (
            <span className="truncate" dir="ltr">
              {hostname(source.url)}
            </span>
          )}
        </span>
        <span className="line-clamp-2 text-[13px] leading-snug font-medium text-ink">{source.title}</span>
      </a>
    </li>
  );
}
