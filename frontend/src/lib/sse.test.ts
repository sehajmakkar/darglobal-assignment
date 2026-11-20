import { describe, expect, it } from "vitest";
import { SSEParser } from "./sse";

describe("SSEParser", () => {
  it("parses events split across chunks", () => {
    const parser = new SSEParser();
    expect(parser.feed('event: token\ndata: {"text":"Hel')).toEqual([]);
    expect(parser.feed('lo"}\n\nevent: done\ndata: {}\n\n')).toEqual([
      { event: "token", data: '{"text":"Hello"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("handles CRLF, comments and multi-line data", () => {
    const parser = new SSEParser();
    expect(parser.feed(": ping\r\n\r\nevent: x\r\ndata: a\r\ndata: b\r\n\r\n")).toEqual([
      { event: "x", data: "a\nb" },
    ]);
  });
});
