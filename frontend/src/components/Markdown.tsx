import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { linkCitations, parseCiteHref, urlTransform } from "../lib/citations";
import type { SourceRef } from "../types";
import { CitationPill } from "./CitationPill";

interface Props {
  text: string;
  sources: SourceRef[];
  openLabel: string;
}

/** Answer markdown (GFM: tables, lists, bold) with `[n]` citations rendered as pills. */
export const Markdown = memo(function Markdown({ text, sources, openLabel }: Props) {
  const valid = useMemo(() => new Set(sources.map((s) => s.n)), [sources]);
  const markdown = useMemo(() => linkCitations(text, valid), [text, valid]);

  const components = useMemo<Components>(
    () => ({
      a: ({ href, children }) => {
        const numbers = parseCiteHref(href);
        if (numbers) return <CitationPill numbers={numbers} sources={sources} openLabel={openLabel} />;
        return (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent underline underline-offset-2">
            {children}
          </a>
        );
      },
      p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
      ul: ({ children }) => <ul className="my-2 list-disc space-y-1 ps-5">{children}</ul>,
      ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 ps-5">{children}</ol>,
      li: ({ children }) => <li className="ps-0.5">{children}</li>,
      strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
      h1: ({ children }) => <h3 className="mt-4 mb-2 text-base font-semibold">{children}</h3>,
      h2: ({ children }) => <h3 className="mt-4 mb-2 text-base font-semibold">{children}</h3>,
      h3: ({ children }) => <h4 className="mt-3 mb-1.5 font-semibold">{children}</h4>,
      code: ({ children }) => <code className="rounded bg-sunken px-1 py-0.5 text-[0.9em]">{children}</code>,
      blockquote: ({ children }) => (
        <blockquote className="my-2 border-s-2 border-accent ps-3 text-muted">{children}</blockquote>
      ),
      table: ({ children }) => (
        <div className="my-3 overflow-x-auto rounded-lg border border-line">
          <table className="w-full border-collapse text-sm">{children}</table>
        </div>
      ),
      thead: ({ children }) => <thead className="bg-sunken text-start">{children}</thead>,
      tr: ({ children }) => <tr className="border-t border-line first:border-t-0 even:bg-sunken/40">{children}</tr>,
      th: ({ children }) => <th className="px-3 py-2 text-start font-semibold whitespace-nowrap">{children}</th>,
      td: ({ children }) => <td className="px-3 py-2 align-top">{children}</td>,
    }),
    [sources, openLabel],
  );

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={urlTransform} components={components}>
      {markdown}
    </ReactMarkdown>
  );
});
