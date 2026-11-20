import type { ChatAnswer, ChatTurn, ErrorKind, Health, Lang, SourceRef } from "../types";
import { SSEParser } from "./sse";

export class ApiError extends Error {
  constructor(
    public kind: ErrorKind,
    message: string,
    public retryAfterS?: number,
  ) {
    super(message);
  }
}

export interface StreamHandlers {
  onSources: (sources: SourceRef[], lang: Lang) => void;
  onToken: (text: string) => void;
  onDone: (answer: ChatAnswer) => void;
}

/** POST /api/chat and dispatch SSE events. Resolves when the stream ends. */
export async function streamChat(
  message: string,
  history: ChatTurn[],
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ message, history, stream: true }),
      signal,
    });
  } catch (err) {
    if (signal.aborted) return;
    throw new ApiError("network", String(err));
  }
  if (!response.ok || !response.body) throw await toApiError(response);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SSEParser();
  for (;;) {
    let chunk: ReadableStreamReadResult<string>;
    try {
      chunk = await reader.read();
    } catch (err) {
      if (signal.aborted) return;
      throw new ApiError("network", String(err));
    }
    if (chunk.done) return;
    for (const { event, data } of parser.feed(chunk.value)) {
      const payload = JSON.parse(data);
      if (event === "sources") handlers.onSources(payload.sources, payload.lang);
      else if (event === "token") handlers.onToken(payload.text);
      else if (event === "done") handlers.onDone(payload as ChatAnswer);
      else if (event === "error") throw new ApiError(payload.code as ErrorKind, payload.message);
    }
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail = response.statusText;
  try {
    const body = await response.json();
    detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    /* non-JSON error body */
  }
  if (response.status === 429) {
    const retry = Number(response.headers.get("Retry-After") ?? "60");
    return new ApiError("rate_limited", detail, Number.isFinite(retry) ? retry : 60);
  }
  if (response.status === 503) return new ApiError("not_ready", detail);
  if (response.status === 422) return new ApiError("invalid", detail);
  return new ApiError("unavailable", detail);
}

/** GET /api/health. `waitS` > 0 holds the request until the search model has loaded. */
export async function getHealth(waitS = 0): Promise<Health | null> {
  try {
    const response = await fetch(waitS > 0 ? `/api/health?wait=${waitS}` : "/api/health");
    return response.ok ? ((await response.json()) as Health) : null;
  } catch {
    return null;
  }
}
