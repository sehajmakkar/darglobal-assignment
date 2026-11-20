import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Health, Lang } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
  health: Health | null;
  lang: Lang;
}

const COPY = {
  en: {
    title: "About this assistant",
    what: "What it knows",
    projects: "DarGlobal projects, partners, press, blog & insights",
    listings: "Wasalt listings (from public sitemaps)",
    passages: "searchable passages",
    data: "Data collected",
    model: "Language models (free, via OpenRouter)",
    search: "Search",
    searchBody: "Hybrid semantic + keyword search (EmbeddingGemma + BM25) over the scraped data; exact counts from a listings database.",
    limits: "Limitations",
    limitsItems: [
      "DarGlobal doesn't publish prices, so the assistant never quotes one.",
      "Most Wasalt listings come from public sitemaps: type, size and bedrooms, but no price or city. Prices exist only for a small hand-saved sample.",
      "Some Wasalt sizes are approximate (listing URLs drop the decimal point).",
      "Free models are rate-limited; if the daily quota is used up, try again later.",
    ],
    code: "Source code",
  },
  ar: {
    title: "عن المساعد",
    what: "ما يعرفه",
    projects: "مشاريع دار جلوبال وشركاؤها وأخبارها ومدونتها",
    listings: "إعلانات وصلت (من خرائط الموقع العامة)",
    passages: "مقطعاً قابلاً للبحث",
    data: "تاريخ جمع البيانات",
    model: "نماذج اللغة (مجانية عبر OpenRouter)",
    search: "البحث",
    searchBody: "بحث هجين دلالي ونصي (EmbeddingGemma + BM25) في البيانات المجمّعة، مع أعداد دقيقة من قاعدة بيانات الإعلانات.",
    limits: "القيود",
    limitsItems: [
      "لا تنشر دار جلوبال الأسعار، لذلك لا يذكر المساعد أي سعر لمشاريعها.",
      "معظم إعلانات وصلت من خرائط الموقع العامة: النوع والمساحة وعدد الغرف دون السعر أو المدينة. الأسعار متوفرة لعينة صغيرة فقط.",
      "بعض مساحات وصلت تقريبية.",
      "النماذج المجانية محدودة الاستخدام؛ إذا نفدت الحصة اليومية، حاول لاحقاً.",
    ],
    code: "الشيفرة المصدرية",
  },
} as const;

export function AboutDrawer({ open, onClose, health, lang }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const c = COPY[lang];

  useEffect(() => {
    if (!open) return;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const index = health?.index;
  const fmt = (n?: number) => (n === undefined ? "—" : n.toLocaleString(lang === "ar" ? "ar-SA" : "en-US"));
  const date = index?.data_fetched ?? index?.built_at;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={c.title}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-md overflow-y-auto border-s border-line bg-surface p-5 shadow-xl outline-none"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{c.title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 hover:bg-sunken">
            <X className="size-4" />
          </button>
        </div>

        <h3 className="mt-5 text-xs font-medium tracking-wide text-muted uppercase">{c.what}</h3>
        <dl className="mt-2 grid grid-cols-2 gap-2">
          <Stat value={fmt(index?.chunks)} label={c.passages} />
          <Stat value={fmt(index?.listings_rows)} label={c.listings} />
        </dl>
        <p className="mt-2 text-sm text-muted">{c.projects}.</p>

        {date && (
          <>
            <h3 className="mt-5 text-xs font-medium tracking-wide text-muted uppercase">{c.data}</h3>
            <p className="mt-1 text-sm" dir="ltr">
              {new Date(date).toLocaleDateString(lang === "ar" ? "ar-SA" : "en-GB", { dateStyle: "long" })}
            </p>
          </>
        )}

        <h3 className="mt-5 text-xs font-medium tracking-wide text-muted uppercase">{c.model}</h3>
        <ul className="mt-1 space-y-0.5 text-sm" dir="ltr">
          {(health?.llm_models ?? []).slice(0, 3).map((m) => (
            <li key={m} className="truncate font-mono text-xs">
              {m}
            </li>
          ))}
        </ul>

        <h3 className="mt-5 text-xs font-medium tracking-wide text-muted uppercase">{c.search}</h3>
        <p className="mt-1 text-sm leading-relaxed">{c.searchBody}</p>

        <h3 className="mt-5 text-xs font-medium tracking-wide text-muted uppercase">{c.limits}</h3>
        <ul className="mt-1 list-disc space-y-1.5 ps-5 text-sm leading-relaxed">
          {c.limitsItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>

        <a
          href="https://github.com/sehajmakkar/darglobal-assignment"
          target="_blank"
          rel="noopener noreferrer"
          className="mt-6 inline-block text-sm font-medium text-accent hover:underline"
        >
          {c.code} ↗
        </a>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-line bg-sunken p-3">
      <dt className="text-xl font-semibold tabular-nums">{value}</dt>
      <dd className="text-xs text-muted">{label}</dd>
    </div>
  );
}
