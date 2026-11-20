import { ArrowUp, Square } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useLayoutEffect, useRef, useState } from "react";

const MAX_CHARS = 1000; // matches the API limit

interface Props {
  busy: boolean;
  placeholder: string;
  sendLabel: string;
  stopLabel: string;
  disclaimer: string;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function Composer({ busy, placeholder, sendLabel, stopLabel, disclaimer, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);

  // Auto-grow. Re-measure on width changes too: the first measurement can happen before
  // layout (width ~0 → everything wraps → max height) and fonts/rotation change wrapping.
  useLayoutEffect(() => {
    const el = area.current;
    if (!el) return;
    const fit = () => {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (busy) return;
    const value = text.trim();
    if (!value || value.length > MAX_CHARS) return;
    onSend(value);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const remaining = MAX_CHARS - text.length;
  return (
    <form onSubmit={submit} className="mx-auto w-full max-w-3xl">
      <div className="rounded-2xl border border-line bg-surface p-2 shadow-sm focus-within:border-accent">
        <textarea
          ref={area}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          aria-label={placeholder}
          rows={1}
          dir="auto"
          maxLength={MAX_CHARS + 200}
          className="block max-h-[200px] w-full resize-none bg-transparent px-2 py-1.5 text-[15px] leading-relaxed outline-none placeholder:text-muted"
        />
        <div className="flex items-center justify-between gap-2 px-1 pt-1">
          <span className={`text-xs tabular-nums ${remaining < 0 ? "text-danger" : "text-muted"}`} aria-live="polite">
            {remaining < 150 ? remaining : ""}
          </span>
          {busy ? (
            <button
              type="button"
              onClick={onStop}
              aria-label={stopLabel}
              className="grid size-9 place-items-center rounded-xl bg-ink text-bg transition hover:opacity-85"
            >
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="submit"
              aria-label={sendLabel}
              disabled={!text.trim() || remaining < 0}
              className="grid size-9 place-items-center rounded-xl bg-accent text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-35"
            >
              <ArrowUp className="size-4" />
            </button>
          )}
        </div>
      </div>
      <p className="mt-1.5 text-center text-[11px] text-muted">{disclaimer}</p>
    </form>
  );
}
