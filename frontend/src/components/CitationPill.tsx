import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import { type CSSProperties, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { hostname } from "../lib/text";
import type { SourceRef } from "../types";
import { SourceBadge } from "./SourceBadge";

interface Props {
  numbers: number[];
  sources: SourceRef[];
  openLabel: string;
}

const CARD_WIDTH = 288;
const MARGIN = 8;

/**
 * Inline citation: compact pill → card with the cited source(s).
 * The card is portalled to <body> with fixed positioning so it can't be clipped by
 * scroll containers (e.g. a table's horizontal-scroll wrapper).
 */
export function CitationPill({ numbers, sources, openLabel }: Props) {
  const cited = numbers.map((n) => sources.find((s) => s.n === n)).filter((s): s is SourceRef => !!s);
  const [position, setPosition] = useState<CSSProperties | null>(null);
  const [page, setPage] = useState(0);
  const pill = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const cardId = useId();
  const open = position !== null;

  useEffect(() => {
    if (!open) return;
    const close = () => setPosition(null);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    const onDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!pill.current?.contains(target) && !card.current?.contains(target)) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    window.addEventListener("scroll", close, true); // any scroll container
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  if (!cited.length) return null;
  const first = cited[0]!;
  const current = cited[Math.min(page, cited.length - 1)]!;

  const show = () => {
    window.clearTimeout(closeTimer.current);
    const rect = pill.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(CARD_WIDTH, window.innerWidth - 2 * MARGIN);
    const rtl = document.documentElement.dir === "rtl";
    // Align with the pill's start edge, then clamp inside the viewport.
    const preferred = rtl ? rect.right - width : rect.left;
    const left = Math.max(MARGIN, Math.min(preferred, window.innerWidth - width - MARGIN));
    const below = rect.bottom + 6;
    const fitsBelow = below + 200 < window.innerHeight;
    setPosition(
      fitsBelow
        ? { left, top: below, width }
        : { left, bottom: window.innerHeight - rect.top + 6, width },
    );
  };
  const hideSoon = () => {
    closeTimer.current = window.setTimeout(() => setPosition(null), 180);
  };
  const keepOpen = () => window.clearTimeout(closeTimer.current);

  return (
    <>
      <button
        ref={pill}
        type="button"
        aria-expanded={open}
        aria-controls={open ? cardId : undefined}
        aria-label={`Sources ${numbers.join(", ")}: ${first.title}`}
        onClick={show}
        onFocus={show}
        onMouseEnter={show}
        onMouseLeave={hideSoon}
        className="mx-0.5 inline-flex items-center gap-1 rounded-full border border-line bg-sunken px-1.5 py-px align-[0.1em] text-[11px] leading-4 font-medium text-muted transition hover:border-accent hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
      >
        <span className="tabular-nums">{numbers.join(",")}</span>
        <span className="max-w-[9rem] truncate">{first.source === "wasalt" ? "Wasalt" : "DarGlobal"}</span>
      </button>
      {open &&
        createPortal(
          <div
            ref={card}
            id={cardId}
            role="dialog"
            aria-label={current.title}
            style={position}
            onMouseEnter={keepOpen}
            onMouseLeave={hideSoon}
            dir={document.documentElement.dir}
            className="fixed z-50 rounded-xl border border-line bg-surface p-3 text-start text-sm leading-snug text-ink shadow-xl"
          >
            {cited.length > 1 && (
              <div className="mb-2 flex items-center justify-between text-xs text-muted">
                <button
                  type="button"
                  aria-label="Previous source"
                  className="rounded p-0.5 hover:bg-sunken disabled:opacity-30"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft className="size-4 rtl:rotate-180" />
                </button>
                <span className="tabular-nums">
                  {page + 1}/{cited.length}
                </span>
                <button
                  type="button"
                  aria-label="Next source"
                  className="rounded p-0.5 hover:bg-sunken disabled:opacity-30"
                  disabled={page >= cited.length - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ChevronRight className="size-4 rtl:rotate-180" />
                </button>
              </div>
            )}
            <div className="flex items-center gap-2">
              <SourceBadge source={current} />
              <span className="truncate text-xs text-muted" dir="ltr">
                {hostname(current.url)}
              </span>
            </div>
            <p className="mt-1.5 font-medium">{current.title}</p>
            <p className="mt-1 line-clamp-4 text-xs text-muted">{current.snippet}</p>
            <a
              href={current.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
            >
              {openLabel}
              <ExternalLink className="size-3" />
            </a>
          </div>,
          document.body,
        )}
    </>
  );
}
