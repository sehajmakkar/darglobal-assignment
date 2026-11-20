import { useCallback, useRef, useState } from "react";
import { ApiError, streamChat } from "../lib/api";
import type { ChatAnswer, ChatTurn, ErrorKind, SourceRef } from "../types";

export type MessageStatus = "searching" | "streaming" | "done" | "stopped" | "error";

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  content: string;
  status: MessageStatus;
  sources: SourceRef[];
  answer?: ChatAnswer;
  error?: { kind: ErrorKind; message: string; retryAfterS?: number };
  question: string;
}

export type Message = UserMessage | AssistantMessage;

const MAX_HISTORY_TURNS = 10;
let counter = 0;
const nextId = () => `m${Date.now()}-${counter++}`;

/** Conversation state + streaming. Components only render what this hook exposes. */
export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const controller = useRef<AbortController | null>(null);
  const busy = messages.some(
    (m) => m.role === "assistant" && (m.status === "searching" || m.status === "streaming"),
  );

  const update = useCallback((id: string, patch: (m: AssistantMessage) => AssistantMessage) => {
    setMessages((all) => all.map((m) => (m.id === id && m.role === "assistant" ? patch(m) : m)));
  }, []);

  const ask = useCallback(
    async (question: string, history: ChatTurn[]) => {
      const assistantId = nextId();
      setMessages((all) => [
        ...all,
        { id: nextId(), role: "user", content: question },
        { id: assistantId, role: "assistant", content: "", status: "searching", sources: [], question },
      ]);
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      try {
        await streamChat(
          question,
          history,
          {
            onSources: (sources) => update(assistantId, (m) => ({ ...m, sources })),
            onToken: (text) =>
              update(assistantId, (m) => ({ ...m, status: "streaming", content: m.content + text })),
            onDone: (answer) =>
              update(assistantId, (m) => ({
                ...m,
                status: "done",
                content: answer.answer,
                sources: answer.sources,
                answer,
              })),
          },
          abort.signal,
        );
        if (abort.signal.aborted) {
          update(assistantId, (m) => ({ ...m, status: m.content ? "stopped" : "error", error: m.content ? undefined : { kind: "network", message: "stopped" } }));
        }
      } catch (err) {
        const e = err instanceof ApiError ? err : new ApiError("network", String(err));
        update(assistantId, (m) => ({
          ...m,
          status: "error",
          error: { kind: e.kind, message: e.message, retryAfterS: e.retryAfterS },
        }));
      } finally {
        if (controller.current === abort) controller.current = null;
      }
    },
    [update],
  );

  const send = useCallback(
    (text: string) => {
      const question = text.trim();
      if (!question || busy) return;
      ask(question, toHistory(messages));
    },
    [ask, busy, messages],
  );

  /** Re-ask a failed question with the history that preceded it. */
  const retry = useCallback(
    (assistantId: string) => {
      const index = messages.findIndex((m) => m.id === assistantId);
      const failed = messages[index];
      if (index < 1 || !failed || failed.role !== "assistant" || busy) return;
      const before = messages.slice(0, index - 1);
      setMessages(before);
      ask(failed.question, toHistory(before));
    },
    [ask, busy, messages],
  );

  const stop = useCallback(() => controller.current?.abort(), []);

  const reset = useCallback(() => {
    controller.current?.abort();
    setMessages([]);
  }, []);

  return { messages, busy, send, retry, stop, reset };
}

/** Completed turns only (no failed/empty answers), most recent last, capped. */
function toHistory(messages: Message[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  for (const m of messages) {
    if (m.role === "user") turns.push({ role: "user", content: m.content });
    else if (m.content && (m.status === "done" || m.status === "stopped"))
      turns.push({ role: "assistant", content: m.content.slice(0, 1500) });
    else turns.pop(); // drop the question whose answer failed
  }
  return turns.slice(-MAX_HISTORY_TURNS);
}
