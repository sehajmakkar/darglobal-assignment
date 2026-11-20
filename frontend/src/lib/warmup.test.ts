import { describe, expect, it } from "vitest";
import type { Health } from "../types";
import { WAIT_S, waitUntilReady } from "./warmup";

const health = (warming_up: boolean, ready: boolean): Health => ({
  status: "ok",
  version: "0.1.0",
  env: "test",
  ready,
  warming_up,
  detail: null,
  index: null,
  llm_models: [],
});

function fakeServer(replies: Health[]) {
  const waits: number[] = [];
  const fetchHealth = async (waitS: number) => {
    waits.push(waitS);
    return replies.shift() ?? null;
  };
  return { fetchHealth, waits };
}

describe("waitUntilReady", () => {
  it("a warm server is checked once, without waiting", async () => {
    const { fetchHealth, waits } = fakeServer([health(false, true)]);
    const seen: (Health | null)[] = [];
    await waitUntilReady(fetchHealth, (h) => seen.push(h));
    expect(waits).toEqual([0]);
    expect(seen.map((h) => h?.ready)).toEqual([true]);
  });

  it("a warming server is long-polled until ready", async () => {
    const { fetchHealth, waits } = fakeServer([health(true, false), health(false, true)]);
    const seen: (Health | null)[] = [];
    await waitUntilReady(fetchHealth, (h) => seen.push(h));
    expect(waits).toEqual([0, WAIT_S]);
    expect(seen.map((h) => h?.warming_up)).toEqual([true, false]);
  });

  it("gives up after a few rounds instead of polling forever", async () => {
    const { fetchHealth, waits } = fakeServer(Array.from({ length: 10 }, () => health(true, false)));
    await waitUntilReady(fetchHealth, () => {}, 2);
    expect(waits).toEqual([0, WAIT_S, WAIT_S]);
  });
});
