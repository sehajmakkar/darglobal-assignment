import { AlertTriangle, Check, Copy, Loader2, RotateCcw, Sparkles } from "lucide-react";
import { useState } from "react";
import type { AssistantMessage as AssistantMsg, UserMessage as UserMsg } from "../hooks/useChat";
import type { STRINGS } from "../lib/i18n";
import { isArabic } from "../lib/text";
import { Markdown } from "./Markdown";
import { Sources } from "./Sources";

type T = (typeof STRINGS)["en"];

export function UserMessage({ message }: { message: UserMsg }) {
  return (
    <div className="flex justify-end">
      <div
        dir="auto"
        className="max-w-[85%] rounded-2xl rounded-ee-md bg-ink px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-bg"
      >
        {message.content}
      </div>
    </div>
  );
}

export function AssistantMessage({ message, t, onRetry }: { message: AssistantMsg; t: T; onRetry: () => void }) {
  const rtl = isArabic(message.content || message.question);
  const streaming = message.status === "streaming";
  const final = message.status === "done" || message.status === "stopped";

  return (
    <article className="flex gap-3" aria-busy={!final && message.status !== "error"}>
      <div className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-accent-soft text-accent">
        <Sparkles className="size-3.5" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        {message.status === "searching" && (
          <p className="flex items-center gap-2 py-1 text-sm text-muted" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            {message.sources.length ? t.writing : t.searching}
          </p>
        )}

        {message.content && (
          <div
            dir={rtl ? "rtl" : "ltr"}
            lang={rtl ? "ar" : "en"}
            className={`text-[15px] leading-relaxed ${streaming ? "caret" : ""}`}
          >
            <Markdown text={message.content} sources={message.sources} openLabel={t.openSource} />
          </div>
        )}

        {message.status === "error" && message.error && (
          <ErrorCard message={message} t={t} onRetry={onRetry} />
        )}

        {message.status !== "error" && (
          <Sources
            sources={message.sources}
            label={t.sources}
            alsoLabel={t.alsoSearched}
            wasaltDataLabel={t.wasaltData}
            final={final}
          />
        )}

        {final && message.answer && <AnswerMeta message={message} t={t} />}
      </div>
    </article>
  );
}

function AnswerMeta({ message, t }: { message: AssistantMsg; t: T }) {
  const [copied, setCopied] = useState(false);
  const answer = message.answer!;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(answer.answer);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (e.g. insecure context) */
    }
  };
  const model = answer.model?.replace(/:free$/, "").split("/").pop();
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
      <button
        type="button"
        onClick={copy}
        className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-sunken hover:text-ink"
        aria-label={t.copy}
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        {copied ? t.copied : t.copy}
      </button>
      {answer.cached ? (
        <span>{t.cached}</span>
      ) : (
        model && (
          <span dir="ltr">
            {t.answeredBy} {model} · {(answer.latency_ms / 1000).toFixed(1)} s
          </span>
        )
      )}
    </div>
  );
}

function ErrorCard({ message, t, onRetry }: { message: AssistantMsg; t: T; onRetry: () => void }) {
  const error = message.error!;
  const text =
    error.kind === "rate_limited" && error.retryAfterS ? t.rateLimited(error.retryAfterS) : t.errors[error.kind];
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger-soft p-3 text-sm">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
      <div className="flex-1">
        <p>{text}</p>
        {error.kind !== "quota" && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium hover:border-accent"
          >
            <RotateCcw className="size-3.5" /> {t.retry}
          </button>
        )}
      </div>
    </div>
  );
}
