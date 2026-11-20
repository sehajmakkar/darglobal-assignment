import { Building2, MapPinned } from "lucide-react";
import type { Starter } from "../lib/i18n";

interface Props {
  title: string;
  body: string;
  starters: Starter[];
  onPick: (text: string) => void;
}

export function EmptyState({ title, body, starters, onPick }: Props) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center px-1 pt-[8vh] pb-6 text-center sm:pt-[12vh]">
      <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">{title}</h2>
      <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-pretty text-muted">{body}</p>
      <ul className="mt-8 grid w-full gap-2 sm:grid-cols-2">
        {starters.map((s) => (
          <li key={s.text}>
            <button
              type="button"
              onClick={() => onPick(s.text)}
              className="flex h-full w-full items-start gap-2.5 rounded-xl border border-line bg-surface p-3 text-start text-sm transition hover:border-accent hover:shadow-sm focus-visible:outline-2 focus-visible:outline-accent"
            >
              {s.source === "darglobal" ? (
                <Building2 className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
              ) : (
                <MapPinned className="mt-0.5 size-4 shrink-0 text-wasalt" aria-hidden />
              )}
              <span dir="auto">{s.text}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
