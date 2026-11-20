import type { ErrorKind, Lang } from "../types";

export interface Starter {
  source: "darglobal" | "wasalt";
  text: string;
}

interface Strings {
  title: string;
  subtitle: string;
  heroTitle: string;
  heroBody: string;
  placeholder: string;
  send: string;
  stop: string;
  newChat: string;
  about: string;
  searching: string;
  writing: string;
  sources: string;
  alsoSearched: string;
  openSource: string;
  copy: string;
  copied: string;
  cached: string;
  answeredBy: string;
  retry: string;
  scrollDown: string;
  langToggle: string;
  disclaimer: string;
  warmingUp: string;
  wasaltData: string;
  errors: Record<ErrorKind, string>;
  rateLimited: (seconds: number) => string;
  starters: Starter[];
}

export const STRINGS: Record<Lang, Strings> = {
  en: {
    title: "DarGlobal × Wasalt Assistant",
    subtitle: "Answers from public DarGlobal & Wasalt data, with sources",
    heroTitle: "Ask about luxury projects or Saudi listings",
    heroBody:
      "I answer from DarGlobal's website and Wasalt's public listings, and I cite every source. I reply in English or Arabic.",
    placeholder: "Ask about a DarGlobal project or Wasalt listings…",
    send: "Send",
    stop: "Stop",
    newChat: "New chat",
    about: "About this assistant",
    searching: "Searching DarGlobal & Wasalt…",
    writing: "Writing the answer…",
    sources: "Sources",
    alsoSearched: "Also searched",
    openSource: "Open source",
    copy: "Copy answer",
    copied: "Copied",
    cached: "instant (cached)",
    answeredBy: "Answered by",
    retry: "Try again",
    scrollDown: "Scroll to latest",
    langToggle: "العربية",
    disclaimer: "AI answers can be wrong — check the sources. DarGlobal doesn't publish prices.",
    warmingUp: "Waking up the assistant after a quiet spell — your first answer may take up to a minute.",
    wasaltData: "Wasalt data · exact counts",
    errors: {
      quota: "The assistant has used today's free model quota. Please try again later.",
      unavailable: "The language model is busy right now. Please try again in a moment.",
      rate_limited: "You're sending questions quickly — please wait a moment.",
      network: "Can't reach the server. Check your connection and try again.",
      invalid: "That message couldn't be sent. Please shorten it and try again.",
      not_ready: "The assistant is starting up. Please try again in a few seconds.",
    },
    rateLimited: (s) => `Too many questions from this connection — try again in ${formatWait(s)}.`,
    starters: [
      { source: "darglobal", text: "What is The Astera, and where is it?" },
      { source: "darglobal", text: "Which DarGlobal projects are in Oman?" },
      { source: "darglobal", text: "Which brands has DarGlobal partnered with?" },
      { source: "wasalt", text: "3-bedroom apartments for sale in Riyadh" },
      { source: "wasalt", text: "Villas for rent in Jeddah" },
      { source: "wasalt", text: "How many listings does Wasalt have?" },
    ],
  },
  ar: {
    title: "مساعد دار جلوبال × وصلت",
    subtitle: "إجابات من بيانات دار جلوبال ووصلت العامة مع المصادر",
    heroTitle: "اسأل عن المشاريع الفاخرة أو العقارات في السعودية",
    heroBody: "أجيب من موقع دار جلوبال وإعلانات وصلت العامة، وأذكر مصدر كل معلومة. أجيب بالعربية أو الإنجليزية.",
    placeholder: "اسأل عن مشروع من دار جلوبال أو عقارات على وصلت…",
    send: "إرسال",
    stop: "إيقاف",
    newChat: "محادثة جديدة",
    about: "عن المساعد",
    searching: "جارٍ البحث في دار جلوبال ووصلت…",
    writing: "جارٍ كتابة الإجابة…",
    sources: "المصادر",
    alsoSearched: "تم البحث أيضاً",
    openSource: "فتح المصدر",
    copy: "نسخ الإجابة",
    copied: "تم النسخ",
    cached: "فوري (محفوظ)",
    answeredBy: "أجاب",
    retry: "حاول مرة أخرى",
    scrollDown: "الانتقال إلى الأحدث",
    langToggle: "English",
    disclaimer: "قد تخطئ إجابات الذكاء الاصطناعي — راجع المصادر. لا تنشر دار جلوبال الأسعار.",
    warmingUp: "جارٍ تشغيل المساعد بعد فترة خمول — قد تستغرق إجابتك الأولى حتى دقيقة.",
    wasaltData: "بيانات وصلت · أعداد دقيقة",
    errors: {
      quota: "استنفد المساعد الحصة المجانية لهذا اليوم. يرجى المحاولة لاحقاً.",
      unavailable: "نموذج اللغة مشغول حالياً. يرجى المحاولة بعد قليل.",
      rate_limited: "ترسل الأسئلة بسرعة — يرجى الانتظار قليلاً.",
      network: "تعذّر الوصول إلى الخادم. تحقّق من الاتصال وحاول مرة أخرى.",
      invalid: "تعذّر إرسال الرسالة. يرجى اختصارها والمحاولة مرة أخرى.",
      not_ready: "المساعد قيد التشغيل. يرجى المحاولة بعد ثوانٍ.",
    },
    rateLimited: (s) => `أسئلة كثيرة من هذا الاتصال — حاول بعد ${formatWait(s)}.`,
    starters: [
      { source: "darglobal", text: "ما هو مشروع ذا أستيرا وأين يقع؟" },
      { source: "darglobal", text: "ما هي مشاريع دار جلوبال في سلطنة عمان؟" },
      { source: "darglobal", text: "ما هي العلامات التجارية الشريكة لدار جلوبال؟" },
      { source: "wasalt", text: "شقق 3 غرف للبيع في الرياض" },
      { source: "wasalt", text: "فلل للإيجار في جدة" },
      { source: "wasalt", text: "كم عدد العقارات المعروضة على وصلت؟" },
    ],
  },
};

function formatWait(seconds: number): string {
  if (seconds < 90) return `${seconds}s`;
  const minutes = Math.ceil(seconds / 60);
  return minutes < 90 ? `${minutes} min` : `${Math.ceil(minutes / 60)} h`;
}
