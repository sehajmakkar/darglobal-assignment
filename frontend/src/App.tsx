import { ArrowDown, Info, Languages, SquarePen } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { AboutDrawer } from "./components/AboutDrawer";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { AssistantMessage, UserMessage } from "./components/Messages";
import { useChat } from "./hooks/useChat";
import { getHealth } from "./lib/api";
import { STRINGS } from "./lib/i18n";
import type { Health, Lang } from "./types";

const LANG_KEY = "dgbot.lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved === "en" || saved === "ar") return saved;
  } catch {
    /* storage blocked */
  }
  return navigator.language?.startsWith("ar") ? "ar" : "en";
}

export default function App() {
  const [lang, setLang] = useState<Lang>(initialLang);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const { messages, busy, send, retry, stop, reset } = useChat();
  const t = STRINGS[lang];

  const scroller = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.title = t.title;
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch {
      /* storage blocked */
    }
  }, [lang, t.title]);

  useEffect(() => {
    getHealth().then(setHealth);
  }, []);

  // Follow the stream only while the reader is at the bottom.
  useEffect(() => {
    const el = scroller.current;
    if (el && atBottom) el.scrollTop = el.scrollHeight;
  }, [messages, atBottom]);

  const onScroll = useCallback(() => {
    const el = scroller.current;
    if (el) setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  }, []);

  const scrollDown = () => {
    const el = scroller.current;
    el?.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-line bg-bg/80 px-4 py-2.5 backdrop-blur sm:px-6">
        <div className="min-w-0">
          <h1 className="truncate text-[15px] font-semibold">{t.title}</h1>
          <p className="hidden truncate text-xs text-muted sm:block">{t.subtitle}</p>
        </div>
        <nav className="flex shrink-0 items-center gap-1">
          <HeaderButton onClick={() => setLang(lang === "en" ? "ar" : "en")} label={t.langToggle}>
            <Languages className="size-4" />
            <span className="text-xs font-medium">{t.langToggle}</span>
          </HeaderButton>
          <HeaderButton onClick={() => setAboutOpen(true)} label={t.about}>
            <Info className="size-4" />
          </HeaderButton>
          {messages.length > 0 && (
            <HeaderButton onClick={reset} label={t.newChat}>
              <SquarePen className="size-4" />
            </HeaderButton>
          )}
        </nav>
      </header>

      <main ref={scroller} onScroll={onScroll} className="relative flex-1 overflow-y-auto px-4 sm:px-6">
        {messages.length === 0 ? (
          <EmptyState title={t.heroTitle} body={t.heroBody} starters={t.starters} onPick={send} />
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-6 py-6" aria-live="polite">
            {messages.map((m) =>
              m.role === "user" ? (
                <UserMessage key={m.id} message={m} />
              ) : (
                <AssistantMessage key={m.id} message={m} t={t} onRetry={() => retry(m.id)} />
              ),
            )}
          </div>
        )}
      </main>

      <div className="relative border-t border-line bg-bg px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6">
        {!atBottom && messages.length > 0 && (
          <button
            type="button"
            onClick={scrollDown}
            aria-label={t.scrollDown}
            className="absolute -top-12 left-1/2 grid size-9 -translate-x-1/2 place-items-center rounded-full border border-line bg-surface shadow-md hover:border-accent"
          >
            <ArrowDown className="size-4" />
          </button>
        )}
        <Composer
          busy={busy}
          placeholder={t.placeholder}
          sendLabel={t.send}
          stopLabel={t.stop}
          disclaimer={t.disclaimer}
          onSend={send}
          onStop={stop}
        />
      </div>

      <AboutDrawer open={aboutOpen} onClose={() => setAboutOpen(false)} health={health} lang={lang} />
    </div>
  );
}

function HeaderButton({ onClick, label, children }: { onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-muted transition hover:bg-sunken hover:text-ink"
    >
      {children}
    </button>
  );
}
