import { describe, expect, it } from "vitest";
import type { SourceRef } from "../types";
import { splitSources } from "./sources";

const src = (n: number, cited: boolean): SourceRef => ({
  n,
  cited,
  title: `t${n}`,
  url: `https://x/${n}`,
  source: "darglobal",
  record_type: "project",
  record_id: `r${n}`,
  snippet: "",
});

describe("splitSources", () => {
  const sources = [src(1, true), src(2, false), src(3, true)];

  it("shows everything while streaming", () => {
    expect(splitSources(sources, false)).toEqual({ primary: sources, others: [] });
  });

  it("final answer: cited are sources, the rest are folded", () => {
    const { primary, others } = splitSources(sources, true);
    expect(primary.map((s) => s.n)).toEqual([1, 3]);
    expect(others.map((s) => s.n)).toEqual([2]);
  });

  it("an answer that cites nothing (e.g. off-topic decline) shows no sources", () => {
    const declined = [src(1, false), src(2, false)];
    expect(splitSources(declined, true)).toEqual({ primary: [], others: declined });
  });
});
