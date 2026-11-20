// Mirrors dgbot.api.schemas / dgbot.domain.chat (keep in sync).

export type Lang = "en" | "ar";

export interface SourceRef {
  n: number;
  title: string;
  url: string;
  source: "darglobal" | "wasalt" | string;
  record_type: string;
  record_id: string;
  snippet: string;
  cited: boolean;
}

export interface ChatAnswer {
  answer: string;
  sources: SourceRef[];
  lang: Lang;
  model: string | null;
  cached: boolean;
  latency_ms: number;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface Health {
  status: "ok";
  version: string;
  env: string;
  ready: boolean;
  detail: string | null;
  index: {
    embedding_model?: string;
    chunks?: number;
    chunks_by_type?: Record<string, number>;
    listings_rows?: number;
    snapshot_fingerprint?: string;
    built_at?: string;
    data_fetched?: string;
  } | null;
  llm_models: string[];
}

export type ErrorKind = "quota" | "unavailable" | "rate_limited" | "network" | "invalid" | "not_ready";
